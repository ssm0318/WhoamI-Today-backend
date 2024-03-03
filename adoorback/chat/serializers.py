from rest_framework import serializers
from chat.models import ChatRoom, Message
from account.serializers import UserMinimalSerializer


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

class MessageSerializer(serializers.ModelSerializer):
    sender = UserMinimalSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ['id', 'sender', 'content', 'timestamp']
