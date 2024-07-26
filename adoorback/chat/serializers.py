from django.contrib.auth import get_user_model
from rest_framework import serializers

from chat.models import ChatRoom, Message, MessageLike
from account.serializers import UserMinimalSerializer

User = get_user_model()


class ChatRoomSerializer(serializers.ModelSerializer):
    participants = serializers.SerializerMethodField(read_only=True)
    unread_cnt = serializers.SerializerMethodField(read_only=True)

    def get_participants(self, obj):
        request = self.context.get('request')
        if request and request.user:
            current_user = request.user
            participants = obj.users.exclude(id=current_user.id)
            return UserMinimalSerializer(participants, many=True).data
        return []
    
    def get_unread_cnt(self, obj):
        request = self.context.get('request')
        if request and request.user:
            current_user = request.user
            return obj.unread_cnt(current_user)
        return 0

    class Meta:
        model = ChatRoom
        fields = ['id', 'participants', 'last_message_content', 'last_message_time', 'active', 'unread_cnt']


class MessageMinimalSerializer(serializers.ModelSerializer):
    sender = UserMinimalSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'sender', 'content', 'timestamp']


class ChatRoomMessageSerializer(MessageMinimalSerializer):
    parent_id = serializers.SerializerMethodField()
    parent_content = serializers.SerializerMethodField()
    current_user_message_like_id = serializers.SerializerMethodField(read_only=True)
    message_like_cnt = serializers.SerializerMethodField(read_only=True)

    def get_parent_id(self, obj):
        if obj.parent:
            return obj.parent.id
        return None

    def get_parent_content(self, obj):
        if obj.parent:
            return obj.parent.content
        return None

    def get_current_user_message_like_id(self, obj):
        current_user_id = self.context['request'].user.id
        message_like = MessageLike.objects.filter(user_id=current_user_id, message_id=obj.id)
        return message_like[0].id if message_like else None

    def get_message_like_cnt(self, obj):
        return MessageLike.objects.filter(message_id=obj.id).count()

    class Meta(MessageMinimalSerializer.Meta):
        model = Message
        fields = MessageMinimalSerializer.Meta.fields + ['parent_id', 'parent_content', 'current_user_message_like_id', 'message_like_cnt']


class SearchMessageSerializer(MessageMinimalSerializer):
    chat_room_id = serializers.SerializerMethodField()

    def get_chat_room_id(self, obj):
        return obj.chat_room.id

    class Meta(MessageMinimalSerializer.Meta):
        model = Message
        fields = MessageMinimalSerializer.Meta.fields + ['chat_room_id']


class MessageLikeSerializer(serializers.ModelSerializer):
    user = UserMinimalSerializer(read_only=True)

    class Meta():
        model = MessageLike
        fields = ['id', 'user']
