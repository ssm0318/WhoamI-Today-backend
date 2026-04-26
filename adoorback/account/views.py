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
from .models import Subscription, Connection, AppSession, DiscoverFeed, DiscoverFeedMusic, Persona, Interest
from custom_fcm.models import CustomFCMDevice
from account.models import FriendRequest, BlockRec, CustomChip
from account.serializers import (CurrentUserSerializer, CurrentUserSignupSerializer, \
                                 UserFriendRequestCreateSerializer, UserFriendRequestUpdateSerializer, \
                                 UserFriendshipStatusSerializer, \
                                 UserEmailSerializer, UserUsernameSerializer, UserBirthDateSerializer, \
                                 UserInviterEmailBirthDateSerializer, FriendListSerializer, \
                                 UserFriendsUpdateSerializer, UserMinimumSerializer, BlockRecSerializer, \
                                 UserFriendRequestSerializer, UserPasswordSerializer, UserProfileSerializer, \
                                 AppSessionSerializer, FriendFriendListSerializer, \
                                 UserMinimalSerializer, \
                                 UserInterestUpdateSerializer, UserPersonaUpdateSerializer, \
                                 InterestSerializer, PersonaSerializer, viewer_sees_check_in_component,
                                 RECENT_POST_WINDOW)
from account.view_as import apply_profile_view_as, parse_view_as, resolve_public_proxy_viewer, resolve_shadow_viewer
from adoorback.utils.content_types import get_generic_relation_type, get_friend_request_type
from adoorback.utils.exceptions import ExistingUsername, LongUsername, InvalidUsername, ExistingEmail, InvalidEmail, \
    NoUsername, WrongPassword, ExistingUsername, InvalidInviterEmail
from adoorback.utils.validators import adoor_exception_handler
from note.models import Note
from note.serializers import NoteSerializer
from notification.models import NotificationActor
from qna.models import ResponseRequest
from qna.models import Question, Response as _Response
from qna.serializers import ResponseSerializer, DailyQuestionSerializer
from qna.serializers import GroupedResponseRequestSerializer, ResponseSerializer
from account.models import CHIP_CATEGORY_CHOICES, CHIP_CATEGORY_DESCRIPTIONS, CHIPS_BY_CATEGORY, ALL_CHIP_NAMES
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
    # Try hashtag format first
    tags = re.findall(r'#([^\s#]+)', data)
    if tags:
        return tags
    # Fallback: space-separated strings without #
    return [t.strip() for t in data.split() if t.strip()]

def get_or_create_normalized_tag(model, raw_tag, category=None):
    normalized_input = normalize_tag(raw_tag)
    # Fetch all in-memory for matching (optimized for small-medium scale)
    qs = model.objects.all_with_deleted()
    if category:
        qs = qs.filter(category=category)
    all_instances = list(qs)
    for instance in all_instances:
        if normalize_tag(instance.content) == normalized_input:
            if instance.deleted:
                instance.undelete()
            return instance
    # Not found, create new PascalCase version
    pascal_content = ''.join(word.capitalize() for word in re.split(r'[-_]', raw_tag))
    kwargs = {'content': pascal_content}
    if category:
        kwargs['category'] = category
    return model.objects.create(**kwargs)

def update_user_personas_logic(user, persona_keys):
    # This function now expects a list of KEYS from PERSONA_CHOICES

    from account.models import PERSONA_CHOICES
    from django.utils import timezone

    # 1. Update ArrayField (stores keys) and timestamp
    user.persona = persona_keys
    user.personas_updated_at = timezone.now()
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
    """Update user interests. Accepts flat list of labels or dict of {category: [labels]}."""
    from django.utils import timezone

    user.interests_updated_at = timezone.now()
    user.save()

    # If it's a dict (chips_by_category format), handle per-category
    if isinstance(interest_labels, dict):
        all_new_interests = []
        for category, labels in interest_labels.items():
            for label in labels:
                interest = get_or_create_normalized_tag(Interest, label, category=category)
                all_new_interests.append(interest)
        current_interests = list(user.user_interests.all())
        user.user_interests.set(all_new_interests)
        # Orphan cleanup
        removed = [i for i in current_interests if i not in all_new_interests]
        for i in removed:
            if i.users.count() == 0:
                i.delete()
        return

    # Flat list fallback (backward compatible)
    from account.models import ALL_CHIP_NAMES
    all_choice_interests_normalized = {normalize_tag(label) for label in ALL_CHIP_NAMES}
    current_interests = list(user.user_interests.all())
    custom_interests = [i for i in current_interests if normalize_tag(i.content) not in all_choice_interests_normalized]
    new_choice_interests = [get_or_create_normalized_tag(Interest, label) for label in interest_labels]
    final_interest_set = custom_interests + new_choice_interests
    user.user_interests.set(final_interest_set)
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

    def post(self, request):
        user = request.user
        registration_id = request.data.get('registration_id')

        if registration_id and user.is_authenticated:
            CustomFCMDevice.objects.filter(
                user=user,
                registration_id=registration_id,
            ).update(active=False)

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
        friend_ids = list(User.objects.filter(
            id__in=user.connected_user_ids, current_ver=user.current_ver
        ).values_list('id', flat=True))
        user_block_rec_ids = user.block_recs.all().values_list('blocked_user', flat=True)

        qs = User.objects.none()
        if query:
            # username starts with query
            start_users = User.objects.filter(username__startswith=query, is_superuser=False, current_ver=user.current_ver) \
                .order_by('username').exclude(id=user_id).exclude(id__in=user_block_rec_ids)
            friend_start_ids = list(start_users.filter(id__in=friend_ids).values_list('id', flat=True))
            nonfriend_start_ids = list(start_users.exclude(id__in=friend_ids).values_list('id', flat=True))

            # username contains query
            contain_users = User.objects.filter(username__icontains=query, is_superuser=False, current_ver=user.current_ver) \
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
        friends = user.connected_users.filter(current_ver=user.current_ver).annotate(lower_username=Lower('username'))

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

    def retrieve(self, request, *args, **kwargs):
        view_as = parse_view_as(request)  # raises 400 if invalid
        instance = self.get_object()
        shadow_viewer = resolve_shadow_viewer(request, instance)
        # When the owner previews as 'public' (no specific friend chosen),
        # use the configured non-friend proxy user as the shadow viewer so
        # friendship-derived fields render as a real non-friend would see them.
        if shadow_viewer is None and view_as == 'public' and request.user == instance:
            shadow_viewer = resolve_public_proxy_viewer(instance)
        serializer = self.get_serializer(
            instance,
            context={**self.get_serializer_context(), 'view_as': view_as, 'shadow_viewer': shadow_viewer},
        )
        data = dict(serializer.data)
        # Tier-mode field masking applies only when no shadow viewer was resolved.
        # If a shadow_viewer is in play (real friend OR proxy), the serializer's
        # _get_viewer-based masking already handled bio/pronouns/etc. correctly.
        if view_as is not None and instance == request.user and shadow_viewer is None:
            apply_profile_view_as(data, instance, view_as)
        return Response(data)


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
        
        user = request.user
        serialized_data = []
        for obj in objects_to_serialize:
            if isinstance(obj, Note):
                serialized = NoteSerializer(obj, context=self.get_serializer_context()).data
                serialized['type'] = 'Note' # Optional: helps client distinguish
            elif isinstance(obj, _Response):
                serialized = ResponseSerializer(obj, context=self.get_serializer_context()).data
                serialized['type'] = 'Response' # Optional
            serialized_data.append(serialized)

        for obj in objects_to_serialize:
            obj.readers.add(user)

        return self.get_paginated_response(serialized_data) if page is not None else Response(serialized_data)


class UserUnreadPostList(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def list(self, request, *args, **kwargs):
        user = request.user
        author_username = self.kwargs.get('username')
        author = get_object_or_404(User, username=author_username)

        all_notes = Note.objects.filter(author=author)
        note_ids = [note.id for note in all_notes if note.is_audience(user)]
        unread_notes = list(
            Note.objects.filter(id__in=note_ids).exclude(readers=user).order_by('-created_at').distinct()
        )

        all_responses = _Response.objects.filter(author=author).order_by('-created_at')
        response_ids = [response.id for response in all_responses if response.is_audience(user)]
        unread_responses = list(
            _Response.objects.filter(id__in=response_ids).exclude(readers=user).distinct()
        )

        combined = sorted(chain(unread_notes, unread_responses), key=lambda x: x.created_at, reverse=True)

        serialized_data = []
        for obj in combined:
            if isinstance(obj, Note):
                serialized = NoteSerializer(obj, context=self.get_serializer_context()).data
                serialized['type'] = 'Note'
            elif isinstance(obj, _Response):
                serialized = ResponseSerializer(obj, context=self.get_serializer_context()).data
                serialized['type'] = 'Response'
            serialized_data.append(serialized)

        # Mark all as read after fetching
        for obj in unread_notes:
            obj.readers.add(user)
        for obj in unread_responses:
            obj.readers.add(user)

        return Response(serialized_data)


def _viewer_can_see_pinned_entry(entry, owner, viewer):
    """Pin visibility check for a given viewer.

    Mirrors the rules used by viewer_sees_check_in_component (public /
    friends / close_friends with upgrade-time handling) but applied to
    entry.pin_visibility. Unlike the live check-in collapse, pinned
    entries are not subject to the 12h only_me auto-archive — a pin is
    an explicit sharing action that the owner can modify anytime via
    the archive's ⋯ → modify visibility modal.
    """
    vis = entry.pin_visibility
    if vis is None:
        return False
    if viewer == owner:
        return True
    if vis == 'only_me':
        return False
    if vis == 'public':
        return True
    if vis == 'friends':
        return viewer.is_connected(owner)
    if vis == 'close_friends':
        if not viewer.is_close_friend(owner):
            return False
        connection = Connection.get_connection_between(owner, viewer)
        if not connection:
            return False
        if owner == connection.user1:
            update_past_posts = connection.user1_update_past_posts
            upgrade_time = connection.user1_upgrade_time
        else:
            update_past_posts = connection.user2_update_past_posts
            upgrade_time = connection.user2_upgrade_time
        if update_past_posts:
            return True
        if upgrade_time is None:
            return True
        if entry.created_at > upgrade_time:
            return True
        return False
    return False


class UserPinnedCheckInEntries(generics.ListAPIView):
    """GET /api/user/<username>/check_in/pinned/

    Friend-visible pinned archive entries for the target user. Response
    matches the owner archive feed (cursor-paginated flat list, newest
    first, each row carrying id/component/data/visibility/is_pinned/
    pin_visibility/created_at/superseded_at). The top-level
    `pinned_count` reflects only pins this viewer can see, so it powers
    the friend card's `Pinned Check-ins (N)` badge directly — no
    second request.
    """
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @property
    def pagination_class(self):
        from check_in.views import ArchiveCursorPagination
        return ArchiveCursorPagination

    def get_serializer_class(self):
        from check_in.serializers import ArchiveEntrySerializer
        return ArchiveEntrySerializer

    def _get_owner(self):
        if not hasattr(self, '_cached_owner'):
            self._cached_owner = get_object_or_404(
                User, username=self.kwargs.get('username')
            )
        return self._cached_owner

    def _visible_ids(self):
        if hasattr(self, '_cached_visible_ids'):
            return self._cached_visible_ids
        from check_in.models import CheckInComponentEntry
        viewer = self.request.user
        owner = self._get_owner()
        # User-level block short-circuit — mirrors CheckIn.is_audience.
        if owner.id in viewer.user_report_blocked_ids:
            self._cached_visible_ids = []
            return self._cached_visible_ids
        qs = CheckInComponentEntry.objects.filter(owner=owner, is_pinned=True)
        self._cached_visible_ids = [
            e.id for e in qs
            if _viewer_can_see_pinned_entry(e, owner, viewer)
        ]
        return self._cached_visible_ids

    def get_queryset(self):
        from check_in.models import CheckInComponentEntry
        ids = self._visible_ids()
        return CheckInComponentEntry.objects.filter(id__in=ids).order_by('-id')

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response.data['pinned_count'] = len(self._visible_ids())
        return response


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


class CurrentUserNoteStatus(APIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get(self, request):
        user = request.user
        tz_now = timezone.now().astimezone(ZoneInfo(user.timezone))
        start_of_today = tz_now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        has_posted_note_today = Note.objects.filter(
            author=user,
            created_at__gte=start_of_today
        ).exists()
        
        return Response({'has_posted_note_today': has_posted_note_today}, status=200)


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
        updated_user = self.get_object()
        
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
                pass
            
            if persona_str is not None:
                old_personas = list(updated_user.user_personas.all())
                persona_tags = parse_hashtags_or_list(persona_str)
                persona_instances = [get_or_create_normalized_tag(Persona, tag) for tag in persona_tags]
                updated_user.user_personas.set(persona_instances)
                # Orphan cleanup
                from account.models import PERSONA_CHOICES
                predefined_personas = {normalize_tag(val) for _, val in PERSONA_CHOICES}
                for p in old_personas:
                    if p not in persona_instances:
                        if normalize_tag(p.content) not in predefined_personas:
                            if p.users.count() == 0:
                                p.delete()

            if interest_str is not None:
                interest_category = self.request.data.get('interest_category')

                if interest_category and interest_category in dict(CHIP_CATEGORY_CHOICES):
                    # Category-specific update: only modify interests for this category
                    if isinstance(interest_str, str):
                        try:
                            interest_tags = json.loads(interest_str)
                        except json.JSONDecodeError:
                            interest_tags = parse_hashtags_or_list(interest_str)
                    else:
                        interest_tags = interest_str if isinstance(interest_str, list) else parse_hashtags_or_list(interest_str)

                    # Remove user's existing interests in this category
                    old_category_interests = list(updated_user.user_interests.filter(category=interest_category))
                    for i in old_category_interests:
                        updated_user.user_interests.remove(i)
                        if i.users.count() == 0:
                            i.delete()

                    # Add new interests for this category (preserve exact chip names)
                    for tag in interest_tags:
                        # Handle SafeDelete: check all_with_deleted to avoid unique constraint issues
                        try:
                            interest = Interest.objects.all_with_deleted().get(content=tag, category=interest_category)
                            if interest.deleted:
                                interest.undelete()
                        except Interest.DoesNotExist:
                            interest = Interest.objects.create(content=tag, category=interest_category)
                        updated_user.user_interests.add(interest)
                else:
                    # Full replacement (backward compatible)
                    old_interests = list(updated_user.user_interests.all())
                    interest_tags = parse_hashtags_or_list(interest_str)
                    interest_instances = [get_or_create_normalized_tag(Interest, tag) for tag in interest_tags]
                    updated_user.user_interests.set(interest_instances)

                    # Orphan cleanup
                    for i in old_interests:
                        if i not in interest_instances:
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


class CurrentUserChipsUpdate(generics.GenericAPIView):
    """Accept chips_by_category dict: {category_key: [chip_labels]}."""
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        chips_by_category = request.data.get('chips_by_category', {})
        if not isinstance(chips_by_category, dict):
            return Response(status=status.HTTP_400_BAD_REQUEST, data={"error": "chips_by_category must be a dict"})
        update_user_interests_logic(request.user, chips_by_category)
        return Response(status=status.HTTP_200_OK, data={"message": "Chips updated"})


class ChipCategoriesView(APIView):
    """Return all chip category definitions (single source of truth)."""
    permission_classes = [IsAuthenticated]

    def get(self, _request):
        result = []
        for key, label in CHIP_CATEGORY_CHOICES:
            result.append({
                'key': key,
                'label': label,
                'description': CHIP_CATEGORY_DESCRIPTIONS.get(key, ''),
                'chips': CHIPS_BY_CATEGORY.get(key, []),
            })
        return Response(result)


class CustomChipListCreate(generics.ListCreateAPIView):
    """List and create custom chips for the current user."""
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        return CustomChip.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        from account.serializers import CustomChipSerializer
        return CustomChipSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        category = serializer.validated_data.get('category')
        # Enforce max 15 per category
        count = CustomChip.objects.filter(user=user, category=category).count()
        if count >= 15:
            raise serializers.ValidationError("Maximum 15 custom chips per category")
        serializer.save(user=user)

    def delete(self, request, *args, **kwargs):
        chip_id = request.data.get('id')
        if chip_id:
            CustomChip.objects.filter(user=request.user, id=chip_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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

    def retrieve(self, request, *args, **kwargs):
        view_as = parse_view_as(request)  # raises 400 if invalid
        instance = self.get_object()
        shadow_viewer = resolve_shadow_viewer(request, instance)
        # When the owner previews as 'public' (no specific friend chosen),
        # use the configured non-friend proxy user as the shadow viewer so
        # friendship-derived fields render as a real non-friend would see them.
        if shadow_viewer is None and view_as == 'public' and request.user == instance:
            shadow_viewer = resolve_public_proxy_viewer(instance)
        serializer = self.get_serializer(
            instance,
            context={**self.get_serializer_context(), 'view_as': view_as, 'shadow_viewer': shadow_viewer},
        )
        data = dict(serializer.data)
        # Tier-mode field masking applies only when no shadow viewer was resolved.
        # If a shadow_viewer is in play (real friend OR proxy), the serializer's
        # _get_viewer-based masking already handled bio/pronouns/etc. correctly.
        if view_as is not None and instance == request.user and shadow_viewer is None:
            apply_profile_view_as(data, instance, view_as)
        return Response(data)


class CurrentUserNoteList(generics.ListAPIView):
    queryset = Note.objects.all()
    serializer_class = NoteSerializer
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

    def get_queryset(self):
        if hasattr(self, '_qs'):
            return self._qs

        user = self.request.user
        friends = user.connected_users.filter(current_ver=user.current_ver)

        query_type = self.request.query_params.get('type')

        if query_type == 'all' or query_type == 'friends':
            self._qs = friends.order_by('username')
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

            self._qs = friends.filter(id__in=target_ids).order_by('username')
        elif query_type == 'has_updates':
            friends = friends.exclude(hidden=True)
            friends_with_updates = [
                friend for friend in friends if not User.user_read(user, friend)
            ]
            self._qs = sorted(friends_with_updates, key=lambda x: x.most_recent_update(user), reverse=True)
        elif query_type == 'favorites':
            self._qs = user.favorites.all().order_by('username')
        else:
            raise Http404("Query parameter 'type' is invalid or not provided.")

        return self._qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            self._page_friend_ids = [f.id for f in page]
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        self._page_friend_ids = [f.id for f in queryset]
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        friend_ids = getattr(self, '_page_friend_ids', None)
        if friend_ids is None:
            qs = self.get_queryset()
            if hasattr(qs, 'values_list'):
                friend_ids = list(qs.values_list('id', flat=True))
            else:
                friend_ids = [f.id for f in qs]
        self._build_batch_context(ctx, friend_ids)
        return ctx

    def _build_batch_context(self, ctx, friend_ids):
        from collections import defaultdict
        from check_in.models import CheckIn, Song, Poke
        from chat.models import ChatRoom, Message
        from note.models import Note
        from qna.models import Response as QnaResponse
        from content_report.models import ContentReport

        user = self.request.user
        ctx['friend_ids'] = friend_ids
        if not friend_ids:
            ctx.update({
                'favorite_ids': set(), 'hidden_ids': set(),
                'connection_by_friend_id': {},
                'visible_check_in_by_user_id': {},
                'active_song_by_user_id': {},
                'unread_note_count_by_author': {},
                'unread_response_count_by_author': {},
                'unread_chat_count_by_friend_id': {},
                'visible_notes_by_author': {},
                'visible_resps_by_author': {},
                'user_report_blocked_ids': set(),
                'content_report_keys': set(),
                'pokes_by_receiver': {},
                'pinned_count_by_friend_id': {},
            })
            return

        # 1. Favorites / hidden M2M
        ctx['favorite_ids'] = set(user.favorites.filter(id__in=friend_ids).values_list('id', flat=True))
        ctx['hidden_ids'] = set(user.hidden.filter(id__in=friend_ids).values_list('id', flat=True))

        # 2. Connection rows
        conns = Connection.objects.filter(
            Q(user1=user, user2_id__in=friend_ids) | Q(user2=user, user1_id__in=friend_ids)
        )
        connection_by_friend_id = {}
        for c in conns:
            other_id = c.user2_id if c.user1_id == user.id else c.user1_id
            connection_by_friend_id[other_id] = c
        ctx['connection_by_friend_id'] = connection_by_friend_id

        # 3. User-report block set (cached once; property issues 2 queries)
        user_report_blocked_ids = set(user.user_report_blocked_ids)
        ctx['user_report_blocked_ids'] = user_report_blocked_ids

        # 4. ContentType ids + viewer's ContentReport keys for Note/Response/CheckIn
        ct_note = ContentType.objects.get_for_model(Note)
        ct_resp = ContentType.objects.get_for_model(QnaResponse)
        ct_ci = ContentType.objects.get_for_model(CheckIn)
        ctx['ct_ids'] = {'note': ct_note.id, 'response': ct_resp.id, 'check_in': ct_ci.id}
        content_report_keys = set(
            ContentReport.objects.filter(
                user=user,
                content_type_id__in=[ct_note.id, ct_resp.id, ct_ci.id],
            ).values_list('content_type_id', 'object_id')
        )
        ctx['content_report_keys'] = content_report_keys

        def _passes_close_friends(author_id, created_at):
            conn = connection_by_friend_id.get(author_id)
            if not conn:
                return False
            # author's choice for viewer
            author_choice = conn.user1_choice if conn.user1_id == author_id else conn.user2_choice
            if author_choice != 'close_friend':
                return False
            if author_id == conn.user1_id:
                update_past = conn.user1_update_past_posts
                upgrade_time = conn.user1_upgrade_time
            else:
                update_past = conn.user2_update_past_posts
                upgrade_time = conn.user2_upgrade_time
            return update_past or upgrade_time is None or created_at > upgrade_time

        def _is_audience(author_id, visibility, pk, ct_id, created_at):
            if (ct_id, pk) in content_report_keys:
                return False
            if author_id in user_report_blocked_ids:
                return False
            if author_id == user.id:
                return True
            if 'public' in visibility:
                return True
            if 'friends' in visibility:
                return True  # viewer is, by definition, in connected_users
            if 'close_friends' in visibility:
                return _passes_close_friends(author_id, created_at)
            return False

        # 5. Active check-ins (with readers prefetch) + visibility filter
        check_ins = list(
            CheckIn.objects.filter(user_id__in=friend_ids, is_active=True)
            .prefetch_related('readers')
        )
        visible_check_in_by_user_id = {}
        for ci in check_ins:
            if _is_audience(ci.user_id, ci.visibility, ci.pk, ct_ci.id, ci.created_at):
                visible_check_in_by_user_id[ci.user_id] = ci
        ctx['visible_check_in_by_user_id'] = visible_check_in_by_user_id

        # 6. Active songs
        ctx['active_song_by_user_id'] = {
            s.user_id: s for s in Song.objects.filter(user_id__in=friend_ids, is_active=True)
        }

        # 8. Chat rooms + unread counts (read-only; no writes)
        rooms = list(ChatRoom.objects.filter(is_group=False).filter(
            Q(user1=user, user2_id__in=friend_ids) | Q(user2=user, user1_id__in=friend_ids)
        ))
        room_to_other = {}
        for r in rooms:
            other_id = r.user2_id if r.user1_id == user.id else r.user1_id
            room_to_other[r.id] = other_id
        unread_rows = (Message.objects.filter(
            chat_room_id__in=list(room_to_other.keys()),
            receiver=user, is_read=False,
        ).values('chat_room_id').annotate(c=Count('id')))
        unread_chat_count_by_friend_id = {}
        for row in unread_rows:
            other_id = room_to_other.get(row['chat_room_id'])
            if other_id is not None:
                unread_chat_count_by_friend_id[other_id] = row['c']
        ctx['unread_chat_count_by_friend_id'] = unread_chat_count_by_friend_id

        # 9. Visible notes / responses (model instances, readers + images prefetched)
        notes_qs = (Note.objects.filter(author_id__in=friend_ids)
                    .select_related('author')
                    .prefetch_related('readers', 'images', 'note_likes',
                                      'note_comments', 'note_comments__replies'))
        resps_qs = (QnaResponse.objects.filter(author_id__in=friend_ids)
                    .select_related('author', 'question')
                    .prefetch_related('readers', 'response_likes',
                                      'response_comments', 'response_comments__replies'))
        visible_notes_by_author = defaultdict(list)
        for n in notes_qs:
            if _is_audience(n.author_id, n.visibility, n.pk, ct_note.id, n.created_at):
                visible_notes_by_author[n.author_id].append(n)
        visible_resps_by_author = defaultdict(list)
        for r in resps_qs:
            if _is_audience(r.author_id, r.visibility, r.pk, ct_resp.id, r.created_at):
                visible_resps_by_author[r.author_id].append(r)
        ctx['visible_notes_by_author'] = visible_notes_by_author
        ctx['visible_resps_by_author'] = visible_resps_by_author

        # 7. Unread note / response counts — derived from the audience-filtered
        # visible_*_by_author dicts so badge stays in sync with `recent_posts` and
        # `FriendsMarkAllPostsAsRead`. Same window as recent_posts (24h), and same
        # superuser exclusion as mark-as-read for notes.
        recent_cutoff = timezone.now() - RECENT_POST_WINDOW
        unread_note_count_by_author = {}
        for author_id, notes in visible_notes_by_author.items():
            c = sum(1 for n in notes
                    if n.created_at >= recent_cutoff
                    and not n.author.is_superuser
                    and user.id not in {r.id for r in n.readers.all()})
            if c:
                unread_note_count_by_author[author_id] = c
        ctx['unread_note_count_by_author'] = unread_note_count_by_author

        unread_response_count_by_author = {}
        for author_id, resps in visible_resps_by_author.items():
            c = sum(1 for r in resps
                    if r.created_at >= recent_cutoff
                    and user.id not in {rd.id for rd in r.readers.all()})
            if c:
                unread_response_count_by_author[author_id] = c
        ctx['unread_response_count_by_author'] = unread_response_count_by_author

        # 10. Pokes (preserved from prior implementation)
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        pokes = Poke.objects.filter(
            sender=user, receiver_id__in=friend_ids, created_at__gte=today_start,
        ).values('receiver_id', 'component_type', 'id')
        bucket = {}
        for p in pokes:
            bucket.setdefault(p['receiver_id'], {})[p['component_type']] = p['id']
        ctx['pokes_by_receiver'] = bucket

        # 11. Viewer-visible pinned archive entries per friend.
        # Avoids N+1 on the friend-card `Pinned Check-ins (N)` chip by
        # bulk-fetching all pinned rows for this page's friends in one
        # query and applying pin_visibility × relationship filtering in
        # Python, reusing the same helpers that drive the single-user
        # pinned endpoint. Only fields required for the filter are
        # selected so the scan is cheap even for heavy users.
        from check_in.models import CheckInComponentEntry

        pinned_rows = CheckInComponentEntry.objects.filter(
            owner_id__in=friend_ids,
            is_pinned=True,
            pin_visibility__isnull=False,
        ).values('owner_id', 'pin_visibility', 'created_at')

        pinned_count_by_friend_id = {}
        for row in pinned_rows:
            owner_id = row['owner_id']
            if owner_id in user_report_blocked_ids:
                continue
            vis = row['pin_visibility']
            if vis == 'only_me':
                continue
            if vis in ('public', 'friends'):
                # Every entry in friend_ids is already connected_users, so
                # `friends` visibility is trivially satisfied.
                pinned_count_by_friend_id[owner_id] = (
                    pinned_count_by_friend_id.get(owner_id, 0) + 1
                )
            elif vis == 'close_friends':
                if _passes_close_friends(owner_id, row['created_at']):
                    pinned_count_by_friend_id[owner_id] = (
                        pinned_count_by_friend_id.get(owner_id, 0) + 1
                    )
        ctx['pinned_count_by_friend_id'] = pinned_count_by_friend_id

        # 11. Check-in subscriptions (version_w only)
        if user.current_ver == 'version_w':
            from adoorback.utils.content_types import get_check_in_type
            ctx['check_in_subscription_ids'] = set(
                Subscription.objects.filter(
                    subscriber=user, content_type=get_check_in_type()
                ).values_list('subscribed_to_id', flat=True)
            )
        else:
            ctx['check_in_subscription_ids'] = set()

        # 12. Any-type subscriptions (모든 subscription_type 통합)
        ctx['subscription_ids'] = set(
            Subscription.objects.filter(subscriber=user)
            .values_list('subscribed_to_id', flat=True)
            .distinct()
        )


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
        friends = user.connected_users.filter(current_ver=user.current_ver).exclude(hidden=True)

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

        return user.connected_users.filter(current_ver=self.request.user.current_ver).order_by(Lower('username'))


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

        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        from chat.views import _get_chat_group_name
        channel_layer = get_channel_layer()
        if channel_layer is not None:
            async_to_sync(channel_layer.group_send)(
                _get_chat_group_name(user.id, obj.id),
                {"type": "friendship.broken", "data": {
                    "action": "friendship_broken",
                    "broken_by": user.id,
                }},
            )


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


class UserRecommendedFriendsList(generics.ListAPIView):
    serializer_class = UserMinimumSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user_id = self.request.user.id
        user = get_object_or_404(User, id=user_id)
        user_friends = user.connected_users.filter(current_ver=user.current_ver)

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


def _build_audience_ctx(user, friend_ids, content_type_ids):
    from content_report.models import ContentReport

    conns = Connection.objects.filter(
        Q(user1=user, user2_id__in=friend_ids) | Q(user2=user, user1_id__in=friend_ids)
    )
    connection_by_friend_id = {}
    for c in conns:
        other_id = c.user2_id if c.user1_id == user.id else c.user1_id
        connection_by_friend_id[other_id] = c

    user_report_blocked_ids = set(user.user_report_blocked_ids)
    content_report_keys = set(
        ContentReport.objects.filter(
            user=user, content_type_id__in=content_type_ids,
        ).values_list('content_type_id', 'object_id')
    )
    return connection_by_friend_id, user_report_blocked_ids, content_report_keys


def _check_audience(user, author_id, visibility, pk, ct_id, created_at,
                    connection_by_friend_id, content_report_keys, user_report_blocked_ids):
    if (ct_id, pk) in content_report_keys:
        return False
    if author_id in user_report_blocked_ids:
        return False
    if author_id == user.id:
        return True
    if 'public' in visibility:
        return True
    if 'friends' in visibility:
        return True
    if 'close_friends' in visibility:
        conn = connection_by_friend_id.get(author_id)
        if not conn:
            return False
        author_choice = conn.user1_choice if conn.user1_id == author_id else conn.user2_choice
        if author_choice != 'close_friend':
            return False
        if author_id == conn.user1_id:
            update_past = conn.user1_update_past_posts
            upgrade_time = conn.user1_upgrade_time
        else:
            update_past = conn.user2_update_past_posts
            upgrade_time = conn.user2_upgrade_time
        return update_past or upgrade_time is None or created_at > upgrade_time
    return False


class FriendsMarkAllCheckInsAsRead(APIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def patch(self, request):
        from check_in.models import CheckIn

        user = request.user
        friend_ids = list(user.connected_users.filter(
            current_ver=user.current_ver
        ).values_list('id', flat=True))
        if not friend_ids:
            return Response({'success': True, 'count': 0}, status=status.HTTP_200_OK)

        ct_ci = ContentType.objects.get_for_model(CheckIn)
        connection_by_friend_id, user_report_blocked_ids, content_report_keys = (
            _build_audience_ctx(user, friend_ids, [ct_ci.id])
        )

        check_ins = (CheckIn.objects.filter(user_id__in=friend_ids, is_active=True)
                     .exclude(readers=user))
        eligible_ids = [
            ci.pk for ci in check_ins
            if _check_audience(user, ci.user_id, ci.visibility, ci.pk, ct_ci.id,
                               ci.created_at, connection_by_friend_id,
                               content_report_keys, user_report_blocked_ids)
        ]

        if eligible_ids:
            Through = CheckIn.readers.through
            Through.objects.bulk_create(
                [Through(checkin_id=ci_id, user_id=user.id) for ci_id in eligible_ids],
                ignore_conflicts=True,
            )

        return Response({'success': True, 'count': len(eligible_ids)},
                        status=status.HTTP_200_OK)


class FriendsMarkAllPostsAsRead(APIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def patch(self, request):
        user = request.user
        friend_ids = list(user.connected_users.filter(
            current_ver=user.current_ver
        ).values_list('id', flat=True))
        if not friend_ids:
            return Response({'success': True, 'note_count': 0, 'response_count': 0},
                            status=status.HTTP_200_OK)

        ct_note = ContentType.objects.get_for_model(Note)
        ct_resp = ContentType.objects.get_for_model(_Response)
        connection_by_friend_id, user_report_blocked_ids, content_report_keys = (
            _build_audience_ctx(user, friend_ids, [ct_note.id, ct_resp.id])
        )

        notes = (Note.objects.filter(author_id__in=friend_ids)
                 .exclude(readers=user)
                 .exclude(author__is_superuser=True))
        eligible_note_ids = [
            n.pk for n in notes
            if _check_audience(user, n.author_id, n.visibility, n.pk, ct_note.id,
                               n.created_at, connection_by_friend_id,
                               content_report_keys, user_report_blocked_ids)
        ]
        if eligible_note_ids:
            NoteThrough = Note.readers.through
            NoteThrough.objects.bulk_create(
                [NoteThrough(note_id=n_id, user_id=user.id) for n_id in eligible_note_ids],
                ignore_conflicts=True,
            )

        responses = (_Response.objects.filter(author_id__in=friend_ids)
                     .exclude(readers=user))
        eligible_resp_ids = [
            r.pk for r in responses
            if _check_audience(user, r.author_id, r.visibility, r.pk, ct_resp.id,
                               r.created_at, connection_by_friend_id,
                               content_report_keys, user_report_blocked_ids)
        ]
        if eligible_resp_ids:
            RespThrough = _Response.readers.through
            RespThrough.objects.bulk_create(
                [RespThrough(response_id=r_id, user_id=user.id) for r_id in eligible_resp_ids],
                ignore_conflicts=True,
            )

        return Response({'success': True,
                         'note_count': len(eligible_note_ids),
                         'response_count': len(eligible_resp_ids)},
                        status=status.HTTP_200_OK)


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


class CheckInSubscribeAdd(generics.CreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        if request.user.current_ver != 'version_w':
            return Response({'error': 'This feature is only available in version W.'},
                            status=status.HTTP_403_FORBIDDEN)

        friend_id = request.data.get('friend_id')
        if not friend_id:
            return Response({'error': 'Friend ID must be provided.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            friend_id = int(friend_id)
        except ValueError:
            return Response({'error': 'Invalid Friend ID.'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        friend = get_object_or_404(User, id=friend_id)

        if not user.is_connected(friend):
            return Response({'error': 'User is not your friend.'}, status=status.HTTP_400_BAD_REQUEST)

        from adoorback.utils.content_types import get_check_in_type
        check_in_ct = get_check_in_type()
        if Subscription.objects.filter(subscriber=user, subscribed_to=friend, content_type=check_in_ct).exists():
            return Response({'error': 'Already subscribed to this friend\'s check-in.'},
                            status=status.HTTP_400_BAD_REQUEST)

        Subscription.objects.create(subscriber=user, subscribed_to=friend, content_type=check_in_ct)
        return Response({'message': 'Subscribed to check-in successfully.'}, status=status.HTTP_201_CREATED)


class CheckInSubscribeDestroy(generics.DestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def destroy(self, request, *args, **kwargs):
        if request.user.current_ver != 'version_w':
            return Response({'error': 'This feature is only available in version W.'},
                            status=status.HTTP_403_FORBIDDEN)

        friend_id = kwargs.get('pk')
        friend = get_object_or_404(User, id=friend_id)
        from adoorback.utils.content_types import get_check_in_type
        check_in_ct = get_check_in_type()
        subscription = get_object_or_404(
            Subscription, subscriber=request.user, subscribed_to=friend, content_type=check_in_ct
        )
        subscription.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


VER_W_SUBSCRIPTION_TYPES = (
    'battery', 'mood', 'thought', 'song',
    'mission_of_the_day', 'question_of_the_day', 'photo_of_the_day',
)
VER_Q_SUBSCRIPTION_TYPES = ('check_in', 'post')


def _allowed_subscription_types(user):
    if user.current_ver == 'version_q':
        return VER_Q_SUBSCRIPTION_TYPES
    return VER_W_SUBSCRIPTION_TYPES


class FriendSubscriptions(APIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get(self, request, pk):
        friend = get_object_or_404(User, id=pk)
        if not request.user.is_connected(friend):
            return Response({'error': 'User is not your friend.'}, status=status.HTTP_400_BAD_REQUEST)

        allowed = _allowed_subscription_types(request.user)
        types = list(Subscription.objects.filter(
            subscriber=request.user,
            subscribed_to=friend,
            subscription_type__in=allowed,
            deleted__isnull=True,
        ).values_list('subscription_type', flat=True))
        return Response({'types': types}, status=status.HTTP_200_OK)

    @transaction.atomic
    def post(self, request, pk):
        friend = get_object_or_404(User, id=pk)
        if not request.user.is_connected(friend):
            return Response({'error': 'User is not your friend.'}, status=status.HTTP_400_BAD_REQUEST)

        allowed = set(_allowed_subscription_types(request.user))
        requested = request.data.get('types', [])
        if not isinstance(requested, list):
            return Response({'error': 'types must be a list.'}, status=status.HTTP_400_BAD_REQUEST)

        invalid = [t for t in requested if t not in allowed]
        if invalid:
            return Response(
                {'error': f'Invalid subscription types for current version: {invalid}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from adoorback.utils.content_types import get_check_in_type
        check_in_ct = get_check_in_type()

        desired = set(requested)
        existing_qs = Subscription.objects.filter(
            subscriber=request.user,
            subscribed_to=friend,
            subscription_type__in=allowed,
            deleted__isnull=True,
        )
        existing = set(existing_qs.values_list('subscription_type', flat=True))

        to_remove = existing - desired
        if to_remove:
            for sub in existing_qs.filter(subscription_type__in=to_remove):
                sub.delete()

        to_add = desired - existing
        Subscription.objects.bulk_create([
            Subscription(
                subscriber=request.user,
                subscribed_to=friend,
                content_type=check_in_ct,
                subscription_type=stype,
            )
            for stype in to_add
        ])

        return Response({'types': sorted(desired)}, status=status.HTTP_200_OK)


class FriendFeed(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user = self.request.user

        # Filter connected users to same version
        connected_user_ids = list(User.objects.filter(
            id__in=user.connected_user_ids, current_ver=user.current_ver
        ).values_list('id', flat=True))
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
        user = request.user
        queryset = self.get_queryset()

        # freeze notes before marking them as read
        note_ids = queryset.values_list("id", flat=True)
        notes_before_update = list(Note.objects.filter(id__in=note_ids).order_by('-created_at'))

        page = self.paginate_queryset(notes_before_update)
        if page is not None:
            serialized_data = NoteSerializer(page, many=True, context=self.get_serializer_context()).data
        else:
            serialized_data = NoteSerializer(notes_before_update, many=True, context=self.get_serializer_context()).data

        # inject is_check_in_subscribed into author_detail (version_w only)
        if user.current_ver == 'version_w':
            from adoorback.utils.content_types import get_check_in_type
            check_in_sub_ids = set(Subscription.objects.filter(
                subscriber=user, content_type=get_check_in_type()
            ).values_list('subscribed_to_id', flat=True))
            source_items = page if page is not None else notes_before_update
            for item, serialized in zip(source_items, serialized_data):
                if 'author_detail' in serialized and serialized['author_detail']:
                    serialized['author_detail']['is_check_in_subscribed'] = item.author_id in check_in_sub_ids

        # mark all notes as read
        unread_note_ids = queryset.exclude(readers=request.user).values_list("id", flat=True)
        if unread_note_ids:
            request.user.read_notes.add(*unread_note_ids)

        if page is not None:
            return self.get_paginated_response(serialized_data)
        return Response(serialized_data)


class FullFriendFeed(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_combined_feed_items(self):
        user = self.request.user
        # Filter connected users to same version
        connected_user_ids = list(User.objects.filter(
            id__in=user.connected_user_ids, current_ver=user.current_ver
        ).values_list('id', flat=True))
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

        # prefetch check-in subscriptions (version_w only)
        check_in_sub_ids = set()
        if user.current_ver == 'version_w':
            from adoorback.utils.content_types import get_check_in_type
            check_in_sub_ids = set(Subscription.objects.filter(
                subscriber=user, content_type=get_check_in_type()
            ).values_list('subscribed_to_id', flat=True))

        serialized_data = []
        for obj in objects_to_serialize:
            if isinstance(obj, Note):
                serialized = NoteSerializer(obj, context=self.get_serializer_context()).data
            elif isinstance(obj, _Response):
                serialized = ResponseSerializer(obj, context=self.get_serializer_context()).data
            # Add connection_status and is_check_in_subscribed to author_detail
            if 'author_detail' in serialized and serialized['author_detail']:
                author = obj.author
                if author == user:
                    serialized['author_detail']['connection_status'] = None
                elif author.is_close_friend(user):
                    serialized['author_detail']['connection_status'] = 'close_friend'
                elif user.is_connected(author):
                    serialized['author_detail']['connection_status'] = 'friend'
                else:
                    serialized['author_detail']['connection_status'] = None
                if user.current_ver == 'version_w':
                    serialized['author_detail']['is_check_in_subscribed'] = obj.author_id in check_in_sub_ids
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

        # Always return all items — filtering is done client-side using the category field
        latest_timestamp = last_feed.created_at
        queryset = DiscoverFeed.objects.filter(
            user=user,
            created_at=latest_timestamp
        ).select_related('response', 'response__author', 'response__question', 'note', 'note__author')

        # Version isolation: exclude items whose author is on a different version
        queryset = queryset.exclude(
            Q(response__isnull=False) & ~Q(response__author__current_ver=user.current_ver)
        ).exclude(
            Q(note__isnull=False) & ~Q(note__author__current_ver=user.current_ver)
        )

        queryset = queryset.order_by('id')

        return queryset

    @transaction.atomic
    def generate_new_feed(self, user):        
        batch_time = timezone.now()

        friend_ids = set(user.friend_ids + user.close_friend_ids)
        blocked_ids = set(user.user_report_blocked_ids)
        exclude_ids = friend_ids | blocked_ids | {user.id}

        feed_items = []  # List of (object, category)

        # Helper to get candidates (only public visibility for non-friend discover)
        def get_candidates(author_ids, limit=None):
            # Responses — only public posts
            responses = _Response.objects.filter(
                author_id__in=author_ids, visibility__contains=['public']
            ).exclude(readers=user).order_by('-created_at')
            if limit:
                responses = responses[:limit]

            # Notes — only public posts
            notes = Note.objects.filter(
                author_id__in=author_ids, visibility__contains=['public']
            ).exclude(readers=user).order_by('-created_at')
            if limit:
                notes = notes[:limit]

            # Combine and sort
            combined = sorted(chain(responses, notes), key=attrgetter('created_at'), reverse=True)

            # Filter by permission (is_audience)
            valid_candidates = []
            count = 0
            for obj in combined:
                if obj.is_audience(user):
                    valid_candidates.append(obj)
                    count += 1
                if limit and count >= limit:
                    break
            return valid_candidates

        # 1, 2, 3. Collect candidates for Mutual Friends, Mutual Traits, and Strangers

        # Mutual Friends Candidates (same version only)
        user_friends = user.connected_users.filter(current_ver=user.current_ver)
        user_friend_ids = set(user_friends.values_list('id', flat=True))
        mutual_friend_potential_ids = set()
        for friend in user_friends:
            friend_of_friend_ids = set(friend.connected_users.filter(
                current_ver=user.current_ver
            ).values_list('id', flat=True))
            mutual_friend_potential_ids.update(friend_of_friend_ids)
        mf_ids = mutual_friend_potential_ids - user_friend_ids - exclude_ids

        mf_candidates = get_candidates(mf_ids, limit=20)

        # Mutual Traits Candidates
        user_interests = set(user.user_interests.values_list('id', flat=True))
        user_personas = set(user.user_personas.values_list('id', flat=True))
        trait_ids = set(User.objects.filter(
            Q(user_interests__id__in=user_interests) | Q(user_personas__id__in=user_personas),
            current_ver=user.current_ver
        ).exclude(id__in=exclude_ids).values_list('id', flat=True))

        trait_candidates = get_candidates(trait_ids, limit=20)

        # Strangers (No Mutual) Candidates
        stranger_ids = set(User.objects.filter(
            current_ver=user.current_ver
        ).exclude(
            id__in=exclude_ids | mutual_friend_potential_ids | trait_ids
        ).exclude(is_superuser=True).values_list('id', flat=True))
        
        stranger_candidates = get_candidates(stranger_ids, limit=20)

        category_candidates = [
            (mf_candidates, 'mutual_friends'),
            (trait_candidates, 'mutual_traits'),
            (stranger_candidates, 'anonymous')
        ]
        
        existing_obj_ids = {(type(item[0]), item[0].id) for item in feed_items}
        
        # Step 1: Ensure at least 1 from each category (if exists)
        for candidates, category_name in category_candidates:
            while candidates:
                cand = candidates.pop(0)
                if (type(cand), cand.id) not in existing_obj_ids:
                    feed_items.append((cand, category_name))
                    existing_obj_ids.add((type(cand), cand.id))
                    break

        # Step 2: If still less than 10, fill more in round-robin fashion
        while len(feed_items) < 10:
            added_in_round = False
            for candidates, category_name in category_candidates:
                if len(feed_items) >= 10:
                    break
                
                while candidates:
                    cand = candidates.pop(0)
                    if (type(cand), cand.id) not in existing_obj_ids:
                        feed_items.append((cand, category_name))
                        existing_obj_ids.add((type(cand), cand.id))
                        added_in_round = True
                        break
            
            if not added_in_round:
                break

        # 5. Fallback: Fill up to 10 random posts (from any non-friends) if still not enough
        if len(feed_items) < 10:
            # Random Response — only public
            random_responses = list(_Response.objects.filter(
                visibility__contains=['public'],
                author__current_ver=user.current_ver
            ).exclude(
                author_id__in=exclude_ids
            ).exclude(readers=user).order_by('-created_at')[:50])

            # Random Note — only public
            random_notes = list(Note.objects.filter(
                visibility__contains=['public'],
                author__current_ver=user.current_ver
            ).exclude(
                author_id__in=exclude_ids
            ).exclude(readers=user).order_by('-created_at')[:50])

            random_potentials = random_responses + random_notes
            random.shuffle(random_potentials) # Shuffle candidates for random selection
            
            for obj in random_potentials:
                if len(feed_items) >= 10:
                    break
                if (type(obj), obj.id) not in existing_obj_ids and obj.is_audience(user):
                    feed_items.append((obj, 'random'))
                    existing_obj_ids.add((type(obj), obj.id))

        # Sort by created_at descending (Newest first)
        feed_items.sort(key=lambda x: x[0].created_at, reverse=True)

        # Save to DiscoverFeed
        for i, (obj, category) in enumerate(feed_items):
            response = obj if isinstance(obj, _Response) else None
            note = obj if isinstance(obj, Note) else None
            
            DiscoverFeed.objects.create(
                user=user,
                response=response,
                note=note,
                category=category,
                created_at=batch_time,
                sort_order=i
            )

        # Generate music tracks for discover feed (respect check-in + song_visibility)
        from check_in.models import Song, CheckIn as CheckInModel
        music_candidates = Song.objects.filter(
            is_active=True,
            user__current_ver=user.current_ver,
        ).exclude(
            user_id__in=exclude_ids
        ).select_related('user').order_by('-created_at')[:40]

        music_songs = []
        for song in music_candidates:
            if len(music_songs) >= 10:
                break
            author = song.user
            active_check_in = CheckInModel.objects.filter(user=author, is_active=True).first()
            if not active_check_in:
                continue
            if not active_check_in.is_audience(user):
                continue
            if not viewer_sees_check_in_component(
                active_check_in, author, user, 'song_visibility', 'song_updated_at'
            ):
                continue
            music_songs.append(song)

        for idx, song in enumerate(music_songs):
            # Determine category based on author
            author_id = song.user_id
            if author_id in mf_ids:
                cat = 'mutual_friends'
            elif author_id in trait_ids:
                cat = 'mutual_traits'
            else:
                cat = 'random'

            DiscoverFeedMusic.objects.create(
                user=user,
                song=song,
                category=cat,
                sort_order=idx,
                created_at=batch_time,
            )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        feed_objects = page if page is not None else queryset
        
        responses = []
        notes = []
        for item in feed_objects:
            if item.response:
                responses.append(item.response)
            elif item.note:
                notes.append(item.note)

        # Mark as read
        if responses:
            request.user.read_responses.add(*responses)
        if notes:
            request.user.read_notes.add(*notes)

        # Serialize
        resp_data_map = {}
        if responses:
            serializer = ResponseSerializer(responses, many=True, context={'request': request})
            resp_data_map = {d['id']: d for d in serializer.data}
            
        note_data_map = {}
        if notes:
            serializer = NoteSerializer(notes, many=True, context={'request': request})
            note_data_map = {d['id']: d for d in serializer.data}

        # --- Injection Logic ---
        req_user = request.user
        req_user_friends = set(req_user.friend_ids + req_user.close_friend_ids)
        req_user_interests = set(req_user.user_interests.values_list('id', flat=True))
        req_user_personas = set(req_user.user_personas.values_list('id', flat=True))

        results = []
        for item in feed_objects:
            author = item.response.author if item.response else item.note.author

            mut_friends = 0
            mut_interests = 0
            mut_personas = 0

            if req_user != author:
                author_friends = set(author.friend_ids + author.close_friend_ids)
                author_interests = set(author.user_interests.values_list('id', flat=True))
                author_personas = set(author.user_personas.values_list('id', flat=True))
                
                mut_friends = len(req_user_friends & author_friends)
                mut_interests = len(req_user_interests & author_interests)
                mut_personas = len(req_user_personas & author_personas)

            if item.response:
                data = resp_data_map.get(item.response.id)
                if data:
                    if 'author_detail' in data and isinstance(data['author_detail'], dict):
                        data['author_detail']['mutual_friend_count'] = mut_friends
                        data['author_detail']['mutual_interest_count'] = mut_interests
                        data['author_detail']['mutual_persona_count'] = mut_personas
                    results.append({
                        "type": "Response",
                        "category": item.category,
                        "body": data
                    })
            elif item.note:
                data = note_data_map.get(item.note.id)
                if data:
                    if 'author_detail' in data and isinstance(data['author_detail'], dict):
                        data['author_detail']['mutual_friend_count'] = mut_friends
                        data['author_detail']['mutual_interest_count'] = mut_interests
                        data['author_detail']['mutual_persona_count'] = mut_personas
                    results.append({
                        "type": "Note",
                        "category": item.category,
                        "body": data
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
        
        original_count = len(results)

        # Inject Interest (single category, rotating)
        if original_count >= 5:
            i_idx = random.choice([5, 6])

            user = request.user
            user_interests = user.user_interests.all()
            all_categories = [key for key, _ in CHIP_CATEGORY_CHOICES]

            # Count user's selections per category
            selection_counts = {}
            for cat_key in all_categories:
                selection_counts[cat_key] = user_interests.filter(category=cat_key).count()

            # Sort by fewest selections (ascending), then shuffle ties
            sorted_cats = sorted(all_categories, key=lambda c: (selection_counts[c], random.random()))

            # Pick first category that differs from last shown; fall back to first if all same
            last_shown = user.last_interest_card_category
            chosen_category = sorted_cats[0]
            if last_shown and len(sorted_cats) > 1:
                for cat in sorted_cats:
                    if cat != last_shown:
                        chosen_category = cat
                        break

            # Save chosen category for next rotation
            user.last_interest_card_category = chosen_category
            user.save(update_fields=['last_interest_card_category'])

            # Build interest list for the chosen category
            category_label = dict(CHIP_CATEGORY_CHOICES)[chosen_category]
            category_interests = user_interests.filter(category=chosen_category)
            user_interest_contents = {i.content for i in category_interests}

            # Use CHIPS_BY_CATEGORY (matching frontend chips.ts)
            category_chips = CHIPS_BY_CATEGORY.get(chosen_category, [])
            category_chips_set = set(category_chips)

            interest_list = []
            for chip_name in category_chips:
                interest_list.append({
                    "content": chip_name,
                    "is_selected": chip_name in user_interest_contents
                })

            # Add custom interests in this category (user-created, not in predefined chips)
            for user_interest in category_interests:
                if user_interest.content not in category_chips_set:
                    interest_list.append({
                        "content": user_interest.content,
                        "is_selected": True
                    })

            interest_card = {
                "type": "Interest",
                "body": {
                    "category": chosen_category,
                    "category_label": category_label,
                    "list": interest_list
                }
            }
            results.insert(min(len(results), i_idx), interest_card)

        # Build music_tracks for the first page only
        music_tracks_data = []
        request_page = request.query_params.get('page', '1')
        if str(request_page) == '1' or request_page is None:
            # Get the latest batch timestamp for this user's discover feed music
            latest_music = DiscoverFeedMusic.objects.filter(
                user=request.user
            ).order_by('-created_at').first()

            if latest_music:
                music_items = DiscoverFeedMusic.objects.filter(
                    user=request.user,
                    created_at=latest_music.created_at,
                    song__user__current_ver=request.user.current_ver,
                ).select_related('song', 'song__user').order_by('sort_order')

                for item in music_items:
                    song = item.song
                    author = song.user
                    music_tracks_data.append({
                        'id': item.id,
                        'user': {
                            'id': author.id,
                            'username': author.username,
                            'profile_pic': author.profile_pic or None,
                            'url': f'/api/user/{author.id}/',
                            'profile_image': author.profile_image.url if author.profile_image else None,
                        },
                        'track_id': song.track_id,
                        'created_at': item.created_at.isoformat(),
                    })

        if page is not None:
            response = self.get_paginated_response(results)
            if music_tracks_data:
                response.data['music_tracks'] = music_tracks_data
            return response

        # If not paginated, return wrapped structure
        resp_data = {"results": results}
        if music_tracks_data:
            resp_data['music_tracks'] = music_tracks_data
        return Response(resp_data)



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


class TmiPlaceholder(APIView):
    """Generate a daily TMI example placeholder using the Anthropic API."""
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get(self, request, *args, **kwargs):
        import datetime
        from django.core.cache import cache

        today_str = datetime.date.today().isoformat()
        lang = request.query_params.get('lang', 'en')
        cache_key = f'tmi_placeholder_{today_str}_{lang}'

        cached = cache.get(cache_key)
        if cached:
            return Response({'placeholder': cached})

        # Fallback examples in case API fails
        fallbacks_en = [
            "had the best reindeer hotdog today!!!",
            "finally beat my friend at bowling 🎳",
            "accidentally called my professor 'mom' today…",
            "found the best ramen place near campus",
            "my cat learned how to open the fridge 😱",
        ]
        fallbacks_ko = [
            "오늘 인생 핫도그를 먹었다!!!",
            "드디어 친구한테 볼링에서 이겼다 🎳",
            "교수님한테 실수로 '엄마'라고 불렀다…",
            "학교 근처에서 역대급 라멘집 발견",
            "우리 고양이가 냉장고 여는 법을 배웠다 😱",
        ]
        fallbacks = fallbacks_ko if lang == 'ko' else fallbacks_en

        try:
            import anthropic
            import os

            api_key = os.environ.get('ANTHROPIC_API_KEY', '')
            if not api_key:
                import random
                placeholder = random.choice(fallbacks)
                cache.set(cache_key, placeholder, 60 * 60 * 24)
                return Response({'placeholder': placeholder})

            client = anthropic.Anthropic(api_key=api_key)

            if lang == 'ko':
                prompt = (
                    "한국 20대 대학생이 친구들에게 가볍게 공유할 만한 오늘의 TMI를 한 문장으로 만들어줘. "
                    "재밌고, 일상적이고, 공감되는 내용으로. 이모지를 하나 넣어줘. "
                    "문장만 출력하고, 따옴표나 설명은 빼줘."
                )
            else:
                prompt = (
                    "Generate a single fun, relatable TMI (Too Much Information) example that a college student "
                    "might share with friends. It should feel casual, light-hearted, and specific. "
                    "Include one emoji. Output only the sentence, no quotes or explanation."
                )

            message = client.messages.create(
                model="claude-haiku-4-20250414",
                max_tokens=80,
                messages=[{"role": "user", "content": prompt}],
            )
            placeholder = message.content[0].text.strip().strip('"').strip("'")
            cache.set(cache_key, placeholder, 60 * 60 * 24)
            return Response({'placeholder': placeholder})

        except Exception:
            import random
            placeholder = random.choice(fallbacks)
            cache.set(cache_key, placeholder, 60 * 60)
            return Response({'placeholder': placeholder})
