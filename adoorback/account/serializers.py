import csv
import json
import os
import traceback
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers
from django.urls import reverse
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ObjectDoesNotExist, ValidationError

from account.models import FriendRequest, BlockRec, Connection, AppSession, \
    VERSION_CHOICES, PERSONA_CHOICES, Interest, Persona, CustomChip, CHIP_CATEGORY_CHOICES
from adoorback.utils.alerts import send_msg_to_slack
from adoorback.utils.exceptions import ExistingEmail, ExistingUsername
from check_in.models import CheckIn
from note.models import Note
from notification.models import Notification
from chat.models import get_chat_room

from django_countries.serializers import CountryFieldMixin

User = get_user_model()

CHECKIN_AUTO_ARCHIVE_HOURS = 12


def viewer_sees_check_in_component(check_in, profile_user, viewer, visibility_field, updated_at_field):
    """
    Whether `viewer` may see a check-in component's value on another user's profile.
    Applies 12h auto-archive (same as FriendListSerializer) and per-component visibility
    (public / friends / close_friends / only_me).
    """
    if viewer == profile_user:
        return True

    updated_at = getattr(check_in, updated_at_field, None)
    if updated_at and (timezone.now() - updated_at > timedelta(hours=CHECKIN_AUTO_ARCHIVE_HOURS)):
        effective_vis = 'only_me'
    else:
        effective_vis = getattr(check_in, visibility_field)

    if effective_vis == 'only_me':
        return False
    if effective_vis == 'public':
        return True
    if effective_vis == 'friends':
        return viewer.is_connected(profile_user)
    if effective_vis == 'close_friends':
        if not viewer.is_close_friend(profile_user):
            return False
        connection = Connection.get_connection_between(profile_user, viewer)
        if not connection:
            return False
        if profile_user == connection.user1:
            update_past_posts = connection.user1_update_past_posts
            upgrade_time = connection.user1_upgrade_time
        else:
            update_past_posts = connection.user2_update_past_posts
            upgrade_time = connection.user2_upgrade_time
        if update_past_posts:
            return True
        if upgrade_time is None:
            return True
        if check_in.created_at > upgrade_time:
            return True
        return False
    return False


def redact_check_in_base_data_for_viewer(data, check_in, profile_user, viewer):
    """
    Apply per-component visibility to a CheckInBaseSerializer payload (mutates a plain dict).
    Single place for profile, read endpoint, and any other viewer-scoped check-in responses.
    """
    out = dict(data)
    component_pairs = [
        ('social_battery', 'battery_visibility', 'battery_updated_at'),
        ('mood', 'mood_visibility', 'mood_updated_at'),
        ('thought', 'thought_visibility', 'thought_updated_at'),
        ('track_id', 'song_visibility', 'song_updated_at'),
    ]
    for value_field, vis_field, updated_field in component_pairs:
        if not viewer_sees_check_in_component(
            check_in, profile_user, viewer, vis_field, updated_field
        ):
            if value_field == 'mood':
                out[value_field] = []
            elif value_field == 'track_id':
                out[value_field] = ''
            else:
                out[value_field] = None
    return out


def serialize_check_in_base_for_viewer(check_in, request, context=None):
    """
    CheckInBaseSerializer output with per-component redaction for `request.user`.
    """
    from check_in.serializers import CheckInBaseSerializer

    ctx = dict(context) if context else {}
    if request is not None:
        ctx.setdefault('request', request)
    data = CheckInBaseSerializer(check_in, read_only=True, context=ctx).data
    return redact_check_in_base_data_for_viewer(
        data, check_in, check_in.user, request.user
    )


class CurrentUserSerializer(CountryFieldMixin, serializers.HyperlinkedModelSerializer):
    url = serializers.SerializerMethodField(read_only=True)
    unread_noti = serializers.SerializerMethodField(read_only=True)
    unread_noti_cnt = serializers.SerializerMethodField(read_only=True)
    current_ver = serializers.ChoiceField(choices=VERSION_CHOICES, read_only=True)
    user_interests = serializers.StringRelatedField(many=True, read_only=True)
    user_personas = serializers.StringRelatedField(many=True, read_only=True)
    chips_by_category = serializers.SerializerMethodField(read_only=True)
    custom_chips = serializers.SerializerMethodField(read_only=True)

    def get_chips_by_category(self, obj):
        """Return user's interests grouped by category."""
        result = {}
        for cat_key, cat_label in CHIP_CATEGORY_CHOICES:
            chips = obj.user_interests.filter(category=cat_key).values_list('content', flat=True)
            result[cat_key] = list(chips)
        return result

    def get_custom_chips(self, obj):
        """Return user's custom chips."""
        return CustomChipSerializer(obj.custom_chips.all(), many=True).data

    def get_url(self, obj):
        return settings.BASE_URL + reverse('user-detail', kwargs={'username': obj.username})

    def get_unread_noti(self, obj):
        notifications = Notification.objects.visible_only().filter(user=obj, is_read=False)

        if obj.ver_changed_at:
            notifications = notifications.filter(created_at__gte=obj.ver_changed_at)

        return notifications.exists()
    
    def get_unread_noti_cnt(self, obj):
        notifications = Notification.objects.visible_only().filter(user=obj, is_read=False)

        if obj.ver_changed_at:
            notifications = notifications.filter(created_at__gte=obj.ver_changed_at)

        return notifications.count()

    def validate_noti_period_days(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("noti_period_days must be a list.")
        return value
    
    def validate_persona(self, value):
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str):
            try:
                value = json.loads(value[0])
            except json.JSONDecodeError:
                raise serializers.ValidationError("persona must be a valid JSON list.")

        if not isinstance(value, list):
            raise serializers.ValidationError("persona must be a list.")

        invalid_choices = [p for p in value if p not in dict(PERSONA_CHOICES)]
        if invalid_choices:
            raise serializers.ValidationError(f"Invalid choices: {invalid_choices}")

        return value

    def validate(self, attrs):
        if self.partial:
            return super().validate(attrs)
        user = User(**attrs)
        errors = {}
        try:
            validate_password(password=attrs.get('password'), user=user)

        except ValidationError as e:
            errors['password'] = [list(e.messages)[0]]

        if errors:
            raise serializers.ValidationError(errors)
        return super().validate(attrs)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password',
                  'profile_pic', 'question_history', 'url',
                  'profile_image', 'gender', 'date_of_birth',
                  'ethnicity', 'nationality', 'research_agreement', 'pronouns', 'bio', 'persona',
                  'user_interests', 'user_personas', 'chips_by_category', 'custom_chips',
                  'interests_friends_only', 'persona_friends_only', 'pronouns_friends_only', 'bio_friends_only',
                  'signature', 'date_of_signature', 'unread_noti', 'unread_noti_cnt', 
                  'noti_time', 'noti_period_days',
                  'timezone', 'current_ver', 'user_group', 'user_type',
                  'has_changed_pw', 'unread_message_cnt']
        extra_kwargs = {'password': {'write_only': True}}


class CurrentUserSignupSerializer(CurrentUserSerializer):
    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop('password')

        user = User(**validated_data)
        user.set_password(password)
        user.save()

        # Prevent redirect to password change page
        user.has_changed_pw = True
        user.save()
        
        return user

    class Meta(CurrentUserSerializer.Meta):
        fields = CurrentUserSerializer.Meta.fields
        extra_kwargs = {**CurrentUserSerializer.Meta.extra_kwargs}


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
        password = attrs.get('password')
        try:
            validate_password(password=password, user=user)
        except ValidationError as e:
            raise serializers.ValidationError({
                'password_validation_error': e.messages
            })

        return super().validate(attrs)


class UserEmailSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email']


class UserUsernameSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username']


class UserBirthDateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['date_of_birth']


class UserInviterEmailBirthDateSerializer(serializers.Serializer):
    email = serializers.EmailField()


class UserProfileSerializer(UserMinimalSerializer):
    check_in = serializers.SerializerMethodField(read_only=True)
    is_favorite = serializers.SerializerMethodField(read_only=True)
    mutuals = serializers.SerializerMethodField(read_only=True)
    are_friends = serializers.SerializerMethodField(read_only=True)
    connection_status = serializers.SerializerMethodField(read_only=True)
    sent_friend_request_to = serializers.SerializerMethodField(read_only=True)
    received_friend_request_from = serializers.SerializerMethodField(read_only=True)
    sent_chat_request_to = serializers.SerializerMethodField(read_only=True)
    unread_chat_count = serializers.SerializerMethodField(read_only=True)
    friend_count = serializers.SerializerMethodField(read_only=True)
    mutual_personas = serializers.SerializerMethodField(read_only=True)
    mutual_interests = serializers.SerializerMethodField(read_only=True)
    friendship_level = serializers.SerializerMethodField(read_only=True)
    is_check_in_subscribed = serializers.SerializerMethodField(read_only=True)

    def get_is_check_in_subscribed(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated and request.user.current_ver == 'version_w':
            from adoorback.utils.content_types import get_check_in_type
            from account.models import Subscription
            return Subscription.objects.filter(
                subscriber=request.user, subscribed_to=obj, content_type=get_check_in_type()
            ).exists()
        return False

    def get_is_favorite(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj in request.user.favorites.all()
        return False

    def get_check_in(self, obj):
        user = self.context.get('request', None).user
        check_in = obj.check_in_set.filter(is_active=True).first()
        if check_in and CheckIn.is_audience(check_in, user):
            return serialize_check_in_base_for_viewer(
                check_in, self.context.get('request'), self.context
            )
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

    def get_mutual_personas(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            current_user_personas = set(request.user.user_personas.all())
            obj_personas = set(obj.user_personas.all())
            mutual_personas = current_user_personas & obj_personas
            return PersonaSerializer(mutual_personas, many=True).data
        return []

    def get_mutual_interests(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            current_user_interests = set(request.user.user_interests.all())
            obj_interests = set(obj.user_interests.all())
            mutual_interests = current_user_interests & obj_interests
            return InterestSerializer(mutual_interests, many=True).data
        return []

    def get_are_friends(self, obj):  # does not mean 'friend' in friend & close friend, it means connection
        user = self.context.get('request', None).user
        if user == obj:
            return None
        return user.is_connected(obj)
    
    def get_connection_status(self, obj):  # what user has set obj as
        user = self.context.get('request', None).user
        if user == obj:
            return None
        if user.is_connected(obj):
            if obj.is_close_friend(user):
                return 'close_friend'
            if obj.is_friend(user):
                return 'friend'
        return None

    def get_received_friend_request_from(self, obj):
        user = self.context.get('request').user
        return user.id in obj.sent_friend_requests.filter(accepted__isnull=True).values_list('requestee_id', flat=True)

    def get_sent_friend_request_to(self, obj):
        user = self.context.get('request').user
        return user.id in obj.received_friend_requests.exclude(accepted=True).values_list('requester_id', flat=True)

    def get_sent_chat_request_to(self, obj):
        user = self.context.get('request').user
        return obj.received_chat_requests.filter(requester=user, accepted__isnull=True).exists()

    def get_unread_chat_count(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            user = request.user
            if user == obj:
                return 0
            chat_room = get_chat_room(user, obj)
            if chat_room:
                return chat_room.messages.filter(receiver=user, is_read=False).count()
        return 0
    
    def get_friendship_level(self, obj):
        user = self.context.get('request', None).user
        if user == obj:
            return None
        if user.is_connected(obj):
            return '1st'
        current_user_connections = set(user.connected_user_ids)
        obj_connections = set(obj.connected_user_ids)
        if current_user_connections & obj_connections:
            return '2nd'
        return '3rd+'

    def get_friend_count(self, obj):
        return Connection.objects.filter(Q(user1=obj) | Q(user2=obj)).count()

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        request = self.context.get('request')
        user = request.user if request else None

        # Check if the requester should see private fields
        can_see_private = False
        if user and user.is_authenticated:
             if user == instance or user.is_connected(instance):
                 can_see_private = True

        if not can_see_private:
            if instance.interests_friends_only:
                ret['user_interests'] = []
            if instance.persona_friends_only:
                ret['user_personas'] = []
            if instance.pronouns_friends_only:
                ret['pronouns'] = None
            if instance.bio_friends_only:
                ret['bio'] = None

        return ret

    user_interests = serializers.StringRelatedField(many=True, read_only=True)
    user_personas = serializers.StringRelatedField(many=True, read_only=True)

    class Meta(UserMinimalSerializer.Meta):
        model = User
        fields = UserMinimalSerializer.Meta.fields + ['check_in', 'is_favorite', 'mutuals',
                                                      'are_friends', 'sent_friend_request_to', 'received_friend_request_from',
                                                      'sent_chat_request_to',
                                                      'pronouns', 'bio', 'persona', 'user_interests', 'user_personas',
                                                      'unread_chat_count', 'unread_message_cnt', 'connection_status',
                                                      'friend_count', 'email_verified',
                                                      'mutual_personas', 'mutual_interests',
                                                      'friendship_level', 'is_check_in_subscribed']


class FriendListSerializer(UserMinimalSerializer):
    url = serializers.SerializerMethodField(read_only=True)
    is_favorite = serializers.SerializerMethodField(read_only=True)
    is_hidden = serializers.SerializerMethodField(read_only=True)
    connection_status = serializers.SerializerMethodField(read_only=True)
    current_user_read = serializers.SerializerMethodField(read_only=True)
    unread_cnt = serializers.SerializerMethodField(read_only=True)
    unread_post_cnt = serializers.SerializerMethodField(read_only=True)
    latest_unread_post = serializers.SerializerMethodField(read_only=True)
    check_in_id = serializers.SerializerMethodField(read_only=True)
    track_id = serializers.SerializerMethodField(read_only=True)
    thought = serializers.SerializerMethodField(read_only=True)
    unread_chat_count = serializers.SerializerMethodField(read_only=True)
    social_battery = serializers.SerializerMethodField(read_only=True)
    mood = serializers.SerializerMethodField(read_only=True)
    battery_visibility = serializers.SerializerMethodField(read_only=True)
    mood_visibility = serializers.SerializerMethodField(read_only=True)
    song_visibility = serializers.SerializerMethodField(read_only=True)
    thought_visibility = serializers.SerializerMethodField(read_only=True)
    sent_pokes = serializers.SerializerMethodField(read_only=True)
    is_check_in_subscribed = serializers.SerializerMethodField(read_only=True)

    def get_is_check_in_subscribed(self, obj):
        return obj.id in self.context.get('check_in_subscription_ids', set())

    def get_sent_pokes(self, obj):
        return self.context.get('pokes_by_receiver', {}).get(obj.id, {})

    def get_url(self, obj):
        return settings.BASE_URL + reverse('user-detail', kwargs={'username': obj.username})

    def get_is_favorite(self, obj):
        return obj.id in self.context.get('favorite_ids', set())

    def get_is_hidden(self, obj):
        return obj.id in self.context.get('hidden_ids', set())

    def get_connection_status(self, obj):  # what user has set obj as
        user = self.context['request'].user
        if user == obj:
            return None
        conn = self.context.get('connection_by_friend_id', {}).get(obj.id)
        if not conn:
            return None
        # viewer's choice for obj (viewer is whichever side of the Connection isn't obj)
        viewer_choice = conn.user1_choice if conn.user1_id == user.id else conn.user2_choice
        if viewer_choice in ('close_friend', 'friend'):
            return viewer_choice
        return None

    def get_current_user_read(self, obj):
        viewer_id = self.context['request'].user.id
        for n in self.context.get('visible_notes_by_author', {}).get(obj.id, []):
            if viewer_id not in {r.id for r in n.readers.all()}:
                return False
        for r in self.context.get('visible_resps_by_author', {}).get(obj.id, []):
            if viewer_id not in {u.id for u in r.readers.all()}:
                return False
        ci = self.check_in(obj)
        if ci and viewer_id not in {u.id for u in ci.readers.all()}:
            return False
        return True

    def get_unread_post_cnt(self, obj):
        return (self.context.get('unread_note_count_by_author', {}).get(obj.id, 0)
                + self.context.get('unread_response_count_by_author', {}).get(obj.id, 0))

    def get_latest_unread_post(self, obj):
        viewer_id = self.context['request'].user.id
        unread = []
        for n in self.context.get('visible_notes_by_author', {}).get(obj.id, []):
            if viewer_id not in {r.id for r in n.readers.all()}:
                unread.append(n)
        for r in self.context.get('visible_resps_by_author', {}).get(obj.id, []):
            if viewer_id not in {u.id for u in r.readers.all()}:
                unread.append(r)
        if not unread:
            return None
        latest = max(unread, key=lambda p: p.created_at)
        if isinstance(latest, Note):
            images = [img.image.url for img in sorted(latest.images.all(), key=lambda i: i.created_at)]
        else:
            images = []
        return {
            'id': latest.id,
            'type': latest.type,
            'content': latest.content,
            'images': images,
        }

    def get_unread_cnt(self, obj):
        return self.context.get('unread_chat_count_by_friend_id', {}).get(obj.id, 0)

    def check_in(self, obj):
        if self.context.get('hide_check_in'):
            return None
        return self.context.get('visible_check_in_by_user_id', {}).get(obj.id)

    def get_check_in_id(self, obj):
        check_in = self.check_in(obj)
        return check_in.id if check_in else None

    def get_track_id(self, obj):
        if not self._is_component_visible(obj, 'song_visibility', 'song_updated_at'):
            return None
        song = self.context.get('active_song_by_user_id', {}).get(obj.id)
        return song.track_id if song else None

    def _is_component_visible(self, obj, visibility_field, updated_at_field):
        """Check if a component should be visible to the current viewer."""
        check_in = self.check_in(obj)
        if not check_in:
            return False
        effective_vis = self._component_visibility(check_in, visibility_field, updated_at_field)
        if effective_vis == 'only_me':
            user = self.context.get('request', None).user
            return user == obj  # Only visible to the owner
        return True

    def get_thought(self, obj):
        if not self._is_component_visible(obj, 'thought_visibility', 'thought_updated_at'):
            return None
        check_in = self.check_in(obj)
        return check_in.thought if check_in else None

    def get_social_battery(self, obj):
        if not self._is_component_visible(obj, 'battery_visibility', 'battery_updated_at'):
            return None
        check_in = self.check_in(obj)
        return check_in.social_battery if check_in else None

    def get_mood(self, obj):
        if not self._is_component_visible(obj, 'mood_visibility', 'mood_updated_at'):
            return None
        check_in = self.check_in(obj)
        return check_in.mood if check_in else None

    def _component_visibility(self, check_in, visibility_field, updated_at_field):
        """Return component visibility, applying auto-archive if >12h old."""
        from datetime import timedelta
        if not check_in:
            return None
        updated_at = getattr(check_in, updated_at_field, None)
        if updated_at and (timezone.now() - updated_at > timedelta(hours=12)):
            return 'only_me'
        return getattr(check_in, visibility_field)

    def get_battery_visibility(self, obj):
        return self._component_visibility(self.check_in(obj), 'battery_visibility', 'battery_updated_at')

    def get_mood_visibility(self, obj):
        return self._component_visibility(self.check_in(obj), 'mood_visibility', 'mood_updated_at')

    def get_song_visibility(self, obj):
        return self._component_visibility(self.check_in(obj), 'song_visibility', 'song_updated_at')

    def get_thought_visibility(self, obj):
        return self._component_visibility(self.check_in(obj), 'thought_visibility', 'thought_updated_at')

    def get_unread_chat_count(self, obj):
        return self.context.get('unread_chat_count_by_friend_id', {}).get(obj.id, 0)

    class Meta(UserMinimalSerializer.Meta):
        model = User
        fields = UserMinimalSerializer.Meta.fields + ['is_favorite', 'is_hidden', 'connection_status', 'current_user_read',
                                                      'unread_cnt', 'unread_post_cnt', 'latest_unread_post',
                                                      'bio', 'check_in_id', 'track_id', 'thought',
                                                      'unread_chat_count', 'social_battery', 'mood',
                                                      'battery_visibility', 'mood_visibility', 'song_visibility', 'thought_visibility',
                                                      'sent_pokes', 'is_check_in_subscribed']


class FriendFriendListSerializer(UserMinimalSerializer):
    url = serializers.SerializerMethodField(read_only=True)
    connection_status = serializers.SerializerMethodField(read_only=True)

    def get_url(self, obj):
        return settings.BASE_URL + reverse('user-detail', kwargs={'username': obj.username})
    
    def get_connection_status(self, obj):  # what user has set obj as
        user = self.context.get('request', None).user
        if user == obj:
            return None
        if user.is_connected(obj):
            if obj.is_close_friend(user):
                return 'close_friend'
            if obj.is_friend(user):
                return 'friend'
        return None

    class Meta(UserMinimalSerializer.Meta):
        model = User
        fields = UserMinimalSerializer.Meta.fields + ['connection_status']


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
    requester_choice = serializers.CharField(required=False)
    requester_update_past_posts = serializers.BooleanField(required=False, default=False)

    def get_requester_detail(self, obj):
        return UserMinimalSerializer(User.objects.get(id=obj.requester_id)).data

    def validate(self, data):
        data = super().validate(data)
        
        try:
            requester = User.objects.get(id=data['requester_id'])
            requestee = User.objects.get(id=data['requestee_id'])
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found")

        if requester.current_ver != requestee.current_ver:
            raise serializers.ValidationError({
                "error": "Cannot send friend requests to users using different versions"
            })

        if data.get('requester_id') == data.get('requestee_id'):
            raise serializers.ValidationError('You cannot be friends with yourself.')

        # requester_choice is required in ver.E
        if not self.context.get("default_api") and "requester_choice" not in data:
            raise serializers.ValidationError({"requester_choice": "This field is required."})

        return data

    class Meta:
        model = FriendRequest
        fields = ['requester_id', 'requestee_id', 'accepted', 'requester_detail', 'requester_choice', 'requester_update_past_posts']


class UserFriendRequestUpdateSerializer(serializers.ModelSerializer):
    requester_id = serializers.IntegerField(required=False)
    requestee_id = serializers.IntegerField(required=False)
    accepted = serializers.BooleanField(required=True)
    requestee_choice = serializers.CharField(required=False)
    requestee_update_past_posts = serializers.BooleanField(required=False, default=False)

    def validate(self, data):
        unknown = set(self.initial_data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError("Unknown field: {}".format(", ".join(unknown)))
        if self.instance.accepted is not None:
            raise serializers.ValidationError("You have already responded to this connection request.")
        
        if data.get("accepted") is True:
            if not self.context.get("default_api") and "requestee_choice" not in self.initial_data:
                raise serializers.ValidationError({"requestee_choice": "This field is required."})

        return data

    class Meta:
        model = FriendRequest
        fields = [
            'requester_id', 
            'requestee_id', 
            'accepted', 
            'requestee_choice', 
            'requestee_update_past_posts'
        ]


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

    def get_are_friends(self, obj):  # does not mean 'friend' in close friend & friend, it means connection
        user = self.context.get('request', None).user
        if user == obj:
            return None
        return user.is_connected(obj)

    def get_chat_room_id(self, obj):
        from chat.models import get_chat_room
        user = self.context.get('request', None).user

        if (obj.id not in user.connected_user_ids) or (obj == user):
            return None

        chat_room = get_chat_room(user, obj)
        if chat_room and chat_room.messages.exists():
            return chat_room.id
        return None

    class Meta(UserMinimalSerializer.Meta):
        model = User
        fields = UserMinimalSerializer.Meta.fields + ['sent_friend_request_to',
                                                      'received_friend_request_from',
                                                      'are_friends', 'chat_room_id', 'email']


class UserFriendRequestSerializer(serializers.ModelSerializer):
    requestee_detail = serializers.SerializerMethodField(read_only=True)

    def get_requestee_detail(self, obj):
        return UserMinimalSerializer(User.objects.get(id=obj.requestee_id)).data

    class Meta:
        model = FriendRequest
        fields = ['requester_id', 'requestee_id', 'requestee_detail']


class UserInterestUpdateSerializer(serializers.Serializer):
    user_interests = serializers.ListField(child=serializers.CharField(), required=False)

    def validate_user_interests(self, value):
        # Handle stringified list from form-data
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str):
            try:
                import json
                value = json.loads(value[0])
            except json.JSONDecodeError:
                raise serializers.ValidationError("user_interests must be a valid JSON list.")

        from account.models import ALL_CHIP_NAMES
        if not isinstance(value, list):
            raise serializers.ValidationError("user_interests must be a list of strings.")

        # Validate against category-based chips (custom chips are also allowed)
        invalid = [i for i in value if i not in ALL_CHIP_NAMES]
        if invalid:
            # Allow custom chips (user-created) — only reject if needed
            pass

        return value


class UserPersonaUpdateSerializer(serializers.Serializer):
    user_personas = serializers.ListField(child=serializers.CharField(), required=False)

    def validate_user_personas(self, value):
        # Handle stringified list from form-data
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str):
            try:
                import json
                value = json.loads(value[0])
            except json.JSONDecodeError:
                raise serializers.ValidationError("user_personas must be a valid JSON list.")

        from account.models import PERSONA_CHOICES
        if not isinstance(value, list):
            raise serializers.ValidationError("user_personas must be a list of strings.")
            
        # Value contains keys (e.g. 'lurker')
        valid_keys = {choice[0] for choice in PERSONA_CHOICES}
        invalid = [p for p in value if p not in valid_keys]
        if invalid:
            raise serializers.ValidationError(f"Invalid choices: {invalid}")
            
        return value


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


class AppSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppSession
        fields = ["session_id", "user", "start_time", "end_time"]
        read_only_fields = ["start_time", "end_time"]


class InterestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Interest
        fields = ['id', 'content', 'category']


class PersonaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Persona
        fields = ['id', 'content']


class CustomChipSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomChip
        fields = ['id', 'text', 'category']
