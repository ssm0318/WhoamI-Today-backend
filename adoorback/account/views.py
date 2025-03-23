from datetime import timedelta
import json
import uuid

from django.apps import apps
from django.conf import settings
from django.contrib.auth import authenticate, logout
from django.core import exceptions
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction, IntegrityError
from django.db.models import Q, Case, When, Value, IntegerField
from django.db.models.functions import Lower
from django.http import HttpResponse, HttpResponseNotAllowed, Http404
from django.middleware import csrf
from django.shortcuts import get_object_or_404
from django.utils import translation, timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from safedelete.models import SOFT_DELETE_CASCADE

from .email import email_manager
from .models import Subscription, Connection, AppSession
from account.models import FriendRequest, BlockRec
from account.serializers import (CurrentUserSerializer, \
                                 UserFriendRequestCreateSerializer, UserFriendRequestUpdateSerializer, \
                                 UserFriendshipStatusSerializer, \
                                 UserEmailSerializer, UserUsernameSerializer, \
                                 FriendListSerializer, \
                                 UserFriendsUpdateSerializer, UserMinimumSerializer, BlockRecSerializer, \
                                 UserFriendRequestSerializer, UserPasswordSerializer, UserProfileSerializer, \
                                 AppSessionSerializer, FriendFriendListSerializer)
from adoorback.utils.content_types import get_generic_relation_type, get_friend_request_type
from adoorback.utils.exceptions import ExistingUsername, LongUsername, InvalidUsername, ExistingEmail, InvalidEmail, \
    NoUsername, WrongPassword, ExistingUsername
from adoorback.utils.validators import adoor_exception_handler
from note.models import Note
from note.serializers import NoteSerializer, DefaultFriendNoteSerializer
from notification.models import NotificationActor
from qna.models import ResponseRequest
from qna.models import Response as _Response
from tracking.utils import clean_session_key


User = get_user_model()


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

    def get_exception_handler(self):
        return adoor_exception_handler

    def post(self, request, format=None):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)

        data = request.data
        response = Response()
        username = data.get('username', None)
        password = data.get('password', None)
        try:
            user = User.objects.get(Q(username=username) | Q(email=username))
        except:
            raise NoUsername()

        user = authenticate(username=username, password=password)
        if user is not None:
            access_token = get_access_token_for_user(user)
            response.set_cookie(
                key=settings.SIMPLE_JWT['AUTH_COOKIE'],
                value=access_token,
                max_age=settings.SIMPLE_JWT['AUTH_COOKIE_MAX_AGE'],
                secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
                # FIXME: 원활한 테스트를 위해 일단 XSS 보안 이슈는 스킵
                # httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
                samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
            )
            csrf.get_token(request)
            return response
        else:
            raise WrongPassword()


class UserLogout(APIView):

    def get_exception_handler(self):
        return adoor_exception_handler

    def get(self, request):
        logout(request)
        response = Response()
        response.delete_cookie(settings.SIMPLE_JWT['AUTH_COOKIE'])
        return response


class UserEmailCheck(generics.CreateAPIView):
    serializer_class = UserEmailSerializer
    parser_classes = (MultiPartParser, FormParser)

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
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

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
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

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
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


class UserSignup(generics.CreateAPIView):
    serializer_class = CurrentUserSerializer
    parser_classes = (MultiPartParser, FormParser)

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            raise e

        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)

        response = Response(serializer.data, status=201, headers=headers)
        user = User.objects.get(username=request.data.get('username'))
        access_token = get_access_token_for_user(user)
        response.set_cookie(
            key=settings.SIMPLE_JWT['AUTH_COOKIE'],
            value=access_token,
            max_age=settings.SIMPLE_JWT['AUTH_COOKIE_MAX_AGE'],
            secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
            # FIXME: 원활한 테스트를 위해 일단 보안 이슈는 스킵
            # httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
            samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
        )
        csrf.get_token(request)
        return response


class SendResetPasswordEmail(generics.CreateAPIView):
    serializer_class = CurrentUserSerializer

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        return User.objects.filter(email=self.request.data['email']).first()

    def post(self, request, *args, **kwargs):
        user = self.get_object()
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
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
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)

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
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)

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

        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)

        response = Response()
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

        qs = User.objects.none()
        if query:
            # username starts with query
            start_users = User.objects.filter(username__startswith=query).order_by('username').exclude(id=user_id)
            friend_start_ids = list(start_users.filter(id__in=friend_ids).values_list('id', flat=True))
            nonfriend_start_ids = list(start_users.exclude(id__in=friend_ids).values_list('id', flat=True))

            # email starts with query
            email_start_users = User.objects.filter(email__startswith=query).order_by('email').exclude(id=user_id)
            friend_email_start_ids = list(email_start_users.filter(id__in=friend_ids).values_list('id', flat=True))
            nonfriend_email_start_ids = list(email_start_users.exclude(id__in=friend_ids).values_list('id', flat=True))

            # username contains query
            contain_users = User.objects.filter(username__icontains=query).order_by('username').exclude(id=user_id)
            friend_contain_ids = list(contain_users.filter(id__in=friend_ids).values_list('id', flat=True))
            nonfriend_contain_ids = list(contain_users.exclude(id__in=friend_ids).values_list('id', flat=True))

            # email contains query
            email_contain_users = User.objects.filter(email__icontains=query).order_by('email').exclude(id=user_id)
            friend_email_contain_ids = list(email_contain_users.filter(id__in=friend_ids).values_list('id', flat=True))
            nonfriend_email_contain_ids = list(email_contain_users.exclude(id__in=friend_ids).values_list('id', flat=True))

            # all friend users
            qs_ids = friend_start_ids + friend_email_start_ids + friend_contain_ids + friend_email_contain_ids

            # only 20 non-friend users
            nonfriend_qs_ids = nonfriend_start_ids[:20]
            if len(nonfriend_qs_ids) < 20:
                nonfriend_qs_ids += nonfriend_email_start_ids[:20 - len(nonfriend_qs_ids)]
            if len(nonfriend_qs_ids) < 20:
                nonfriend_qs_ids += nonfriend_contain_ids[:20 - len(nonfriend_qs_ids)]
            if len(nonfriend_qs_ids) < 20:
                nonfriend_qs_ids += nonfriend_email_contain_ids[:20 - len(nonfriend_qs_ids)]

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
        all_notes = Note.objects.filter(author__username=self.kwargs.get('username'))
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
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        user = self.request.user
        all_responses = _Response.objects.filter(author__username=self.kwargs.get('username')).order_by('-created_at')
        response_ids = [response.id for response in all_responses if response.is_audience(user)]
        return _Response.objects.filter(id__in=response_ids)


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
        if serializer.is_valid(raise_exception=True):
            if 'username' in self.request.data:
                if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
                    lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
                    translation.activate(lang)

                new_username = serializer.validated_data.get('username')
                # check if @ or . is included in username
                if '@' in new_username or '.' in new_username:
                    raise InvalidUsername()
                # check if username exceeds 20 letters
                if len(new_username) > 20:
                    raise LongUsername()
                # check if username exists
                if new_username and User.objects.filter(username=new_username).exclude(id=self.request.user.id).exists():
                    raise ExistingUsername()
                
            persona = self.request.data.get('persona')
            if persona:
                if isinstance(persona, str):
                    try:
                        persona = json.loads(persona)
                    except json.JSONDecodeError:
                        raise serializers.ValidationError({
                            "persona": ["persona must be a valid JSON list."]
                        })
                if not isinstance(persona, list):
                    raise serializers.ValidationError({
                        "persona": ["persona must be a list."]
                    })
                from .models import PERSONA_CHOICES
                invalid_choices = [p for p in persona if p not in dict(PERSONA_CHOICES)]
                if invalid_choices:
                    raise serializers.ValidationError({
                        "persona": [f"Invalid choices: {invalid_choices}"]
                    })
                serializer.validated_data['persona'] = persona

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

            obj = serializer.save()

            # update notification redirect url when username changes
            if 'username' in self.request.data:
                # "friend request recieved" notification
                friend_request_ct = get_friend_request_type()
                self.request.user.friendship_originated_notis.filter(
                    target_type=friend_request_ct
                ).update(
                    redirect_url=f"/users/{serializer.validated_data.get('username')}"
                )
                
                # "became friends" notification
                Notification = apps.get_model('notification', 'Notification')
                notis_to_change = Notification.objects.filter(redirect_url=f'/users/{self.request.user.username}')
                notis_to_change.update(
                    redirect_url=f"/users/{serializer.validated_data.get('username')}"
                )
            
            updating_data = list(self.request.data.keys())
            if len(updating_data) == 1 and updating_data[0] == 'question_history':
                Notification = apps.get_model('notification', 'Notification')
                admin = User.objects.filter(is_superuser=True).first()

                noti = Notification.objects.create(user=obj,
                                                   target=admin,
                                                   origin=admin,
                                                   message_ko=f"{obj.username}님, 질문 선택을 완료하셨네요! 이제 오늘의 질문들을 확인해볼까요?",
                                                   message_en=f"Great choice, {obj.username}! Now, let's check out today's questions!",
                                                   redirect_url='/questions')
                NotificationActor.objects.create(user=admin, notification=noti)


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
        instance.delete(force_policy=SOFT_DELETE_CASCADE)

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


class CurrentUserResponseList(generics.ListAPIView):
    queryset = _Response.objects.all()
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_serializer_class(self):
        from qna.serializers import ResponseSerializer
        return ResponseSerializer

    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        user = self.request.user
        return _Response.objects.filter(author=user).order_by('-created_at')


class ReceivedResponseRequestList(generics.ListAPIView):
    queryset = ResponseRequest.objects.all()
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_serializer_class(self):
        from qna.serializers import ReceivedResponseRequestSerializer
        return ReceivedResponseRequestSerializer

    def get_queryset(self):
        user = self.request.user
        thirty_days_ago = timezone.now() - timedelta(days=30)
        return ResponseRequest.objects.filter(requestee=user, created_at__gte=thirty_days_ago).order_by('-created_at')


class FriendList(generics.ListAPIView):
    serializer_class = FriendListSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)

        user = self.request.user
        friends = user.connected_users

        query_type = self.request.query_params.get('type')

        if query_type == 'all':
            return friends.order_by('username')
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
            
        connection.update_friendship_level(request.user, new_choice, update_past_posts)
        return Response({'status': 'Friendship level updated'})


class FriendFriendList(generics.ListAPIView):
    serializer_class = FriendFriendListSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)

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
        serializer.is_valid(raise_exception=True)  # `accepted` 필드 검사
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
            potential_friends = friend.connected_users.filter(user_group=user.user_group) \
                .exclude(id__in=user_friend_ids) \
                .exclude(id=user_id).exclude(id__in=user_block_rec_ids) \
                .exclude(id__in=sent_friend_request_ids) \
                .exclude(id__in=received_friend_request_ids) \
                .exclude(is_superuser=True)

            for potential_friend in potential_friends:
                if potential_friend.id not in mutual_friends_count_dict:
                    mutual_friends_count_dict[potential_friend.id] = 1
                mutual_friends_count_dict[potential_friend.id] += 1

        # Sort the by number of mutual friends
        sorted_friends = sorted(mutual_friends_count_dict.items(), key=lambda x: x[1], reverse=True)[:25]
        sorted_friend_ids = [friend_id for friend_id, _ in sorted_friends]

        if not sorted_friend_ids:
            # If there is no user to recommend, recommend 3 random users
            potential_random_users = User.objects.filter(user_group=user.user_group) \
                .exclude(id=user_id) \
                .exclude(id__in=user_friend_ids) \
                .exclude(id__in=user_block_rec_ids) \
                .exclude(id__in=sent_friend_request_ids) \
                .exclude(id__in=received_friend_request_ids) \
                .exclude(is_superuser=True)

            random_users = potential_random_users.order_by("?")[:3]
            return random_users

        recommended_friends = User.objects.filter(id__in=sorted_friend_ids) \
            .order_by(Case(*[When(id=id_, then=pos) for pos, id_ in enumerate(sorted_friend_ids)], default=0))

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

        notes = Note.objects.filter(author=target_user).exclude(readers=request.user)
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
        ).exclude(author_id__in=blocked_user_ids).select_related('author')
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

        return self.get_paginated_response(serialized_data) if page is not None else Response(serialized_data)


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
