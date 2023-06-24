import json
# import sentry_sdk

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model, authenticate, logout
from django.core import exceptions
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseBadRequest
from django.middleware import csrf
from django.utils import translation
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenViewBase
from safedelete.models import SOFT_DELETE_CASCADE

from account.models import FriendRequest
from account.serializers import UserProfileSerializer, \
    UserFriendRequestCreateSerializer, UserFriendRequestUpdateSerializer, \
    UserFriendshipStatusSerializer, AuthorFriendSerializer, \
    UserEmailSerializer, UserPasswordSerializer, UserUsernameSerializer

from adoorback.utils.exceptions import ExistingUsername, LongUsername, InvalidUsername, ExistingEmail, InvalidEmail, NoUsername, WrongPassword
from adoorback.utils.permissions import IsNotBlocked
from adoorback.utils.validators import adoor_exception_handler
from .email import email_manager
from feed.models import Question
from feed.models import Response as ResponseModel
from feed.serializers import QuestionAnonymousSerializer
import feed.serializers as fs
from moment.models import Moment
import moment.serializers as ms

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
                key = settings.SIMPLE_JWT['AUTH_COOKIE'], 
                value = access_token, 
                max_age = settings.SIMPLE_JWT['AUTH_COOKIE_MAX_AGE'],
                secure = settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
                httponly = settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
                samesite = settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
            )
            csrf.get_token(request)
            return response
        else:
            raise WrongPassword()


class UserLogout(APIView):
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
            raise e

        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)

        response = Response(serializer.data, status=201, headers=headers)     
        user = User.objects.get(username=request.data.get('username'))
        access_token = get_access_token_for_user(user)
        response.set_cookie(
            key = settings.SIMPLE_JWT['AUTH_COOKIE'], 
            value = access_token, 
            max_age = settings.SIMPLE_JWT['AUTH_COOKIE_MAX_AGE'],
            secure = settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
            httponly = settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
            samesite = settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
        )
        csrf.get_token(request)
        return response


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
        if user:
            email_manager.send_reset_password_email(user)
            
        return HttpResponse(status=200) # whether email is valid or not, response will be always success-response


class ResetPasswordWithToken(generics.UpdateAPIView):
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
        try:
            validate_password(password=raw_password, user=user)
        except exceptions.ValidationError as e:
            raise e
        user.set_password(raw_password)
        user.save()


class UserPasswordConfirm(APIView):
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
        

class ResetPassword(generics.UpdateAPIView):
    serializer_class = UserProfileSerializer
    queryset = User.objects.all()

    def get_exception_handler(self):
        return adoor_exception_handler

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        self.update_password(user, self.request.data['password'])
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

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(settings.SIMPLE_JWT['AUTH_COOKIE'])
        return response


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
        return FriendRequest.objects.filter(requestee=self.request.user).filter(accepted__isnull=True)

    @transaction.atomic
    def perform_create(self, serializer):
        if int(self.request.data.get('requester_id')) != int(self.request.user.id):
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


class TodayFriends(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    
    def get_date(self):
        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        day = self.kwargs.get('day')
        formatted_date = f"{year}-{month:02d}-{day:02d}"
        
        return formatted_date

    def get_exception_handler(self):
        return adoor_exception_handler

    def list(self, request, *args, **kwargs):    
        response_queryset = self.filter_queryset(
            ResponseModel.objects
            .filter(date=self.get_date(), author__in=self.request.user.friends.all())
            .order_by('author')
        )

        self.serializer_class = fs.ResponseFriendSerializer
        response_serializer = self.get_serializer(response_queryset, many=True)
        response_data = response_serializer.data
        
        friends_with_responses = []
        last_author_id = 0
        author_ids = []

        for response in response_data:
            author = response["author_detail"]
            copied_response = response.copy()
            del copied_response["author_detail"]
            author_id = author["id"]

            if author_id != last_author_id:
                copied_author = author.copy()
                copied_author["responses"] = [copied_response]
                friends_with_responses.append(copied_author)
                last_author_id = author_id
                author_ids.append(author_id)
            else:
                friends_with_responses[-1]["responses"].append(copied_response)
        
        moment_queryset = self.filter_queryset(
            Moment.objects
            .filter(date=self.get_date(), author__in=self.request.user.friends.all())
            .order_by('author')
        )

        self.serializer_class = ms.MomentDetailSerializer
        moment_serializer = self.get_serializer(moment_queryset, many=True)
        moment_data = moment_serializer.data
        
        for moment in moment_data:
            author = moment["author_detail"]
            copied_moment = moment.copy()
            del copied_moment["author_detail"]
            author_id = author["id"]

            if author_id not in author_ids:
                copied_author = author.copy()
                copied_author["moment"] = copied_moment
                friends_with_responses.append(copied_author)
            else:
                idx = author_ids.index(author_id)
                friends_with_responses[idx]["moment"] = copied_moment
                
        for friend in friends_with_responses:
            if "responses" in friend:
                responses = friend["responses"].copy()
                del friend["responses"]
                combined_responses = []
                last_question_id = 0

                for response in responses:
                    question = response["question"]
                    copied_response = response.copy()
                    del copied_response["question"]

                    if question["id"] != last_question_id:
                        copied_question = question.copy()
                        copied_question["responses"] = [copied_response]
                        combined_responses.append(copied_question)
                        last_question_id = question["id"]
                    else:
                        combined_responses[-1]["responses"].append(copied_response)
                friend["responses"] = combined_responses
        
        return Response(friends_with_responses)
        