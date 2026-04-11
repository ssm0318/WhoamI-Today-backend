from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Ping, PingRoom, PingRequest
from account.serializers import UserMinimalSerializer

User = get_user_model()


class PingSerializer(serializers.ModelSerializer):
    sender = UserMinimalSerializer(read_only=True)

    class Meta:
        model = Ping
        fields = ['id', 'sender', 'emoji', 'content', 'is_read', 'created_at']


class PingRoomSerializer(serializers.ModelSerializer):
    opponent = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    last_message_time = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    request_status = serializers.SerializerMethodField()

    class Meta:
        model = PingRoom
        fields = ['id', 'opponent', 'last_message', 'last_message_time', 'unread_count', 'request_status']

    def get_opponent(self, obj):
        user = self.context['request'].user
        opponent = obj.user2 if obj.user1 == user else obj.user1
        return UserMinimalSerializer(opponent).data

    def get_last_message(self, obj):
        if hasattr(obj, 'last_ping_content'):
            return obj.last_ping_content or obj.last_ping_emoji
        last_ping = obj.pings.last()
        if last_ping:
            return last_ping.content or last_ping.emoji
        return None

    def get_last_message_time(self, obj):
        if hasattr(obj, 'last_ping_time'):
            return obj.last_ping_time
        last_ping = obj.pings.last()
        return last_ping.created_at if last_ping else None

    def get_unread_count(self, obj):
        user = self.context['request'].user
        if hasattr(obj, 'unread_cnt'):
            return obj.unread_cnt
        return obj.pings.filter(receiver=user, is_read=False).count()

    def get_request_status(self, obj):
        """Return ping request status for non-friend rooms."""
        user = self.context['request'].user
        opponent = obj.user2 if obj.user1 == user else obj.user1
        if user.is_connected(opponent):
            return 'friends'
        req = PingRequest.objects.filter(
            requester=user, requestee=opponent
        ).first() or PingRequest.objects.filter(
            requester=opponent, requestee=user
        ).first()
        if req is None:
            return None
        if req.accepted is True:
            return 'accepted'
        if req.accepted is False:
            return 'declined'
        if req.requester == user:
            return 'sent'
        return 'received'


class PingRequestSerializer(serializers.ModelSerializer):
    requester_detail = UserMinimalSerializer(source='requester', read_only=True)
    requestee_detail = UserMinimalSerializer(source='requestee', read_only=True)
    requestee_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = PingRequest
        fields = ['id', 'requester_detail', 'requestee_detail', 'requestee_id',
                  'accepted', 'created_at']
        read_only_fields = ['id', 'requester_detail', 'requestee_detail', 'accepted', 'created_at']

    def validate_requestee_id(self, value):
        user = self.context['request'].user
        if value == user.id:
            raise serializers.ValidationError("You cannot send a ping request to yourself.")
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError("User not found.")
        return value


class PingRequestUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PingRequest
        fields = ['accepted']
