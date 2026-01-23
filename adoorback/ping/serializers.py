from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Ping, PingRoom
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

    class Meta:
        model = PingRoom
        fields = ['id', 'opponent', 'last_message', 'last_message_time', 'unread_count']

    def get_opponent(self, obj):
        user = self.context['request'].user
        opponent = obj.user2 if obj.user1 == user else obj.user1
        return UserMinimalSerializer(opponent).data

    def get_last_message(self, obj):
        # We will annotate this in the view for efficiency, but fallback to query if needed
        if hasattr(obj, 'last_ping_content'):
            return obj.last_ping_content or obj.last_ping_emoji
        
        last_ping = obj.pings.last() # rely on default ordering of Ping model
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
