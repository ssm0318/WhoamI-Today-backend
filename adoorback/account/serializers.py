import secrets

from django.db import transaction
from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers
from django.urls import reverse
from django.utils import translation
from rest_framework_simplejwt.serializers import TokenObtainSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.settings import api_settings
from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from account.models import FriendRequest
from adoorback.settings.base import BASE_URL
from adoorback.utils.exceptions import ExistingEmail, ExistingUsername

from django_countries.serializers import CountryFieldMixin

User = get_user_model()


class UserProfileSerializer(CountryFieldMixin, serializers.HyperlinkedModelSerializer):
    """
    Serializer for auth and profile update
    """
    url = serializers.HyperlinkedIdentityField(view_name='user-detail', read_only=True, lookup_field='username')

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password',
                  'profile_pic', 'question_history', 'url',
                  'profile_image', 'gender', 'date_of_birth',
                  'ethnicity', 'nationality', 'research_agreement',
                  'signature', 'date_of_signature']
        extra_kwargs = {'password': {'write_only': True}}

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def validate(self, attrs):
        user = User(**attrs)
        errors = dict() 
        try:
            validate_password(password=attrs.get('password'), user=user)

        except ValidationError as e:
            errors['password'] = [list(e.messages)[0]]

        if errors:
            raise serializers.ValidationError(errors)
        return super(UserProfileSerializer, self).validate(attrs)


class UserEmailSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email']

    def validate(self, attrs):
        for user in User.deleted_objects.all():
            if attrs['email'] == user.email:
                raise ExistingEmail()
        return super(UserEmailSerializer, self).validate(attrs)


class UserPasswordSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['password']

    def validate(self, attrs):
        user = User(**attrs)
        errors = dict()
        try:
            validate_password(password=attrs.get('password'), user=user)

        except ValidationError as e:
            errors['password'] = [list(e.messages)[0]]

        if errors:
            raise serializers.ValidationError(errors)
        return super(UserPasswordSerializer, self).validate(attrs)


class UserUsernameSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username']

    def validate(self, attrs):
        for user in User.deleted_objects.all():
            if attrs['username'] == user.username:
                raise ExistingUsername()
        return super(UserUsernameSerializer, self).validate(attrs)


class AuthorFriendSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField(read_only=True)

    def get_url(self, obj):
        return BASE_URL + reverse('user-detail', kwargs={'username': obj.username})
    class Meta:
        model = User
        fields = ['id', 'username', 'profile_pic', 'url', 'profile_image']


class AuthorAnonymousSerializer(serializers.ModelSerializer):
    color_hex = serializers.SerializerMethodField(read_only=True)

    def get_color_hex(self, obj):
        author_hash = obj.id * secrets.randbelow(63872) * secrets.randbelow(98574)
        return '#{0:06X}'.format(author_hash % 16777215)  # mod max color HEX

    class Meta:
        model = User
        fields = ['color_hex']


class UserFriendRequestCreateSerializer(serializers.ModelSerializer):
    requester_id = serializers.IntegerField()
    requestee_id = serializers.IntegerField()
    accepted = serializers.BooleanField(allow_null=True, required=False)
    requester_detail = serializers.SerializerMethodField(read_only=True)

    def get_requester_detail(self, obj):
        return AuthorFriendSerializer(User.objects.get(id=obj.requester_id)).data
    
    def validate(self, data):
        if data.get('requester_id') == data.get('requestee_id'):
            raise serializers.ValidationError('본인과는 친구가 될 수 없어요...')
        return data

    class Meta:
        model = FriendRequest
        fields = ['requester_id', 'requestee_id', 'accepted', 'requester_detail']



class UserFriendRequestUpdateSerializer(serializers.ModelSerializer):
    requester_id = serializers.IntegerField(required=False)
    requestee_id = serializers.IntegerField(required=False)
    accepted = serializers.BooleanField(required=True)

    def validate(self, data):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError("이 필드는 뭘까요...: {}".format(", ".join(unknown)))
        if self.instance.accepted is not None:
            raise serializers.ValidationError("이미 friend request에 응답하셨습니다...")
        return data

    class Meta:
        model = FriendRequest
        fields = UserFriendRequestCreateSerializer.Meta.fields


class UserFriendshipStatusSerializer(AuthorFriendSerializer):
    sent_friend_request_to = serializers.SerializerMethodField(read_only=True)
    received_friend_request_from = serializers.SerializerMethodField(read_only=True)
    are_friends = serializers.SerializerMethodField(read_only=True, allow_null=True)

    def get_received_friend_request_from(self, obj):
        return self.context.get('request', None).user.id in \
               list(obj.sent_friend_requests.values_list('requestee_id', flat=True))

    def get_sent_friend_request_to(self, obj):
        return self.context.get('request', None).user.id in \
               list(obj.received_friend_requests.values_list('requester_id', flat=True))

    def get_are_friends(self, obj):
        user = self.context.get('request', None).user
        if user == obj:
            return None
        return User.are_friends(user, obj)

    class Meta(AuthorFriendSerializer.Meta):
        model = User
        fields = AuthorFriendSerializer.Meta.fields + ['sent_friend_request_to',
                                                       'received_friend_request_from',
                                                       'are_friends']
