from datetime import timedelta
from itertools import chain
import json
from operator import attrgetter
import uuid
import re
from zoneinfo import ZoneInfo

from django.apps import apps
from django.conf import settings
from django.contrib.auth import authenticate, logout
from django.core import exceptions
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.password_validation import validate_password
from django.db import transaction, IntegrityError
from django.db.models import Q, Case, When, Value, IntegerField, Count
from django.db.models.functions import Lower
from django.http import HttpResponse, HttpResponseNotAllowed, Http404
from django.middleware import csrf
from django.shortcuts import get_object_or_404
from django.utils import translation, timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from safedelete.models import SOFT_DELETE_CASCADE

from .email import email_manager
from .models import Subscription, Connection, AppSession, DiscoverFeed, Persona, Interest
from account.models import FriendRequest, BlockRec
from account.serializers import (CurrentUserSerializer, CurrentUserSignupSerializer, \
                                 UserFriendRequestCreateSerializer, UserFriendRequestUpdateSerializer, \
                                 UserFriendshipStatusSerializer, \
                                 UserEmailSerializer, UserUsernameSerializer, UserBirthDateSerializer, \
                                 UserInviterEmailBirthDateSerializer, FriendListSerializer, \
                                 UserFriendsUpdateSerializer, UserMinimumSerializer, BlockRecSerializer, \
                                 UserFriendRequestSerializer, UserPasswordSerializer, UserProfileSerializer, \
                                 AppSessionSerializer, FriendFriendListSerializer, \
                                 UserFollowRequestCreateSerializer, UserFollowRequestSerializer, \
                                 UserFollowRequestUpdateSerializer, UserMinimalSerializer, \
                                 UserInterestUpdateSerializer, UserPersonaUpdateSerializer, \
                                 InterestSerializer, PersonaSerializer)
from adoorback.utils.content_types import get_generic_relation_type, get_friend_request_type
from adoorback.utils.exceptions import ExistingUsername, LongUsername, InvalidUsername, ExistingEmail, InvalidEmail, \
    NoUsername, WrongPassword, ExistingUsername, InvalidInviterEmail
from adoorback.utils.validators import adoor_exception_handler
from note.models import Note
from note.serializers import NoteSerializer, DefaultFriendNoteSerializer
from notification.models import NotificationActor
from qna.models import ResponseRequest
from qna.models import Question, Response as _Response
from qna.serializers import ResponseSerializer, DailyQuestionSerializer
from qna.serializers import GroupedResponseRequestSerializer, ResponseSerializer
from account.models import FollowRequest, Follow, PERSONA_CHOICES, INTEREST_CHOICES_BASE
from tracking.utils import clean_session_key
import random

User = get_user_model()


def normalize_tag(t):
    return t.lower().replace('-', '').replace('_', '').replace(' ', '')

def parse_hashtags_or_list(data):
    if not data:
        return []
    if isinstance(data, list):
        return data
    return re.findall(r'#([^\s#]+)', data)

def get_or_create_normalized_tag(model, raw_tag):
    normalized_input = normalize_tag(raw_tag)
    # Fetch all in-memory for matching (optimized for small-medium scale)
    all_instances = list(model.objects.all_with_deleted())
    for instance in all_instances:
        if normalize_tag(instance.content) == normalized_input:
            if instance.deleted:
                instance.undelete()
            return instance
    # Not found, create new PascalCase version
    pascal_content = ''.join(word.capitalize() for word in re.split(r'[-_]', raw_tag))
    return model.objects.create(content=pascal_content)

def update_user_personas_logic(user, persona_keys):
    # This function now expects a list of KEYS from PERSONA_CHOICES
    
    from account.models import PERSONA_CHOICES
    
    # 1. Update ArrayField (stores keys)
    user.persona = persona_keys
    user.save()

    # 2. Update ManyToMany Field (stores Label objects)
    # Map keys to labels
    key_to_label = dict(PERSONA_CHOICES)
    new_labels = {key_to_label[key] for key in persona_keys if key in key_to_label}
    
    # Get all current personas
    current_personas = list(user.user_personas.all())
    
    # Identify "Choice Personas" (those in the predefined list) vs "Custom Personas" (hashtags)
    # Predefined labels set for quick lookup
    all_choice_labels_normalized = {normalize_tag(label) for _, label in PERSONA_CHOICES}
    
    custom_personas = []
    for p in current_personas:
        if normalize_tag(p.content) not in all_choice_labels_normalized:
            custom_personas.append(p)
            
    # Get or create new Persona instances for the new selection
    new_choice_personas = [get_or_create_normalized_tag(Persona, label) for label in new_labels]
    
    # Final set = Custom Personas (preserved) + New Choice Personas
    final_persona_set = custom_personas + new_choice_personas
    user.user_personas.set(final_persona_set)
    
    # Orphan cleanup for removed choice personas
    # We only check personas that were removed from the user's set
    removed_personas = [p for p in current_personas if p not in final_persona_set]
    for p in removed_personas:
        if normalize_tag(p.content) in all_choice_labels_normalized: # Only cleanup choice personas here?
             # Actually orphan cleanup applies to any tag that has no users.
             if p.users.count() == 0:
                 p.delete()

def update_user_interests_logic(user, interest_labels):
    # This function expects a list of LABELS from INTEREST_CHOICES_BASE
    
    from account.models import INTEREST_CHOICES_BASE
    
    # Predefined interests set for quick lookup
    all_choice_interests_normalized = {normalize_tag(label) for label in INTEREST_CHOICES_BASE}
    
    # Get all current interests
    current_interests = list(user.user_interests.all())
    
    # Separate Custom vs Base
    custom_interests = []
    for i in current_interests:
        if normalize_tag(i.content) not in all_choice_interests_normalized:
            custom_interests.append(i)
            
    # Get or create new Interest instances for the new selection
    new_choice_interests = [get_or_create_normalized_tag(Interest, label) for label in interest_labels]
    
    # Final set = Custom Interests (preserved) + New Choice Interests
    final_interest_set = custom_interests + new_choice_interests
    user.user_interests.set(final_interest_set)

    # Orphan cleanup
    removed_interests = [i for i in current_interests if i not in final_interest_set]
    for i in removed_interests:
        if i.users.count() == 0:
            i.delete()


@transaction.atomic
@ensure_csrf_cookie
def token_anonymous(request):
    if request.method == 'GET':
        return HttpResponse(status=204)
    else:
        return HttpResponseNotAllowed(['GET'])


def get_access_token_for_user(user):
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token)


class UserLogin(APIView):
    authentication_classes = []

    def get_exception_handler(self):
        return adoor_exception_handler

    def post(self, request, format=None):
        data = request.data
        response = Response(
            data={"message": "Login successful"},
            content_type="application/json"
        )

        username = data.get('username', None)
        password = data.get('password', None)
        try:
            user = User.objects.get(Q(username=username) | Q(email=username))
        except:
            raise NoUsername()

        user = authenticate(username=user.username, password=password)
        if user is not None:
            access_token = get_access_token_for_user(user)
            response.set_cookie(
                key=settings.SIMPLE_JWT['AUTH_COOKIE'],
                value=access_token,
                max_age=settings.SIMPLE_JWT['AUTH_COOKIE_MAX_AGE'],
                secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
                # FIXME: Skip XSS security issues for smooth testing
                # httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
                samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
            )
            csrf.get_token(request)

            if user.username in ['user_me', 'user_friend_A', 'user_friend_B'] and user.current_ver == 'experiment':
                user.current_ver = 'default'
                user.save()
            return response
        else:
            raise WrongPassword()


class UserLogout(APIView):

    def get_exception_handler(self):
        return adoor_exception_handler

    def get(self, request):
        logout(request)
        response = Response(data={"message": "Logout successful"}, content_type="application/json")
        response.delete_cookie(settings.SIMPLE_JWT['AUTH_COOKIE'])
        return response


class UserEmailCheck(generics.CreateAPIView):
    serializer_class = UserEmailSerializer
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = []

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            if 'email' in e.detail:
                if 'unique' in e.get_codes()['email']:
                    raise ExistingEmail()
                if 'invalid' in e.get_codes()['email']:
                    raise InvalidEmail()
            raise e

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=201, headers=headers)


class UserPasswordCheck(generics.CreateAPIView):
    serializer_class = UserPasswordSerializer
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = []

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            raise e

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=201, headers=headers)


class UserUsernameCheck(generics.CreateAPIView):
    serializer_class = UserUsernameSerializer
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = []

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            if 'username' in e.detail:
                if 'unique' in e.get_codes()['username']:
                    raise ExistingUsername()
                if 'invalid' in e.get_codes()['username']:
                    raise InvalidUsername()
                if 'max_length' in e.get_codes()['username']:
                    raise LongUsername()
            raise e

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=201, headers=headers)


class UserBirthDateCheck(generics.CreateAPIView):
    serializer_class = UserBirthDateSerializer
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = []

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=201, headers=headers)


class UserInviterBirthDateCheck(generics.CreateAPIView):
    serializer_class = UserInviterEmailBirthDateSerializer
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = []

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)

        serializer = self.get_serializer(data=request.data)
        # check if email format is invalid
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            if 'email' in e.detail:
                if 'invalid' in e.get_codes()['email']:
                    raise InvalidEmail()
            raise e

        # check if user with invited email exists
        invited_email = request.data.get('email').strip().lower()        
        try:
            inviter = User.objects.get(email=invited_email)
            user_group = inviter.user_group
            current_ver = inviter.current_ver
        except ObjectDoesNotExist:
            raise InvalidInviterEmail()

        response_data = {
            'email': invited_email,
            'inviter_id': inviter.id,
            'user_group': user_group,
            'current_ver': current_ver
        }

        return Response(response_data, status=status.HTTP_200_OK)


class UserSignup(generics.CreateAPIView):
    serializer_class = CurrentUserSignupSerializer
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = []

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            raise e

        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)

        response = Response(serializer.data, status=201, headers=headers)
        user = serializer.instance
        access_token = get_access_token_for_user(user)
        response.set_cookie(
            key=settings.SIMPLE_JWT['AUTH_COOKIE'],
            value=access_token,
            max_age=settings.SIMPLE_JWT['AUTH_COOKIE_MAX_AGE'],
            secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
            # FIXME: Skip security issues for smooth testing
            # httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
            samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
        )
        csrf.get_token(request)

        return response
    

class UserVerifyEmail(generics.UpdateAPIView):
    queryset = User.objects.all()
    serializer_class = UserProfileSerializer

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        uidb64 = self.kwargs.get('uidb64')
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
        return user

    def update(self, request, *args, **kwargs):
        token = self.kwargs.get('token')
        user = self.get_object()
        if not user:
            return HttpResponse(status=404)
        if email_manager.check_activate_token(user, token):
            self.verify_email(user)
            return HttpResponse(status=204)
        else:
            return HttpResponse(status=400)

    @transaction.atomic
    def verify_email(self, user):
        user.email_verified = True
        user.save()


class SendResetPasswordEmail(generics.CreateAPIView):
    serializer_class = CurrentUserSerializer
    authentication_classes = []

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        return User.objects.filter(email=self.request.data['email']).first()

    def post(self, request, *args, **kwargs):
        user = self.get_object()

        if user:
            email_manager.send_reset_password_email(user)
            return HttpResponse(status=200)
        else:
            return HttpResponse(status=404, content=b"We couldn't find a user with the given email.")
    

class ResetPassword(generics.UpdateAPIView):
    '''
    Reset password API for users who haven't signed in.
    (= Users who arrive at the reset password page through reset password email.)
    (= Users who have forgotten their password.)
    '''
    serializer_class = CurrentUserSerializer
    authentication_classes = []
    queryset = User.objects.all()

    def get_exception_handler(self):
        return adoor_exception_handler

    def update(self, request, *args, **kwargs):
        user = self.get_object()

        # Verify token
        token = request.data.get('token')
        if not token or not email_manager.check_reset_password_token(user, token):
            return HttpResponse(status=403, content=b"Invalid or expired token.")

        self.update_password(user, self.request.data['password'])

        if not user.has_changed_pw:
            user.has_changed_pw = True
            user.save()
        return HttpResponse(status=200)

    @transaction.atomic
    def update_password(self, user, raw_password):
        errors = dict()
        try:
            validate_password(password=raw_password, user=user)
        except exceptions.ValidationError as e:
            errors['password'] = [list(e.messages)[0]]
        if errors:
            raise ValidationError(errors)
        user.set_password(raw_password)
        user.save()


class CurrentUserResetPassword(generics.UpdateAPIView):
    '''
    Reset password API for currently signed in users.
    '''
    serializer_class = CurrentUserSerializer
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def update(self, request, *args, **kwargs):
        user = request.user

        try:
            self.update_password(user, request.data['password'])
        except ValidationError as e:
            return Response({"error": e.detail}, status=400)

        if not user.has_changed_pw:
            user.has_changed_pw = True
            user.save()
        return Response(status=200)

    @transaction.atomic
    def update_password(self, user, raw_password):
        errors = dict()
        try:
            validate_password(password=raw_password, user=user)
        except exceptions.ValidationError as e:
            errors['password'] = [list(e.messages)[0]]
        if errors:
            raise ValidationError(errors)
        user.set_password(raw_password)
        user.save()


class UserPasswordConfirm(APIView):

    def get_exception_handler(self):
        return adoor_exception_handler

    def post(self, request, format=None):
        user = request.user

        response = Response(data={"message": "Password confirmed"}, content_type="application/json")
        password = request.data.get('password', None)

        auth_user = authenticate(username=user.username, password=password)
        if auth_user is not None:
            return response
        else:
            raise WrongPassword()


class UserSearch(generics.ListAPIView):
    serializer_class = UserFriendshipStatusSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        query = self.request.GET.get('query')
        user = self.request.user
        user_id = user.id
        friend_ids = user.connected_user_ids
        user_block_rec_ids = user.block_recs.all().values_list('blocked_user', flat=True)

        qs = User.objects.none()
        if query:
            # username starts with query
            start_users = User.objects.filter(username__startswith=query, is_superuser=False) \
                .order_by('username').exclude(id=user_id).exclude(id__in=user_block_rec_ids)
            friend_start_ids = list(start_users.filter(id__in=friend_ids).values_list('id', flat=True))
            nonfriend_start_ids = list(start_users.exclude(id__in=friend_ids).values_list('id', flat=True))

            # username contains query
            contain_users = User.objects.filter(username__icontains=query, is_superuser=False) \
                .order_by('username').exclude(id=user_id).exclude(id__in=user_block_rec_ids)
            friend_contain_ids = list(contain_users.filter(id__in=friend_ids).values_list('id', flat=True))
            nonfriend_contain_ids = list(contain_users.exclude(id__in=friend_ids).values_list('id', flat=True))

            # all friend users
            qs_ids = friend_start_ids + friend_contain_ids

            # only 20 non-friend users
            nonfriend_qs_ids = nonfriend_start_ids[:20]
            if len(nonfriend_qs_ids) < 20:
                nonfriend_qs_ids += nonfriend_contain_ids[:20 - len(nonfriend_qs_ids)]

            # merge querysets while preserving order
            qs_ids += nonfriend_qs_ids
            cases = [When(id=x, then=Value(i)) for i, x in enumerate(qs_ids)]
            case = Case(*cases, output_field=IntegerField())
            qs = User.objects.filter(id__in=qs_ids).annotate(my_order=case).order_by('my_order')

        return qs


class CurrentUserFriendSearch(generics.ListAPIView):
    serializer_class = UserFriendshipStatusSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        query = self.request.GET.get('query', '').replace(" ", "").lower()
        user = self.request.user
        friends = user.connected_users.annotate(lower_username=Lower('username'))

        if query:
            start_friends = friends.filter(lower_username__startswith=query).order_by('username')
            contain_friends = friends.filter(lower_username__icontains=query).order_by('username')

            qs = start_friends.union(contain_friends, all=False)  # start_friends first *then* contain_friends

            return qs

        return friends


class UserProfile(generics.RetrieveAPIView):
    queryset = User.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'username'

    def get_exception_handler(self):
        return adoor_exception_handler


class UserNoteList(generics.ListAPIView):
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user = self.request.user
        author_username = self.kwargs.get('username')
        author = User.objects.get(username=author_username)
        
        # don't show superuser's note list (Notice must be shown on its own tab)
        if author.is_superuser:
            return Note.objects.none()
    
        all_notes = Note.objects.filter(author=author)
        note_ids = [note.id for note in all_notes if note.is_audience(user)]
        return Note.objects.filter(id__in=note_ids).order_by('-created_at')


class DefaultUserNoteList(generics.ListAPIView):
    serializer_class = DefaultFriendNoteSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user = self.request.user
        all_notes = Note.objects.filter(author__username=self.kwargs.get('username'))
        note_ids = [note.id for note in all_notes if note.is_audience(user)]
        return Note.objects.filter(id__in=note_ids).order_by('-created_at')


class UserResponseList(generics.ListAPIView):
    queryset = _Response.objects.all().order_by('-created_at')
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_serializer_class(self):
        from qna.serializers import ResponseSerializer
        return ResponseSerializer

    def get_queryset(self):
        user = self.request.user
        all_responses = _Response.objects.filter(author__username=self.kwargs.get('username')).order_by('-created_at')
        response_ids = [response.id for response in all_responses if response.is_audience(user)]
        return _Response.objects.filter(id__in=response_ids)


class UserAllPostList(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_combined_items(self):
        user = self.request.user
        author_username = self.kwargs.get('username')
        author = get_object_or_404(User, username=author_username)
        
        # don't show superuser's note list (Notice must be shown on its own tab)
        if author.is_superuser:
            notes = []
        else:
            all_notes = Note.objects.filter(author=author)
            note_ids = [note.id for note in all_notes if note.is_audience(user)]
            notes = list(Note.objects.filter(id__in=note_ids).order_by('-created_at'))

        all_responses = _Response.objects.filter(author=author).order_by('-created_at')
        response_ids = [response.id for response in all_responses if response.is_audience(user)]
        responses = list(_Response.objects.filter(id__in=response_ids))

        combined = sorted(chain(notes, responses), key=lambda x: x.created_at, reverse=True)
        return combined

    def paginate_queryset(self, queryset):
        page = super().paginate_queryset(queryset)
        return page

    def list(self, request, *args, **kwargs):
        combined_items = self.get_combined_items()
        
        page = self.paginate_queryset(combined_items)
        objects_to_serialize = page if page is not None else combined_items
        
        serialized_data = []
        for obj in objects_to_serialize:
            if isinstance(obj, Note):
                serialized = NoteSerializer(obj, context=self.get_serializer_context()).data
                serialized['type'] = 'Note' # Optional: helps client distinguish
            elif isinstance(obj, _Response):
                serialized = ResponseSerializer(obj, context=self.get_serializer_context()).data
                serialized['type'] = 'Response' # Optional
            serialized_data.append(serialized)
            
        return self.get_paginated_response(serialized_data) if page is not None else Response(serialized_data)


class CurrentUserLatestVisibility(APIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get(self, request):
        user = request.user
        
        latest_note = Note.objects.filter(author=user).order_by('-created_at').first()
        latest_response = _Response.objects.filter(author=user).order_by('-created_at').first()
        
        if not latest_note and not latest_response:
            return Response({'visibility': ['close_friends']}, status=200)
            
        if latest_note and not latest_response:
            return Response({'visibility': latest_note.visibility}, status=200)
            
        if not latest_note and latest_response:
            return Response({'visibility': latest_response.visibility}, status=200)
            
        # Both exist
        if latest_note.created_at > latest_response.created_at:
             return Response({'visibility': latest_note.visibility}, status=200)
        else:
             return Response({'visibility': latest_response.visibility}, status=200)


class CurrentUserDetail(generics.RetrieveUpdateAPIView):
    serializer_class = CurrentUserSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        return User.objects.get(id=self.request.user.id)

    @transaction.atomic
    def perform_update(self, serializer):
        # NOTE: We need to use 'updated_user' which might be modified by serializer.save(),
        # however, this method is called *around* serializer.save().
        # Actually standard perform_update calls serializer.save().
        # But here we are overriding it.
        # Let's keep the logic consistent: validate first, then operate.
        # But wait, original code did `serializer.save()` then `updated_user = self.get_object()`.
        # And it used `self.get_object()` before that for old_personas.
        # The refactoring above uses `updated_user` inside `update_user_...`.
        # So I need to define `updated_user` correctly.
        # In the original code, `updated_user` was defined AFTER `serializer.save()`.
        # But `old_personas` were fetched from `self.get_object()` BEFORE updates?
        # Actually in original code:
        # `old_personas = list(self.get_object().user_personas.all())` happens inside the `if persona_str` block,
        # which is BEFORE `serializer.save()`.
        # So `self.get_object()` refers to the user instance.
        
        updated_user = self.get_object() # This is the user instance
        
        if serializer.is_valid(raise_exception=True):
            if 'username' in self.request.data:
                new_username = serializer.validated_data.get('username')
                old_username = self.request.user.username
                # check if @ or . is included in username
                if '@' in new_username or '.' in new_username:
                    raise InvalidUsername()
                # check if username exceeds 20 letters
                if len(new_username) > 20:
                    raise LongUsername()
                # check if username exists
                if new_username and User.objects.filter(username=new_username).exclude(id=self.request.user.id).exists():
                    raise ExistingUsername()

            persona_str = self.request.data.get('persona') or self.request.data.get('user_personas')
            interest_str = self.request.data.get('interest') or self.request.data.get('user_interests') or self.request.data.get('user_interest')

            if persona_str is not None:
                # Legacy behavior: parse hashtags and replace ALL
                # This logic is for the 'user/me' endpoint which might send mixed content or just hashtags
                # Ideally we should keep the same behavior as before:
                # "parse_hashtags" -> set(personas)
                
                # Note: `update_user_personas_logic` has been changed to support the NEW API behavior (subset replacement).
                # The OLD `CurrentUserDetail` logic did: parse -> set.
                # If we want to preserve OLD behavior here, we should NOT use the new `update_user_personas_logic` directly 
                # if it does subset replacement.
                
                # Let's revert `CurrentUserDetail` to use the original full-replacement logic using the helpers.
                # Or create a `update_user_personas_full_replacement` helper.
                pass # See below
                
            # Wait, I need to provide the implementation in this block.
            # I will inline the old logic here to avoid confusion, using the helpers.
            
            if persona_str is not None:
                old_personas = list(updated_user.user_personas.all())
                persona_tags = parse_hashtags_or_list(persona_str)
                persona_instances = [get_or_create_normalized_tag(Persona, tag) for tag in persona_tags]
                updated_user.user_personas.set(persona_instances)
                
                # Update ArrayField if needed? 
                # Original code: `self.get_object().user_personas.set(persona_instances)`
                # It did NOT update `user.persona` (ArrayField) based on hashtags.
                # So we just do M2M update.
                
                # Orphan cleanup
                from account.models import PERSONA_CHOICES
                predefined_personas = {normalize_tag(val) for _, val in PERSONA_CHOICES}
                for p in old_personas:
                    if p not in persona_instances:
                        if normalize_tag(p.content) not in predefined_personas:
                            if p.users.count() == 0:
                                p.delete()

            if interest_str is not None:
                old_interests = list(updated_user.user_interests.all())
                interest_tags = parse_hashtags_or_list(interest_str)
                interest_instances = [get_or_create_normalized_tag(Interest, tag) for tag in interest_tags]
                updated_user.user_interests.set(interest_instances)

                # Orphan cleanup
                from account.models import INTEREST_CHOICES_BASE
                predefined_interests = {normalize_tag(val) for val in INTEREST_CHOICES_BASE}
                for i in old_interests:
                    if i not in interest_instances:
                        if normalize_tag(i.content) not in predefined_interests:
                            if i.users.count() == 0:
                                i.delete()

            noti_period_days = self.request.data.get('noti_period_days')
            if noti_period_days:
                # Check if it's a JSON string and parse it
                if isinstance(noti_period_days, str):
                    try:
                        noti_period_days = json.loads(noti_period_days)
                    except json.JSONDecodeError:
                        raise serializers.ValidationError("noti_period_days must be a valid JSON list.")
                try:
                    noti_period_days = [str(int(day)) for day in noti_period_days]
                except ValueError:
                    raise serializers.ValidationError({
                        "noti_period_days": ["noti_period_days must only contain integers between 0 and 6."]
                    })
            
                if any(int(day) not in range(0, 7) for day in noti_period_days):
                    raise serializers.ValidationError({
                        "noti_period_days": ["noti_period_days must only contain integers between 0 and 6."]
                    })
                if len(noti_period_days) != len(set(noti_period_days)):
                    raise serializers.ValidationError({
                        "noti_period_days": ["There are duplicate values in noti_period_days."]
                    })
                serializer.validated_data['noti_period_days'] = noti_period_days

            serializer.save()
            updated_user = self.get_object()

            # record username history
            # update notification redirect url when username changes
            if 'username' in self.request.data:
                if new_username != old_username and new_username and new_username not in updated_user.username_history:
                    updated_user.username_history.append(new_username)
                    updated_user.save()

                # "friend request recieved" notification
                friend_request_ct = get_friend_request_type()
                self.request.user.friendship_originated_notis.filter(
                    target_type=friend_request_ct
                ).update(
                    redirect_url=f"/users/{new_username}"
                )
                
                # "became friends" notification
                Notification = apps.get_model('notification', 'Notification')
                user_ct = ContentType.objects.get_for_model(User)
                notis_to_change = self.request.user.friendship_originated_notis.filter(
                    target_type=user_ct
                )
                notis_to_change.update(
                    redirect_url=f"/users/{new_username}"
                )


class CurrentUserInterestUpdate(generics.UpdateAPIView):
    serializer_class = UserInterestUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        return self.request.user

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user_interests = serializer.validated_data.get('user_interests')
        if user_interests is not None:
             update_user_interests_logic(self.get_object(), user_interests)

        return Response(status=status.HTTP_200_OK, data={"message": "Interests updated successfully"})


class CurrentUserPersonaUpdate(generics.UpdateAPIView):
    serializer_class = UserPersonaUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        return self.request.user

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user_personas = serializer.validated_data.get('user_personas')
        if user_personas is not None:
             update_user_personas_logic(self.get_object(), user_personas)

        return Response(status=status.HTTP_200_OK, data={"message": "Personas updated successfully"})


class CurrentUserDelete(generics.DestroyAPIView):
    serializer_class = CurrentUserSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        return self.request.user

    @transaction.atomic
    def perform_destroy(self, instance):
        # email cannot be null, so set it to a dummy value
        instance.email = f"{instance.username}@{instance.username}"
        instance.gender = None
        instance.ethnicity = None
        instance.date_of_birth = None
        instance.save()
        # user is soft-deleted, contents user created will be cascade-deleted
        instance.safe_delete()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(settings.SIMPLE_JWT['AUTH_COOKIE'])
        return response


class CurrentUserProfile(generics.RetrieveAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        user = self.request.user
        if user.is_authenticated:
            return user
        else:
            raise PermissionDenied("User is not authenticated")


class CurrentUserNoteList(generics.ListAPIView):
    queryset = Note.objects.all()
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user = self.request.user
        return Note.objects.filter(author=user).order_by('-created_at')
    

class DefaultCurrentUserNoteList(generics.ListAPIView):
    queryset = Note.objects.all()
    serializer_class = DefaultFriendNoteSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user = self.request.user
        return Note.objects.filter(author=user).order_by('-created_at')


class CurrentUserResponseList(generics.ListAPIView):
    queryset = _Response.objects.all()
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_serializer_class(self):
        from qna.serializers import ResponseSerializer
        return ResponseSerializer

    def get_queryset(self):
        user = self.request.user
        return _Response.objects.filter(author=user).order_by('-created_at')



class CurrentUserAllPostList(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_combined_items(self):
        user = self.request.user
        
        all_notes = Note.objects.filter(author=user).order_by('-created_at')
        notes = list(all_notes)

        all_responses = _Response.objects.filter(author=user).order_by('-created_at')
        responses = list(all_responses)

        combined = sorted(chain(notes, responses), key=lambda x: x.created_at, reverse=True)
        return combined

    def paginate_queryset(self, queryset):
        page = super().paginate_queryset(queryset)
        return page

    def list(self, request, *args, **kwargs):
        combined_items = self.get_combined_items()
        
        page = self.paginate_queryset(combined_items)
        objects_to_serialize = page if page is not None else combined_items
        
        serialized_data = []
        for obj in objects_to_serialize:
            if isinstance(obj, Note):
                serialized = NoteSerializer(obj, context=self.get_serializer_context()).data
                serialized['type'] = 'Note'
            elif isinstance(obj, _Response):
                serialized = ResponseSerializer(obj, context=self.get_serializer_context()).data
                serialized['type'] = 'Response'
            serialized_data.append(serialized)
            
        return self.get_paginated_response(serialized_data) if page is not None else Response(serialized_data)


class ReceivedResponseRequestPagination(PageNumberPagination):
    page_size = 10


class ReceivedResponseRequestList(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = GroupedResponseRequestSerializer

    def get(self, request, *args, **kwargs):
        user = request.user
        tz_now = timezone.now().astimezone(ZoneInfo(user.timezone))
        thirty_days_ago = tz_now - timedelta(days=30)

        response_requests = ResponseRequest.objects.filter(
            requestee=user,
            created_at__gte=thirty_days_ago
        ).select_related('question', 'requester')

        # unanswered only
        unanswered = []
        for rr in response_requests:
            has_response = rr.question.response_set.filter(author=user).exists()
            if not has_response:
                unanswered.append(rr)

        # group by question
        grouped_dict = {}
        for rr in unanswered:
            qid = rr.question.id
            if qid not in grouped_dict:
                grouped_dict[qid] = {
                    "question_id": qid,
                    "question_content": rr.question.content,
                    "requester_username_list": [],
                    "created_at": rr.created_at,
                    "id": rr.id,
                }
            else:
                # Keep the most recent created_at
                if rr.created_at > grouped_dict[qid]["created_at"]:
                    grouped_dict[qid]["created_at"] = rr.created_at
            grouped_dict[qid]["requester_username_list"].append(rr.requester.username)

        grouped_list = sorted(grouped_dict.values(), key=lambda x: x["created_at"], reverse=True)

        seven_days_ago = timezone.now() - timedelta(days=7)
        for group in grouped_dict.values():
            group["is_recent"] = group["created_at"] >= seven_days_ago

        # paginate manually
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(grouped_list, request, view=self)
        return paginator.get_paginated_response(page)


class FriendList(generics.ListAPIView):
    serializer_class = FriendListSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_serializer_context(self):
        context = super().get_serializer_context()
        query_type = self.request.query_params.get('type')
        if query_type == 'following':
            context['hide_check_in'] = True
        return context

    def get_queryset(self):
        user = self.request.user
        friends = user.connected_users

        query_type = self.request.query_params.get('type')

        if query_type == 'all' or query_type == 'friends':
            return friends.order_by('username')
        elif query_type == 'close_friends':
            close_friends_ids = Connection.objects.filter(
                Q(user1=user, user1_choice='close_friend') | 
                Q(user2=user, user2_choice='close_friend')
            ).values_list('user1_id', 'user2_id')
            
            target_ids = set()
            for u1_id, u2_id in close_friends_ids:
                if u1_id == user.id:
                    target_ids.add(u2_id)
                else:
                    target_ids.add(u1_id)
            
            return friends.filter(id__in=target_ids).order_by('username')
        elif query_type == 'following':
            return user.following.order_by('username')
        elif query_type == 'has_updates':
            friends = friends.exclude(hidden=True)
            friends_with_updates = [
                friend for friend in friends if not User.user_read(user, friend)
            ]
            return sorted(friends_with_updates, key=lambda x: x.most_recent_update(user), reverse=True)
        elif query_type == 'favorites':
            return user.favorites.all().order_by('username')
        else:
            raise Http404("Query parameter 'type' is invalid or not provided.")


class FriendListUpdate(generics.UpdateAPIView):
    serializer_class = UserFriendsUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_200_OK)


class FriendUpdateList(generics.ListAPIView):
    serializer_class = UserMinimalSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user = self.request.user
        friends = user.connected_users.exclude(hidden=True)
        
        friends_with_updates = [
            friend for friend in friends if not User.user_read(user, friend)
        ]
        
        return sorted(friends_with_updates, key=lambda x: x.most_recent_update(user), reverse=True)


class UserFavoriteAdd(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        friend_id = request.data.get('friend_id')
        if not friend_id:
            return Response({'error': 'Friend ID must be provided.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            friend_id = int(friend_id)
        except ValueError:
            return Response({'error': 'Invalid Friend ID.'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        if user.favorites.filter(id=friend_id).exists():
            return Response({'error': 'Friend is already in favorites.'}, status=status.HTTP_400_BAD_REQUEST)

        user_to_add = get_object_or_404(User, id=friend_id)
        if not user.is_connected(user_to_add):
            return Response({'error': 'User is not connected.'}, status=status.HTTP_400_BAD_REQUEST)

        user.favorites.add(user_to_add)

        return Response({'message': 'Friend added to favorites successfully.'}, status=status.HTTP_201_CREATED)


class UserFavoriteDestroy(generics.DestroyAPIView):
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_destroy(self, obj):
        self.request.user.favorites.remove(obj)


class UserHiddenAdd(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        friend_id = request.data.get('friend_id')
        if not friend_id:
            return Response({'error': 'Friend ID must be provided.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            friend_id = int(friend_id)
        except ValueError:
            return Response({'error': 'Invalid Friend ID.'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        if user.hidden.filter(id=friend_id).exists():
            return Response({'error': 'Friend is already in hidden.'}, status=status.HTTP_400_BAD_REQUEST)

        user_to_add = get_object_or_404(User, id=friend_id)
        if not user.is_connected(user_to_add):
            return Response({'error': 'User is not connected.'}, status=status.HTTP_400_BAD_REQUEST)

        if user.favorites.filter(id=friend_id).exists():
            user.favorites.remove(user_to_add)

        user.hidden.add(user_to_add)

        return Response({'message': 'Friend added to hidden successfully.'}, status=status.HTTP_201_CREATED)


class UserHiddenDestroy(generics.DestroyAPIView):
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_destroy(self, obj):
        self.request.user.hidden.remove(obj)


class ConnectionChoiceUpdate(generics.UpdateAPIView):
    queryset = Connection.objects.all()
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        try:
            connected_user = User.objects.get(id=self.kwargs['pk'])
            connection = Connection.get_connection_between(self.request.user, connected_user)
        except User.DoesNotExist:
            raise Http404("The specified connected user does not exist.")

        if not connection:
            raise Http404("No connection exists between the current user and the specified friend.")

        return connection
    
    def patch(self, request, *args, **kwargs):
        connection = self.get_object()
        new_choice = request.data.get('choice')
        update_past_posts = request.data.get('update_past_posts', False)
        
        if new_choice not in ['friend', 'close_friend']:
            return Response({'error': 'Invalid choice'}, status=400)
        
        # Check limits
        user = request.user
        if new_choice == 'close_friend':
            if user.close_friends.count() >= 15:
                return Response({'error': 'You can only have up to 15 close friends.'}, status=400)
            
        connection.update_friendship_level(request.user, new_choice, update_past_posts)
        return Response({'status': 'Friendship level updated'})


class FriendFriendList(generics.ListAPIView):
    serializer_class = FriendFriendListSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        username = self.kwargs.get('username')
        user = User.objects.filter(username=username).first()
        if not user:
            return User.objects.none()
        if not self.request.user == user and not self.request.user.is_connected(user):
            raise PermissionDenied("You do not have permission to view this user's friends.")

        return user.connected_users.order_by(Lower('username'))


class UserFriendDestroy(generics.DestroyAPIView):
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_destroy(self, obj):
        user = self.request.user

        if not user.is_connected(obj):
            raise ValidationError({'error': 'No connection exists between these users.'})

        connection = Connection.get_connection_between(user, obj)
        connection.delete()


class UserFriendRequest(generics.ListCreateAPIView):
    queryset = FriendRequest.objects.all()
    serializer_class = UserFriendRequestCreateSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        return FriendRequest.objects.filter(requestee=self.request.user).filter(accepted__isnull=True)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["default_api"] = False
        return context

    @transaction.atomic
    def perform_create(self, serializer):
        if int(self.request.data.get('requester_id')) != int(self.request.user.id):
            raise PermissionDenied("The requester must be yourself.")
        try:
            requester_update_past_posts = self.request.data.get('requester_update_past_posts', False)
            serializer.save(accepted=None, requester_update_past_posts=requester_update_past_posts)
        except serializers.ValidationError as e:
            if 'error' in e.detail and "different versions" in str(e.detail['error']):
                raise PermissionDenied("Users belong to different groups, so a friend request cannot be sent.")
            raise e

class UserFriendRequestDefault(generics.CreateAPIView):
    queryset = FriendRequest.objects.all()
    serializer_class = UserFriendRequestCreateSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["default_api"] = True
        return context

    @transaction.atomic
    def perform_create(self, serializer):
        if int(self.request.data.get('requester_id')) != int(self.request.user.id):
            raise PermissionDenied("The requester must be yourself.")
        serializer.save(accepted=None, requester_choice='friend')


class UserSentFriendRequestList(generics.ListAPIView):
    queryset = FriendRequest.objects.all()
    serializer_class = UserFriendRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        return FriendRequest.objects.filter(requester=self.request.user).filter(
            Q(accepted__isnull=True) | Q(accepted=False)
        )


class UserFriendRequestDestroy(generics.DestroyAPIView):
    serializer_class = UserFriendRequestCreateSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        # since the requester is the authenticated user, no further permission checking unnecessary
        return FriendRequest.objects.get(requester_id=self.request.user.id,
                                         requestee_id=self.kwargs.get('pk'))

    @transaction.atomic
    def perform_destroy(self, obj):
        obj.delete(force_policy=SOFT_DELETE_CASCADE)


class BaseUserFriendRequestUpdate(generics.UpdateAPIView):
    serializer_class = UserFriendRequestUpdateSerializer
    permission_classes = [IsAuthenticated]
    default_api = False

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        return FriendRequest.objects.get(requester_id=self.kwargs.get('pk'),
                                         requestee_id=self.request.user.id)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["default_api"] = self.default_api
        return context

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        # catch version validation before update is processed
        if instance.requester.current_ver != instance.requestee.current_ver:
            raise ValidationError({
                "error": "Cannot accept friend requests from users using different versions"
            })

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)  # Check `accepted` field
        
        # Check limits before performing update
        if serializer.validated_data.get('accepted'):
            requestee = self.get_object().requestee
            # checking friend limit
            if requestee.friends.count() >= 35:
                 raise ValidationError({'error': 'You can only have up to 35 friends.'})
            
            # checking close friend limit
            if self.default_api: # default api accepts as friend
                 pass
            else:
                choice = request.data.get('requestee_choice')
                if choice == 'close_friend':
                    if requestee.close_friends.count() >= 15:
                        raise ValidationError({'error': 'You can only have up to 15 close friends.'})

        self.perform_update(serializer)
        return Response(serializer.data)

    @transaction.atomic
    def perform_update(self, serializer):
        friend_request = self.get_object()
        requester = User.objects.get(id=friend_request.requester_id)
        requestee = User.objects.get(id=friend_request.requestee_id)

        if self.default_api:
            serializer.save(requestee_choice='friend')
        else:
            serializer.save()

        send_users = []
        if len(requester.connected_user_ids) == 1:
            send_users.append(requester)
        if len(requestee.connected_user_ids) == 1:
            send_users.append(requestee)

        for user in send_users:
            from custom_fcm.models import CustomFCMDevice
            has_enabled_notifications = CustomFCMDevice.objects.filter(user=user, active=True).exists()
            if not has_enabled_notifications:
                Notification = apps.get_model('notification', 'Notification')
                admin = User.objects.filter(is_superuser=True).first()

                noti = Notification.objects.create(
                    user=user,
                    target=admin,
                    origin=admin,
                    message_ko=f"{user.username}님, 답변 작성을 놓치고 싶지 않다면 알림 설정을 해보세요!",
                    message_en=f"{user.username}, if you don't want to miss writing daily responses, try setting up notifications!",
                    redirect_url='/settings'
                )
                NotificationActor.objects.create(user=admin, notification=noti)


class UserFriendRequestUpdate(BaseUserFriendRequestUpdate):
    default_api = False


class UserFriendRequestUpdateDefault(BaseUserFriendRequestUpdate):
    default_api = True


class UserFollowRequestListCreate(generics.ListCreateAPIView):
    queryset = FollowRequest.objects.all()
    serializer_class = UserFollowRequestCreateSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        # List pending received follow requests
        return FollowRequest.objects.filter(requestee=self.request.user).filter(accepted__isnull=True)

    @transaction.atomic
    def perform_create(self, serializer):
        if int(self.request.data.get('requester_id')) != int(self.request.user.id):
            raise PermissionDenied("The requester must be yourself.")
        serializer.save(accepted=None)


class UserSentFollowRequestList(generics.ListAPIView):
    queryset = FollowRequest.objects.all()
    serializer_class = UserFollowRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        # List pending sent follow requests (not accepted, not declined)
        return FollowRequest.objects.filter(requester=self.request.user).filter(accepted__isnull=True)


class UserFollowRequestDestroy(generics.DestroyAPIView):
    serializer_class = UserFollowRequestCreateSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        return FollowRequest.objects.get(requester_id=self.request.user.id,
                                         requestee_id=self.kwargs.get('pk'))

    @transaction.atomic
    def perform_destroy(self, obj):
        obj.delete(force_policy=SOFT_DELETE_CASCADE)


class UserFollowRequestUpdate(generics.UpdateAPIView):
    serializer_class = UserFollowRequestUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        return FollowRequest.objects.get(requester_id=self.kwargs.get('pk'),
                                         requestee_id=self.request.user.id)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        if serializer.validated_data.get('accepted'):
             # Check follower limit
             if request.user.followers.count() >= 100:
                 raise ValidationError({'error': 'You can only have up to 100 followers.'})

        self.perform_update(serializer)
        return Response(serializer.data)

    @transaction.atomic
    def perform_update(self, serializer):
        serializer.save()


class UserRecommendedFriendsList(generics.ListAPIView):
    serializer_class = UserMinimumSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user_id = self.request.user.id
        user = get_object_or_404(User, id=user_id)
        user_friends = user.connected_users

        user_friend_ids = user_friends.values_list('id', flat=True)
        user_block_rec_ids = user.block_recs.all().values_list('blocked_user', flat=True)
        sent_friend_request_ids = FriendRequest.objects.filter(requester=user).values_list('requestee__id', flat=True)
        received_friend_request_ids = FriendRequest.objects.filter(requestee=user).values_list('requester__id', flat=True)

        mutual_friends_count_dict = {}
        for friend in user_friends:
            potential_friends = friend.connected_users.filter(current_ver=user.current_ver) \
                .exclude(id__in=user_friend_ids) \
                .exclude(id=user_id).exclude(id__in=user_block_rec_ids) \
                .exclude(id__in=sent_friend_request_ids) \
                .exclude(id__in=received_friend_request_ids) \
                .exclude(is_superuser=True)

            for potential_friend in potential_friends:
                if potential_friend.id not in mutual_friends_count_dict:
                    mutual_friends_count_dict[potential_friend.id] = 1
                else:
                    mutual_friends_count_dict[potential_friend.id] += 1

        # Sort by number of mutual friends
        sorted_friends = sorted(mutual_friends_count_dict.items(), key=lambda x: x[1], reverse=True)[:25]
        sorted_friend_ids = [friend_id for friend_id, _ in sorted_friends]

        # Add 10 random users
        potential_random_users = User.objects.filter(current_ver=user.current_ver) \
            .exclude(id=user_id) \
            .exclude(id__in=user_friend_ids) \
            .exclude(id__in=user_block_rec_ids) \
            .exclude(id__in=sent_friend_request_ids) \
            .exclude(id__in=received_friend_request_ids) \
            .exclude(is_superuser=True) \
            .exclude(id__in=sorted_friend_ids)

        random_user_ids = list(potential_random_users.order_by("?").values_list('id', flat=True)[:10])

        # Get invited_from user and check conditions
        invited_from = user.invited_from
        if invited_from and \
            invited_from.id not in user_friend_ids and \
            invited_from.id not in user_block_rec_ids and \
            invited_from.id not in sent_friend_request_ids and \
            invited_from.id not in received_friend_request_ids and \
            not invited_from.is_superuser and \
            invited_from.id not in sorted_friend_ids:

            sorted_friend_ids = [invited_from.id] + sorted_friend_ids

        final_user_ids = sorted_friend_ids + random_user_ids

        recommended_friends = User.objects.filter(id__in=final_user_ids) \
            .order_by(Case(*[When(id=id_, then=pos) for pos, id_ in enumerate(final_user_ids)], default=0))

        return recommended_friends

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class BlockRecCreate(generics.CreateAPIView):
    queryset = BlockRec.objects.all()
    serializer_class = BlockRecSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        try:
            serializer.save(user=self.request.user,
                            blocked_user_id=self.request.data['blocked_user_id'])
        except IntegrityError:
            pass


class UserMarkAllNotesAsRead(APIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def patch(self, request):
        username = request.data.get('username')
        if not username:
            return Response({'error': 'Username is required.'}, status=status.HTTP_400_BAD_REQUEST)

        User = get_user_model()
        try:
            if username.isdigit():
                target_user = get_object_or_404(User, pk=username)
            else:
                target_user = get_object_or_404(User, username=username)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        notes = Note.objects.filter(author=target_user).exclude(readers=request.user).exclude(author__is_superuser=True)
        for note in notes:
            note.readers.add(request.user)

        return Response({'success': 'All content marked as read successfully'}, status=status.HTTP_200_OK)


class UserMarkAllResponsesAsRead(APIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def patch(self, request):
        username = request.data.get('username')
        if not username:
            return Response({'error': 'Username is required.'}, status=status.HTTP_400_BAD_REQUEST)

        User = get_user_model()
        try:
            if username.isdigit():
                target_user = get_object_or_404(User, pk=username)
            else:
                target_user = get_object_or_404(User, username=username)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        responses = _Response.objects.filter(author=target_user).exclude(readers=request.user)
        for response in responses:
            response.readers.add(request.user)

        return Response({'success': 'All content marked as read successfully'}, status=status.HTTP_200_OK)


class SubscribeUserContent(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        friend_id = request.data.get('user_id')
        user = request.user
        user_to_subscribe = get_object_or_404(User, id=friend_id)
        content_type_str = request.data.get('content_type')  # 'note' or 'response'

        content_type = get_generic_relation_type(content_type_str)
        if not content_type:
            return Response({'error': 'Invalid content type.'}, status=status.HTTP_400_BAD_REQUEST)

        if Subscription.objects.filter(subscriber=request.user, subscribed_to=user_to_subscribe, content_type=content_type).exists():
            return Response({'error': f'You are already subscribed to this user\'s {content_type_str}.'}, status=status.HTTP_400_BAD_REQUEST)

        if not user.is_connected(user_to_subscribe):
            return Response({'error': 'User is not your friend.'}, status=status.HTTP_400_BAD_REQUEST)

        Subscription.objects.create(
            subscriber=user,
            subscribed_to=user_to_subscribe,
            content_type=content_type
        )

        return Response({'message': f'Subscribed to {user_to_subscribe.username}\'s {content_type_str} successfully.'}, status=status.HTTP_201_CREATED)


class UnsubscribeUserContent(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def delete(self, request, *args, **kwargs):
        subscription_id = kwargs.get('pk')
        subscription = get_object_or_404(Subscription, id=subscription_id, subscriber=request.user)

        subscription.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)


class FriendFeed(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user = self.request.user

        connected_user_ids = user.connected_user_ids
        blocked_user_ids = user.user_report_blocked_ids

        notes = Note.objects.filter(
            author_id__in=connected_user_ids
        ).exclude(author_id__in=blocked_user_ids).exclude(author__is_superuser=True).select_related('author')
        note_list = list(filter(lambda note: note.is_audience(user), notes))

        return Note.objects.filter(id__in=[note.id for note in note_list]).order_by('-created_at')

    def paginate_queryset(self, queryset):
        page = super().paginate_queryset(queryset)
        return page

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        # freeze notes before marking them as read
        note_ids = queryset.values_list("id", flat=True)
        notes_before_update = list(Note.objects.filter(id__in=note_ids).order_by('-created_at'))

        page = self.paginate_queryset(notes_before_update)
        if page is not None:
            serialized_data = DefaultFriendNoteSerializer(page, many=True, context=self.get_serializer_context()).data
        else:
            serialized_data = DefaultFriendNoteSerializer(notes_before_update, many=True, context=self.get_serializer_context()).data

        # mark all notes as read
        unread_note_ids = queryset.exclude(readers=request.user).values_list("id", flat=True)
        if unread_note_ids:
            request.user.read_notes.add(*unread_note_ids)

class FullFriendFeed(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_combined_feed_items(self):
        user = self.request.user
        connected_user_ids = user.connected_user_ids
        blocked_user_ids = user.user_report_blocked_ids

        # 1. Notes
        notes = Note.objects.filter(
            author_id__in=connected_user_ids
        ).exclude(author_id__in=blocked_user_ids).exclude(author__is_superuser=True).select_related('author')
        notes = [n for n in notes if n.is_audience(user)]

        # 2. Responses
        responses = _Response.objects.filter(
            author_id__in=connected_user_ids
        ).exclude(author_id__in=blocked_user_ids).select_related('author', 'question')
        responses = [r for r in responses if r.is_audience(user)]

        combined = sorted(chain(notes, responses), key=lambda x: x.created_at, reverse=True)
        return notes, responses, combined

    def paginate_queryset(self, queryset):
        page = super().paginate_queryset(queryset)
        return page

    def list(self, request, *args, **kwargs):
        user = request.user
        notes, responses, combined_feed_items = self.get_combined_feed_items()

        # freeze notes before marking them as read
        frozen_items = list(combined_feed_items)

        page = self.paginate_queryset(frozen_items)
        objects_to_serialize = page if page is not None else frozen_items

        serialized_data = []
        for obj in objects_to_serialize:
            if isinstance(obj, Note):
                serialized = NoteSerializer(obj, context=self.get_serializer_context()).data
            elif isinstance(obj, _Response):
                serialized = ResponseSerializer(obj, context=self.get_serializer_context()).data
            serialized_data.append(serialized)

        # mark all notes as read
        unread_note_ids = [n.id for n in notes if user not in n.readers.all()]
        if unread_note_ids:
            user.read_notes.add(*unread_note_ids)

        unread_response_ids = [r.id for r in responses if user not in r.readers.all()]
        if unread_response_ids:
            user.read_responses.add(*unread_response_ids)

        return self.get_paginated_response(serialized_data) if page is not None else Response(serialized_data)


class DiscoverFeedView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user = self.request.user
        type_param = self.request.query_params.get('type', 'all')

        now = timezone.now()
        last_feed = DiscoverFeed.objects.filter(user=user).order_by('-created_at').first()

        # Check if date has changed in user's timezone
        user_timezone = getattr(user, 'timezone', 'UTC')
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(user_timezone)
        except:
            tz = timezone.get_current_timezone()

        now_local = now.astimezone(tz)
        
        needs_new_feed = False
        if not last_feed:
            needs_new_feed = True
        else:
            last_feed_local = last_feed.created_at.astimezone(tz)
            if now_local.date() > last_feed_local.date():
                needs_new_feed = True

        if needs_new_feed:
            self.generate_new_feed(user)
            last_feed = DiscoverFeed.objects.filter(user=user).order_by('-created_at').first()

        if not last_feed:
            return DiscoverFeed.objects.none()

        # Get only the latest batch (items with the same created_at as the latest one)
        latest_timestamp = last_feed.created_at
        queryset = DiscoverFeed.objects.filter(
            user=user, 
            created_at=latest_timestamp
        ).select_related('response', 'response__author', 'response__question')

        # Filter by type if not 'all'
        type_param = type_param.lower().rstrip('/')
        if type_param == 'following':
            queryset = queryset.filter(category='following')
        elif type_param == 'mutual_friends':
            queryset = queryset.filter(category='mutual_friends')
        elif type_param == 'mutual_traits':
            queryset = queryset.filter(category='mutual_traits')
        elif type_param == 'anonymous':
            queryset = queryset.filter(category='anonymous')
        elif type_param == 'random':
            queryset = queryset.filter(category='random')

        # If 'all', we might want a specific mixed ordering
        if type_param == 'all':
            # We can use the order they were added or a custom sort_order field if we add one.
            # For now, let's just make sure it's consistent.
            queryset = queryset.order_by('id') # Or some other stable order
        else:
            queryset = queryset.order_by('-id')

        return queryset

    @transaction.atomic
    def generate_new_feed(self, user):        
        batch_time = timezone.now()

        friend_ids = set(user.friend_ids + user.close_friend_ids)
        blocked_ids = set(user.user_report_blocked_ids)
        exclude_ids = friend_ids | blocked_ids | {user.id}

        feed_items = []  # List of (response, category)

        # 1. Posts from people I follow (who are not friends) - Include ALL
        following_ids = set(user.following.values_list('id', flat=True))
        follow_but_not_friend_ids = following_ids - friend_ids - blocked_ids - {user.id}
        
        following_responses = _Response.objects.filter(
            author_id__in=follow_but_not_friend_ids
        ).exclude(readers=user).order_by('-created_at')
        
        for r in following_responses:
            if r.is_audience(user):
                feed_items.append((r, 'following'))

        # 2, 3, 4. Collect candidates for Mutual Friends, Mutual Traits, and Strangers
        
        # Mutual Friends Candidates
        user_friends = user.connected_users
        user_friend_ids = set(user_friends.values_list('id', flat=True))
        mutual_friend_potential_ids = set()
        for friend in user_friends:
            friend_of_friend_ids = set(friend.connected_users.values_list('id', flat=True))
            mutual_friend_potential_ids.update(friend_of_friend_ids)
        mf_ids = mutual_friend_potential_ids - user_friend_ids - following_ids - exclude_ids
        mf_candidates = list(_Response.objects.filter(author_id__in=mf_ids).exclude(readers=user).order_by('-created_at')[:20])

        # Mutual Traits Candidates
        user_interests = set(user.user_interests.values_list('id', flat=True))
        user_personas = set(user.user_personas.values_list('id', flat=True))
        trait_ids = set(User.objects.filter(
            Q(user_interests__id__in=user_interests) | Q(user_personas__id__in=user_personas)
        ).exclude(id__in=exclude_ids | following_ids).values_list('id', flat=True))
        trait_candidates = list(_Response.objects.filter(author_id__in=trait_ids).exclude(readers=user).order_by('-created_at')[:20])

        # Strangers (No Mutual) Candidates
        stranger_ids = set(User.objects.exclude(
            id__in=exclude_ids | following_ids | mutual_friend_potential_ids | trait_ids
        ).exclude(is_superuser=True).values_list('id', flat=True))
        stranger_candidates = list(_Response.objects.filter(author_id__in=stranger_ids).exclude(readers=user).order_by('-created_at')[:20])

        category_candidates = [
            (mf_candidates, 'mutual_friends'),
            (trait_candidates, 'mutual_traits'),
            (stranger_candidates, 'anonymous')
        ]
        
        existing_response_ids = {item[0].id for item in feed_items}
        
        # Step 1: Ensure at least 1 from each category (if exists)
        for candidates, category_name in category_candidates:
            while candidates:
                cand = candidates.pop(0)
                if cand.id not in existing_response_ids and cand.is_audience(user):
                    feed_items.append((cand, category_name))
                    existing_response_ids.add(cand.id)
                    break

        # Step 2: If still less than 10, fill more in round-robin fashion
        while len(feed_items) < 10:
            added_in_round = False
            for candidates, category_name in category_candidates:
                if len(feed_items) >= 10:
                    break
                
                while candidates:
                    cand = candidates.pop(0)
                    if cand.id not in existing_response_ids and cand.is_audience(user):
                        feed_items.append((cand, category_name))
                        existing_response_ids.add(cand.id)
                        added_in_round = True
                        break
            
            if not added_in_round:
                break

        # 5. Fallback: Fill up to 10 random posts (from any non-friends) if still not enough
        if len(feed_items) < 10:
            existing_response_ids = [item[0].id for item in feed_items]
            # Exclude friends and blocked, and already added
            random_potentials = _Response.objects.exclude(
                author_id__in=exclude_ids
            ).exclude(id__in=existing_response_ids).exclude(readers=user).order_by('-created_at')[:50]
            
            import random
            random_responses = list(random_potentials)
            random.shuffle(random_responses)
            
            for r in random_responses:
                if len(feed_items) >= 10:
                    break
                if r.is_audience(user):
                    feed_items.append((r, 'random'))

        # Mix feed items to ensure variety in 'all' view
        import random
        random.shuffle(feed_items)

        # Save to DiscoverFeed
        for i, (response, category) in enumerate(feed_items):
            DiscoverFeed.objects.create(
                user=user, 
                response=response, 
                category=category, 
                created_at=batch_time,
                sort_order=i
            )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        # Serialize data
        if page is not None:
            responses = [item.response for item in page]
            request.user.read_responses.add(*responses)
            serializer = ResponseSerializer(responses, many=True, context={'request': request})
            serialized_data = serializer.data
        else:
            responses = [item.response for item in queryset]
            request.user.read_responses.add(*responses)
            serializer = ResponseSerializer(responses, many=True, context={'request': request})
            serialized_data = serializer.data

        # --- Injection Logic ---
        results = []
        for item in serialized_data:
            results.append({
                "type": "Response",
                "body": item
            })

        # Inject Daily Question
        from qna.models import Question
        
        daily_questions_qs = Question.objects.daily_questions(request.user)
        daily_question = daily_questions_qs.order_by('?').first()

        if daily_question:
            q_data = DailyQuestionSerializer(daily_question).data
            q_card = {
                "type": "Question",
                "body": q_data
            }
            # Insert at 2nd (idx 1) or 3rd (idx 2)
            # If empty, just append.
            if not results:
                results.append(q_card)
            else:
                q_idx = random.choice([1, 2])
                results.insert(min(len(results), q_idx), q_card)
        
        original_count = len(serialized_data)

        # Inject Interest
        if original_count >= 5:
            # Insert at 6th (idx 5) or 7th (idx 6)
            i_idx = random.choice([5, 6])
            
            # Fetch user's selected interests
            user_interest_contents = set(request.user.user_interests.values_list('content', flat=True))
            
            interest_list = []
            for interest in INTEREST_CHOICES_BASE:
                interest_list.append({
                    "content": interest,
                    "is_selected": interest in user_interest_contents
                })

            interest_card = {
                "type": "Interest",
                "body": {
                    "list": interest_list
                }
            }
            results.insert(min(len(results), i_idx), interest_card)

        # Inject Persona
        if original_count >= 9:
            # Insert at 12th (idx 11) or 13th (idx 12)
            p_idx = random.choice([11, 12])
            
            # Fetch user's selected personas
            user_persona_contents = set(request.user.user_personas.values_list('content', flat=True))

            persona_list = []
            for key, label in PERSONA_CHOICES:
                # Format label to match DB content (remove spaces and #)
                formatted_content = label.replace(' ', '').replace('#', '')
                persona_list.append({
                    "key": key, 
                    "label": label,
                    "is_selected": formatted_content in user_persona_contents
                })

            persona_card = {
                "type": "Persona",
                "body": {
                    "list": persona_list
                }
            }
            results.insert(min(len(results), p_idx), persona_card)

        if page is not None:
             return self.get_paginated_response(results)
        
        # If not paginated, return wrapped structure
        return Response({"results": results})



class StartSession(generics.CreateAPIView):
    queryset = AppSession.objects.all()
    serializer_class = AppSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        while True:
            session_id = str(uuid.uuid4())
            
            # Clean the session key using the utility function
            session_id = clean_session_key(session_id)
                
            try:
                session = AppSession.objects.create(
                    user=request.user,
                    session_id=session_id,
                    start_time=timezone.now()
                )
                return Response(
                    {"message": "Session started", "session_id": session.session_id, "start_time": session.start_time},
                    status=status.HTTP_201_CREATED
                )
            except IntegrityError:
                continue


class EndSession(generics.UpdateAPIView):
    queryset = AppSession.objects.all()
    serializer_class = AppSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def update(self, request, *args, **kwargs):
        session = self.get_object()

        if session.end_time is not None:
            return Response({"error": "Session already ended"}, status=status.HTTP_400_BAD_REQUEST)

        session.end_time = timezone.now()
        session.save()
        return Response({"message": "Session ended"}, status=status.HTTP_200_OK)

    def get_object(self):
        session_id = self.request.data.get("session_id")

        return get_object_or_404(AppSession, session_id=session_id, user=self.request.user)


class TouchSession(generics.UpdateAPIView):
    queryset = AppSession.objects.all()
    serializer_class = AppSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def update(self, request, *args, **kwargs):
        session = self.get_object()

        if session.end_time is not None:
            return Response({"error": "Session already ended"}, status=status.HTTP_400_BAD_REQUEST)

        session.last_touch_time = timezone.now()
        session.save()
        return Response({"message": "Touch received"}, status=status.HTTP_200_OK)
    
    def get_object(self):
        session_id = self.request.data.get("session_id")
        
        if not session_id:
            raise Http404("No session_id provided")
            
        # Clean the session key using the utility function
        session_id = clean_session_key(session_id)
        
        return get_object_or_404(AppSession, session_id=session_id, user=self.request.user)

class UserFollowerList(generics.ListAPIView):
    serializer_class = UserMinimalSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        return self.request.user.followers


class UserFollowingList(generics.ListAPIView):
    serializer_class = UserMinimalSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        return self.request.user.following

class InterestSearch(generics.ListAPIView):
    serializer_class = InterestSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        query = self.request.GET.get('q') or self.request.GET.get('query', '')
        if not query:
            return Interest.objects.none()

        if query.startswith('#'):
            query = query[1:]
        
        # 1. Startswith matches
        startswith_qs = Interest.objects.filter(content__istartswith=query)
        startswith_count = startswith_qs.count()
        
        if startswith_count >= 10:
            return startswith_qs[:10]
        
        # 2. Contains matches (fill up to 10)
        needed = 10 - startswith_count
        # Exclude IDs from startswith to avoid duplicates
        sw_ids = list(startswith_qs[:10].values_list('id', flat=True))  # Evaluate startswith_qs
        
        contains_qs = Interest.objects.filter(content__icontains=query).exclude(id__in=sw_ids)
        ct_ids = list(contains_qs[:needed].values_list('id', flat=True))
        
        all_ids = sw_ids + ct_ids
        
        if not all_ids:
            return Interest.objects.none()
            
        cases = [When(id=pk, then=Value(i)) for i, pk in enumerate(all_ids)]
        qs = Interest.objects.filter(id__in=all_ids).annotate(
            search_rank=Case(*cases, output_field=IntegerField())
        ).order_by('search_rank')
        
        return qs


class PersonaSearch(generics.ListAPIView):
    serializer_class = PersonaSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        query = self.request.GET.get('q') or self.request.GET.get('query', '')
        if not query:
            return Persona.objects.none()

        if query.startswith('#'):
            query = query[1:]
        
        # 1. Startswith matches
        startswith_qs = Persona.objects.filter(content__istartswith=query)
        startswith_count = startswith_qs.count()
        
        if startswith_count >= 10:
            return startswith_qs[:10]
        
        # 2. Contains matches (fill up to 10)
        needed = 10 - startswith_count
        sw_ids = list(startswith_qs[:10].values_list('id', flat=True))
        
        contains_qs = Persona.objects.filter(content__icontains=query).exclude(id__in=sw_ids)
        ct_ids = list(contains_qs[:needed].values_list('id', flat=True))
        
        all_ids = sw_ids + ct_ids
        
        if not all_ids:
            return Persona.objects.none()
            
        cases = [When(id=pk, then=Value(i)) for i, pk in enumerate(all_ids)]
        qs = Persona.objects.filter(id__in=all_ids).annotate(
            search_rank=Case(*cases, output_field=IntegerField())
        ).order_by('search_rank')
        
        return qs
        return qs


class InterestRecommendation(generics.ListAPIView):
    serializer_class = InterestSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        return Interest.objects.annotate(user_count=Count('users')).order_by('-user_count')[:15]


class PersonaRecommendation(generics.ListAPIView):
    serializer_class = PersonaSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        return Persona.objects.annotate(user_count=Count('users')).order_by('-user_count')[:15]
