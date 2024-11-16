from django.db import transaction
from django.db.models import Count, Q
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import serializers
from django.urls import reverse
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from account.models import FriendRequest, BlockRec
from adoorback.utils.exceptions import ExistingEmail, ExistingUsername
from check_in.models import CheckIn
from note.models import Note
from qna.models import Response
from notification.models import Notification

from django_countries.serializers import CountryFieldMixin

User = get_user_model()


class CurrentUserSerializer(CountryFieldMixin, serializers.HyperlinkedModelSerializer):
    url = serializers.SerializerMethodField(read_only=True)
    unread_noti = serializers.SerializerMethodField(read_only=True)

    def get_url(self, obj):
        return settings.BASE_URL + reverse('user-detail', kwargs={'username': obj.username})

    def get_unread_noti(self, obj):
        unread_notis = Notification.objects.filter(user=obj, is_read=False)
        return True if unread_notis else False

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password',
                  'profile_pic', 'question_history', 'url',
                  'profile_image', 'gender', 'date_of_birth',
                  'ethnicity', 'nationality', 'research_agreement', 'pronouns', 'bio',
                  'signature', 'date_of_signature', 'unread_noti', 'noti_time', 'timezone']
        extra_kwargs = {'password': {'write_only': True}}

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def validate(self, attrs):
        if self.partial:
            return super(CurrentUserSerializer, self).validate(attrs)
        user = User(**attrs)
        errors = dict()
        try:
            validate_password(password=attrs.get('password'), user=user)

        except ValidationError as e:
            errors['password'] = [list(e.messages)[0]]

        if errors:
            raise serializers.ValidationError(errors)
        return super(CurrentUserSerializer, self).validate(attrs)


class UserMinimalSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField(read_only=True)

    def get_url(self, obj):
        return settings.BASE_URL + reverse('user-detail', kwargs={'username': obj.username})

    class Meta:
        model = User
        fields = ['id', 'username', 'profile_pic', 'url', 'profile_image']


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


class UserEmailSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email']


class UserUsernameSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username']


class UserProfileSerializer(UserMinimalSerializer):
    check_in = serializers.SerializerMethodField(read_only=True)
    is_favorite = serializers.SerializerMethodField(read_only=True)
    mutuals = serializers.SerializerMethodField(read_only=True)
    are_friends = serializers.SerializerMethodField(read_only=True)
    sent_friend_request_to = serializers.SerializerMethodField(read_only=True)
    received_friend_request_from = serializers.SerializerMethodField(read_only=True)

    def get_is_favorite(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj in request.user.favorites.all()
        return False

    def get_check_in(self, obj):
        from check_in.serializers import CheckInBaseSerializer
        user = self.context.get('request', None).user
        check_in = obj.check_in_set.filter(is_active=True).first()
        if check_in and CheckIn.is_audience(check_in, user):
            return CheckInBaseSerializer(check_in, read_only=True, context=self.context).data
        return {}

    def get_mutuals(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            current_user_connections = set(request.user.connected_user_ids)
            obj_user_connections = set(obj.connected_user_ids)

            mutual_connections = current_user_connections & obj_user_connections
            mutual_users = User.objects.filter(id__in=mutual_connections)
            return UserMinimalSerializer(mutual_users, many=True).data
        return {}

    def get_are_friends(self, obj):  # does not mean 'friend' in friend & follower, it means connection
        user = self.context.get('request', None).user
        if user == obj:
            return None
        return user.is_connected(obj)

    def get_received_friend_request_from(self, obj):
        user = self.context.get('request').user
        return user.id in obj.sent_friend_requests.filter(accepted__isnull=True).values_list('requestee_id', flat=True)

    def get_sent_friend_request_to(self, obj):
        user = self.context.get('request').user
        return user.id in obj.received_friend_requests.exclude(accepted=True).values_list('requester_id', flat=True)

    class Meta(UserMinimalSerializer.Meta):
        model = User
        fields = UserMinimalSerializer.Meta.fields + ['check_in', 'is_favorite', 'mutuals', 
                                                      'are_friends', 'sent_friend_request_to', 'received_friend_request_from',
                                                      'pronouns', 'bio']


class FriendListSerializer(UserMinimalSerializer):
    url = serializers.SerializerMethodField(read_only=True)
    is_favorite = serializers.SerializerMethodField(read_only=True)
    is_hidden = serializers.SerializerMethodField(read_only=True)
    current_user_read = serializers.SerializerMethodField(read_only=True)
    unread_cnt = serializers.SerializerMethodField(read_only=True)
    track_id = serializers.SerializerMethodField(read_only=True)
    description = serializers.SerializerMethodField(read_only=True)

    def get_url(self, obj):
        return settings.BASE_URL + reverse('user-detail', kwargs={'username': obj.username})

    def get_is_favorite(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj in request.user.favorites.all()
        return False

    def get_is_hidden(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj in request.user.hidden.all()
        return False

    def get_current_user_read(self, obj):
        from check_in.serializers import CheckInBaseSerializer
        responses = self.responses(obj)
        notes = self.notes(obj)
        check_in = self.check_in(obj)
        if check_in:
            check_in_data = CheckInBaseSerializer(check_in, read_only=True, context=self.context).data
        else:
            check_in_data = {}

        current_user_read = not any(not response['current_user_read'] for response in responses) \
                            and not any(not note['current_user_read'] for note in notes) \
                            and not (check_in_data and not check_in_data['current_user_read'])
        return current_user_read
    
    def get_unread_cnt(self, obj):
        from chat.models import ChatRoom
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            user = request.user
            chat_room = ChatRoom.objects.filter(users__in=[user, obj]).annotate(user_count=Count('users')).filter(user_count=2).first()
            if chat_room:
                return chat_room.unread_cnt(user)
        return 0

    def check_in(self, obj):
        user = self.context.get('request', None).user
        check_in = obj.check_in_set.filter(is_active=True).first()
        if check_in and CheckIn.is_audience(check_in, user):
            return check_in
        return None

    def get_track_id(self, obj):
        check_in = self.check_in(obj)
        if check_in:
            return check_in.track_id
        else:
            return None

    def get_description(self, obj):
        check_in = self.check_in(obj)
        if check_in:
            return check_in.description
        else:
            return None

    def responses(self, obj):
        from qna.serializers import ResponseSerializer
        user = self.context.get('request', None).user
        response_ids = [response.id for response in obj.response_set.all() if Response.is_audience(response, user)]
        response_queryset = Response.objects.filter(id__in=response_ids).order_by('question__id', 'created_at')
        responses = ResponseSerializer(response_queryset, many=True, read_only=True, context=self.context).data
        return responses

    def notes(self, obj):
        from note.serializers import NoteSerializer
        user = self.context.get('request', None).user
        note_ids = [note.id for note in obj.note_set.all() if Note.is_audience(note, user)]
        note_queryset = Note.objects.filter(id__in=note_ids)
        notes = NoteSerializer(note_queryset, many=True, read_only=True, context=self.context).data
        return notes

    class Meta(UserMinimalSerializer.Meta):
        model = User
        fields = UserMinimalSerializer.Meta.fields + ['is_favorite', 'is_hidden', 'current_user_read', 'unread_cnt',
                                                      'bio', 'track_id', 'description']


class UserFriendsUpdateSerializer(serializers.ModelSerializer):
    favorites = serializers.ListField(child=serializers.IntegerField(), write_only=True)
    hidden = serializers.ListField(child=serializers.IntegerField(), write_only=True)
    unfriend_ids = serializers.ListField(child=serializers.IntegerField(), write_only=True)

    class Meta:
        model = User
        fields = ['favorites', 'hidden', 'unfriend_ids']

    def update(self, instance, validated_data):
        if 'favorites' in validated_data:
            instance.favorites.set(validated_data['favorites'])

        if 'hidden' in validated_data:
            instance.hidden.set(validated_data['hidden'])

        if 'unfriend_ids' in validated_data:
            unfriended_user_ids = validated_data['unfriend_ids']

            # Delete the Connection objects
            from account.models import Connection
            Connection.objects.filter(
                Q(user1=instance, user2_id__in=unfriended_user_ids) |
                Q(user2=instance, user1_id__in=unfriended_user_ids)
            ).delete()

        instance.save()
        return instance


class UserFriendRequestCreateSerializer(serializers.ModelSerializer):
    requester_id = serializers.IntegerField()
    requestee_id = serializers.IntegerField()
    accepted = serializers.BooleanField(allow_null=True, required=False)
    requester_detail = serializers.SerializerMethodField(read_only=True)

    def get_requester_detail(self, obj):
        return UserMinimalSerializer(User.objects.get(id=obj.requester_id)).data

    def validate(self, data):
        if data.get('requester_id') == data.get('requestee_id'):
            raise serializers.ValidationError('본인과는 친구가 될 수 없어요.')
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
            raise serializers.ValidationError("이 필드는 뭘까요: {}".format(", ".join(unknown)))
        if self.instance.accepted is not None:
            raise serializers.ValidationError("이미 friend request에 응답하셨습니다.")
        return data

    class Meta:
        model = FriendRequest
        fields = ['requester_id', 'requestee_id', 'accepted']


class UserFriendshipStatusSerializer(UserMinimalSerializer):
    sent_friend_request_to = serializers.SerializerMethodField(read_only=True)
    received_friend_request_from = serializers.SerializerMethodField(read_only=True)
    are_friends = serializers.SerializerMethodField(read_only=True, allow_null=True)
    chat_room_id = serializers.SerializerMethodField(read_only=True, allow_null=True)

    def get_received_friend_request_from(self, obj):
        user = self.context.get('request').user
        return user.id in obj.sent_friend_requests.filter(accepted__isnull=True).values_list('requestee_id', flat=True)

    def get_sent_friend_request_to(self, obj):
        user = self.context.get('request').user
        return user.id in obj.received_friend_requests.exclude(accepted=True).values_list('requester_id', flat=True)

    def get_are_friends(self, obj):  # does not mean 'friend' in friend & follower, it means connection
        user = self.context.get('request', None).user
        if user == obj:
            return None
        return user.is_connected(obj)

    def get_chat_room_id(self, obj):
        from chat.models import ChatRoom
        user = self.context.get('request', None).user

        if (obj.id not in user.connected_user_ids) or (obj == user):
            return None

        chat_room = ChatRoom.objects.filter(users=user).filter(users=obj) \
            .filter(messages__isnull=False).first()
        return chat_room.id if chat_room else None

    class Meta(UserMinimalSerializer.Meta):
        model = User
        fields = UserMinimalSerializer.Meta.fields + ['sent_friend_request_to',
                                                      'received_friend_request_from',
                                                      'are_friends', 'chat_room_id']


class UserFriendRequestSerializer(serializers.ModelSerializer):
    requestee_detail = serializers.SerializerMethodField(read_only=True)

    def get_requestee_detail(self, obj):
        return UserMinimalSerializer(User.objects.get(id=obj.requestee_id)).data

    class Meta:
        model = FriendRequest
        fields = ['requester_id', 'requestee_id', 'requestee_detail']


class UserMinimumSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField(read_only=True)

    def get_url(self, obj):
        return settings.BASE_URL + reverse('user-detail', kwargs={'username': obj.username})

    class Meta:
        model = User
        fields = ['id', 'username', 'profile_image', 'url']


class BlockRecSerializer(serializers.ModelSerializer):
    blocked_user_id = serializers.IntegerField()

    class Meta:
        model = BlockRec
        fields = ['blocked_user_id']
