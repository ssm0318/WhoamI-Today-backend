from django.apps import apps
from django.conf import settings
from django.contrib.auth import authenticate, logout
from django.core import exceptions
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.db.models import F, Q, Max
from django.http import HttpResponse, HttpResponseNotAllowed
from django.middleware import csrf
from django.shortcuts import get_object_or_404
from django.utils import translation
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from safedelete.models import SOFT_DELETE_CASCADE

from account.models import FriendRequest, FriendGroup
from account.serializers import UserProfileSerializer, \
    UserFriendRequestCreateSerializer, UserFriendRequestUpdateSerializer, \
    UserFriendshipStatusSerializer, AuthorFriendSerializer, \
    UserEmailSerializer, UserPasswordSerializer, UserUsernameSerializer, \
    TodayFriendsSerializer, UserFriendGroupBaseSerializer, UserFriendGroupMemberSerializer, \
    UserFriendGroupOrderSerializer, AddFriendFavoriteHiddenSerializer, FriendDetailSerializer, \
    UserFriendsUpdateSerializer
from adoorback.utils.exceptions import ExistingUsername, LongUsername, InvalidUsername, ExistingEmail, InvalidEmail, NoUsername, WrongPassword
from adoorback.utils.permissions import IsNotBlocked
from adoorback.utils.validators import adoor_exception_handler
from check_in.models import CheckIn
from .email import email_manager
from feed.models import Question
from feed.models import Response as _Response
from feed.serializers import QuestionAnonymousSerializer

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


class CurrentUserFriendDetailList(generics.ListAPIView):
    serializer_class = FriendDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        return self.request.user.friends.all().exclude(hidden=True).order_by('username')


class CurrentUserFriendEditList(generics.ListAPIView):
    serializer_class = FriendDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        return self.request.user.friends.all().order_by('username')


class CurrentUserFriendUpdatedList(generics.ListAPIView):
    serializer_class = FriendDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)

        user = self.request.user
        friends = user.friends.all().exclude(hidden=True)
        friends = User.objects.filter(id__in=[
            friend.id for friend in friends if not User.user_read(user, friend)
        ])

        # sort in recent order
        friends = sorted(friends, key=lambda x: x.most_recent_update(user), reverse=True)

        return friends


class CurrentUserFavoritesList(generics.ListAPIView):
    serializer_class = FriendDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        return self.request.user.favorites.all().order_by('username')


class UserFavoriteAdd(generics.CreateAPIView):
    serializer_class = AddFriendFavoriteHiddenSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        friend_id = serializer.validated_data.get('friend_id')

        if request.user.favorites.filter(id=friend_id).exists():
            return Response({'error': 'Friend is already in favorites.'}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.friends.filter(id=friend_id).exists():
            return Response({'error': 'User is not friend.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_to_add = User.objects.get(id=friend_id)
            self.perform_create(user_to_add)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    def perform_create(self, user_to_add):
        self.request.user.favorites.add(user_to_add)


class UserFavoriteDestroy(generics.DestroyAPIView):
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_destroy(self, obj):
        self.request.user.favorites.remove(obj)


class UserHiddenAdd(generics.CreateAPIView):
    serializer_class = AddFriendFavoriteHiddenSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        friend_id = serializer.validated_data.get('friend_id')

        if request.user.hidden.filter(id=friend_id).exists():
            return Response({'error': 'Friend is already in hidden.'}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.friends.filter(id=friend_id).exists():
            return Response({'error': 'User is not friend.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_to_add = User.objects.get(id=friend_id)
            # Remove the user from favorites if the user is in favorites
            if request.user.favorites.filter(id=friend_id).exists():
                request.user.favorites.remove(user_to_add)
            self.perform_create(user_to_add)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

    def perform_create(self, user_to_add):
        self.request.user.hidden.add(user_to_add)


class CurrentUserFriendsUpdate(generics.UpdateAPIView):
    serializer_class = UserFriendsUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_200_OK)


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
        self.request.user.friends.remove(obj)


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
        friend_request = self.get_object()
        requester = User.objects.get(id=friend_request.requester_id)
        requestee = User.objects.get(id=friend_request.requestee_id)

        serializer.save()

        send_users = []
        if len(requester.friend_ids) == 1:  # 디바이스 노티 설정이 켜져있는지 확인 필요 없을지?
            send_users.append(requester)
        if len(requestee.friend_ids) == 1:
            send_users.append(requestee)

        for user in send_users:
            Notification = apps.get_model('notification', 'Notification')
            admin = User.objects.filter(is_superuser=True).first()

            Notification.objects.create(user=user,
                                        actor=admin,
                                        target=admin,
                                        origin=admin,
                                        message_ko=f"{user.username}님, 투데이 작성을 놓치고 싶지 않다면 알림 설정을 해보세요!",
                                        message_en=f"{user.username}, if you don't want to miss writing today, try setting up notifications!",
                                        redirect_url='/settings')


class TodayFriends(generics.ListAPIView):
    serializer_class = TodayFriendsSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        return self.request.user.friends.all()


class TodayFriend(generics.ListAPIView):
    serializer_class = TodayFriendsSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        selected_user_id = self.kwargs.get('pk')
        current_user = self.request.user
        if selected_user_id in current_user.user_report_blocked_ids:
            raise PermissionDenied("current user blocked this user")
        if selected_user_id not in current_user.friend_ids:
            raise PermissionDenied("you're not his/her friend")
        return User.objects.filter(id=selected_user_id)


class UserFriendGroupList(generics.ListAPIView):
    """
    List all friend groups of a user
    """
    queryset = FriendGroup.objects.all()
    serializer_class = UserFriendGroupBaseSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        return FriendGroup.objects.filter(user=self.request.user).order_by('order')


class UserFriendGroupCreate(generics.CreateAPIView):
    """
    Create a new friend group.
    """
    queryset = FriendGroup.objects.all()
    serializer_class = UserFriendGroupMemberSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        max_order = user.friend_groups.aggregate(max_order=Max('order'))['max_order']
        name = self.request.data.get('name')
        friend_ids = self.request.data.get('friends', [])
        friends = [get_object_or_404(User, id=friend_id) for friend_id in friend_ids]

        serializer.save(user=user, name=name, order=max_order+1, friends=friends)


class UserFriendGroupDetail(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or destroy a friend group.
    """
    queryset = FriendGroup.objects.all()
    serializer_class = UserFriendGroupMemberSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        friend_group = FriendGroup.objects.get(id=self.kwargs.get('pk'))
        if friend_group.user != self.request.user:
            raise exceptions.PermissionDenied("You cannot view other users' friend groups.")
        return friend_group

    def update(self, request, *args, **kwargs):
        friend_group = self.get_object()

        if 'friends' in request.data or 'name' in request.data:
            serializer = self.get_serializer(instance=friend_group, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()

            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response({"detail": "No data provided for update."}, status=status.HTTP_400_BAD_REQUEST)

    @transaction.atomic
    def perform_destroy(self, obj):
        order_to_delete = obj.order
        obj.delete(force_policy=SOFT_DELETE_CASCADE)
        # update order of remaining FriendGroup instances
        FriendGroup.objects.filter(user=self.request.user).filter(order__gt=order_to_delete) \
            .update(order=F('order') - 1)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserFriendGroupOrderUpdate(generics.UpdateAPIView):
    queryset = FriendGroup.objects.all()
    serializer_class = UserFriendGroupOrderSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def patch(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ids = serializer.validated_data['ids']
        order_mapping = {group_id: idx+1 for idx, group_id in enumerate(ids)}

        user = self.request.user
        queryset = FriendGroup.objects.filter(user=user)

        for group in queryset:
            try:
                group.order = order_mapping[group.id]
            except KeyError:
                raise ValidationError({'ids': "'ids' must include all id's of a user's friend groups."})

        FriendGroup.objects.bulk_update(queryset, ['order'])
        return Response("Friend group orders updated.", status=status.HTTP_200_OK)
