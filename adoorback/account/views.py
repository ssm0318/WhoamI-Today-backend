import json
# import sentry_sdk

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseBadRequest
from django.utils import translation
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.views import TokenViewBase
from safedelete.models import SOFT_DELETE_CASCADE

from account.models import FriendRequest
from account.serializers import UserProfileSerializer, \
    UserFriendRequestCreateSerializer, UserFriendRequestUpdateSerializer, \
    UserFriendshipStatusSerializer, AuthorFriendSerializer, CustomTokenObtainPairSerializer

from feed.serializers import QuestionAnonymousSerializer
from feed.models import Question
from adoorback.utils.validators import adoor_exception_handler
from.email import email_manager
from adoorback.utils.permissions import IsNotBlocked
from rest_framework.parsers import MultiPartParser, FormParser
from adoorback.utils.exceptions import ExistingUsername, LongUsername, InvalidUsername, ExistingEmail, InvalidEmail, InActiveUser

User = get_user_model()

@transaction.atomic
@ensure_csrf_cookie
def token_anonymous(request):
    if request.method == 'GET':
        return HttpResponse(status=204)
    else:
        return HttpResponseNotAllowed(['GET'])


class CustomTokenObtainPairView(TokenViewBase):
    """
    https://github.com/jazzband/djangorestframework-simplejwt/issues/368#issuecomment-778686307
    Takes a set of user credentials and returns an access and refresh JSON web
    token pair to prove the authentication of those credentials.

    Returns HTTP 406 when user is inactive and HTTP 401 when login credentials are invalid.
    """
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class UserSignup(generics.CreateAPIView):
    serializer_class = UserProfileSerializer
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
                    user = User.objects.get(username=request.data['username'])
                    if not user.is_active:
                        raise InActiveUser()
                    raise ExistingUsername()
                if 'invalid' in e.get_codes()['username']:
                    raise InvalidUsername()
                if 'max_length' in e.get_codes()['username']:
                    raise LongUsername()
            if 'email' in e.detail:
                if 'unique' in e.get_codes()['email']:
                    raise ExistingEmail()
                if 'invalid' in e.get_codes()['email']:
                    raise InvalidEmail()
            raise e

        self.perform_create(serializer)

        user = User.objects.get(username=request.data.get('username'))
        email_manager.send_verification_email(user)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=201, headers=headers)

    @transaction.atomic
    def perform_create(self, serializer):
        obj = serializer.save()
        Notification = apps.get_model('notification', 'Notification')
        admin = User.objects.filter(is_superuser=True).first()

        Notification.objects.create(user=obj,
                                    actor=admin,
                                    target=admin,
                                    origin=admin,
                                    message_ko=f"{obj.username}님, 반갑습니다! :) 먼저 익명피드를 둘러볼까요?",
                                    message_en=f"Welcome {obj.username}! :) Start with looking around the anonymous feed.",
                                    redirect_url='/anonymous')


class UserActivate(generics.UpdateAPIView):
    queryset = User.objects.all()
    serializer_class = UserProfileSerializer

    def get_exception_handler(self):
        print(self.request.headers)
        return adoor_exception_handler

    def update(self, request, *args, **kwargs):
        token = self.kwargs.get('token')
        user = self.get_object()
        if email_manager.check_activate_token(user, token):
            self.activate(user)
            return HttpResponse(status=204)
        else:
            return HttpResponse(status=400)

    @transaction.atomic
    def activate(self, user):
        user.is_active = True
        user.save()


class SendResetPasswordEmail(generics.CreateAPIView):
    serializer_class = UserProfileSerializer

    def get_exception_handler(self):
        return adoor_exception_handler
    
    def get_object(self):
        return User.objects.filter(email=self.request.data['email']).first()

    def post(self, request, *args, **kwargs):
        user = self.get_object()
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        if user and user.is_active:
            email_manager.send_reset_password_email(user)
            
        return HttpResponse(status=200) # whether email is valid or not, response will be always success-response


class ResetPassword(generics.UpdateAPIView):
    serializer_class = UserProfileSerializer
    queryset = User.objects.all()

    def get_exception_handler(self):
        return adoor_exception_handler

    def update(self, request, *args, **kwargs):
        token = self.kwargs.get('token')
        user = self.get_object()
        if email_manager.check_reset_password_token(user, token):
            self.update_password(user, self.request.data['password'])
            return HttpResponse(status=200)
        return HttpResponse(status=400)

    @transaction.atomic
    def update_password(self, user, raw_password):
        user.set_password(raw_password)
        user.save()


class SignupQuestions(generics.ListAPIView):
    queryset = Question.objects.order_by('?')[:10]
    serializer_class = QuestionAnonymousSerializer
    model = serializer_class.Meta.model
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler


class UserList(generics.ListAPIView):
    queryset = User.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        queryset = User.objects.filter(id=self.request.user.id)
        if self.request.user.is_superuser:
            queryset = User.objects.all()
        return queryset

class CurrentUserDelete(generics.DestroyAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

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

class CurrentUserFriendList(generics.ListAPIView):
    serializer_class = AuthorFriendSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        return self.request.user.friends.all()


class CurrentUserProfile(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        # since the obtained user object is the authenticated user,
        # no further permission checking unnecessary
        return User.objects.get(id=self.request.user.id)

    @transaction.atomic
    def perform_update(self, serializer):
        if serializer.is_valid(raise_exception=True):
            serializer.save()
        updating_data = list(self.request.data.keys())
        if len(updating_data) == 1 and updating_data[0] == 'question_history':
            obj = serializer.save()
            Notification = apps.get_model('notification', 'Notification')
            admin = User.objects.filter(is_superuser=True).first()

            Notification.objects.create(user=obj,
                                        actor=admin,
                                        target=admin,
                                        origin=admin,
                                        message_ko=f"{obj.username}님, 질문 선택을 완료해주셨네요 :) 그럼 오늘의 질문들을 둘러보러 가볼까요?",
                                        message_en=f"Nice job selecting your questions {obj.username} :) How about looking around today's questions?",
                                        redirect_url='/questions')


class UserDetail(generics.RetrieveAPIView):
    queryset = User.objects.all()
    serializer_class = UserFriendshipStatusSerializer
    permission_classes = [IsAuthenticated, IsNotBlocked]
    lookup_field = 'username'

    def get_exception_handler(self):
        return adoor_exception_handler


class UserSearch(generics.ListAPIView):
    serializer_class = UserFriendshipStatusSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        query = self.request.GET.get('query')
        queryset = User.objects.none()
        if query:
            queryset = User.objects.filter(
                username__icontains=self.request.GET.get('query'))
        return queryset.order_by('username')


class UserFriendDestroy(generics.DestroyAPIView):
    """
    Destroy a friendship.
    """
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_destroy(self, obj):
        obj.friends.remove(self.request.user)


class UserFriendRequestList(generics.ListCreateAPIView):
    queryset = FriendRequest.objects.all()
    serializer_class = UserFriendRequestCreateSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        return FriendRequest.objects.filter(requestee=self.request.user)

    @transaction.atomic
    def perform_create(self, serializer):
        if self.request.data.get('requester_id') != self.request.user.id:
            raise PermissionDenied("requester가 본인이 아닙니다...")
        serializer.save(accepted=None)


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


class UserFriendRequestUpdate(generics.UpdateAPIView):
    serializer_class = UserFriendRequestUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        # since the requestee is the authenticated user, no further permission checking unnecessary
        return FriendRequest.objects.get(requester_id=self.kwargs.get('pk'),
                                         requestee_id=self.request.user.id)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)  # check `accepted` field
        self.perform_update(serializer)
        return Response(serializer.data)

    @transaction.atomic
    def perform_update(self, serializer):
        return serializer.save()
