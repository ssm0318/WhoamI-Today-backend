from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from rest_framework import serializers

from .models import Message, ChatRoom, ChatRequest, MessageReaction, GroupReadCursor
from account.serializers import UserMinimalSerializer

User = get_user_model()


class MessageReactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageReaction
        fields = ['id', 'user', 'emoji']
        read_only_fields = ['id', 'user']


class MessageSerializer(serializers.ModelSerializer):
    sender = UserMinimalSerializer(read_only=True)
    reactions = serializers.SerializerMethodField()
    parent_preview = serializers.SerializerMethodField()
    shared_content_preview = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'sender', 'emoji', 'content', 'image', 'is_read', 'created_at',
            'parent', 'reactions', 'parent_preview',
            'shared_content_type', 'shared_object_id', 'shared_content_preview',
        ]

    def get_reactions(self, obj):
        reactions_qs = obj.reactions.all() if hasattr(obj, '_prefetched_objects_cache') and 'reactions' in obj._prefetched_objects_cache else obj.reactions.all()
        emoji_groups = {}
        user = self.context.get('request').user if self.context.get('request') else None

        for r in reactions_qs:
            if r.emoji not in emoji_groups:
                emoji_groups[r.emoji] = {'emoji': r.emoji, 'count': 0, 'my_reaction_id': None}
            emoji_groups[r.emoji]['count'] += 1
            if user and r.user_id == user.id:
                emoji_groups[r.emoji]['my_reaction_id'] = r.id

        return list(emoji_groups.values())

    def get_parent_preview(self, obj):
        if not obj.parent:
            return None
        return {
            'id': obj.parent.id,
            'content': obj.parent.content[:100] if obj.parent.content else None,
            'emoji': obj.parent.emoji,
            'sender': UserMinimalSerializer(obj.parent.sender).data,
        }

    def get_shared_content_preview(self, obj):
        if not obj.shared_object_id or not obj.shared_content_type:
            return None
        target = obj.shared_content
        if not target:
            return None
        model_name = obj.shared_content_type.model
        preview = {
            'type': model_name,
            'id': obj.shared_object_id,
        }
        if hasattr(target, 'author'):
            preview['author'] = UserMinimalSerializer(target.author).data
        elif hasattr(target, 'sender'):
            preview['author'] = UserMinimalSerializer(target.sender).data
        if hasattr(target, 'content'):
            preview['content'] = str(target.content)[:150]
        if hasattr(target, 'title'):
            preview['title'] = str(target.title)[:100]
        if hasattr(target, 'images') and target.images.exists():
            preview['image_url'] = target.images.first().image.url
        return preview


class ChatRoomSerializer(serializers.ModelSerializer):
    opponent = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    last_message_time = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    request_status = serializers.SerializerMethodField()
    members_detail = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = [
            'id', 'is_group', 'name', 'opponent', 'members_detail',
            'last_message', 'last_message_time', 'unread_count', 'request_status',
        ]

    def get_opponent(self, obj):
        if obj.is_group:
            return None
        user = self.context['request'].user
        opponent = obj.user2 if obj.user1 == user else obj.user1
        return UserMinimalSerializer(opponent).data

    def get_members_detail(self, obj):
        if not obj.is_group:
            return None
        return UserMinimalSerializer(obj.members.all(), many=True).data

    def get_last_message(self, obj):
        if hasattr(obj, 'last_message_content'):
            return obj.last_message_content or obj.last_message_emoji
        last_msg = obj.messages.last()
        if last_msg:
            return last_msg.content or last_msg.emoji
        return None

    def get_last_message_time(self, obj):
        if hasattr(obj, 'last_message_time'):
            return obj.last_message_time
        last_msg = obj.messages.last()
        return last_msg.created_at if last_msg else None

    def get_unread_count(self, obj):
        user = self.context['request'].user
        if obj.is_group:
            cursor = GroupReadCursor.objects.filter(user=user, chat_room=obj).first()
            if cursor and cursor.last_read_message:
                return obj.messages.exclude(sender=user).filter(
                    created_at__gt=cursor.last_read_message.created_at
                ).count()
            # No cursor = never read = all messages from others are unread
            return obj.messages.exclude(sender=user).count()
        if hasattr(obj, 'unread_cnt'):
            return obj.unread_cnt
        return obj.messages.filter(receiver=user, is_read=False).count()

    def get_request_status(self, obj):
        user = self.context['request'].user
        opponent = obj.user2 if obj.user1 == user else obj.user1
        if user.is_connected(opponent):
            return 'friends'
        req = ChatRequest.objects.filter(
            requester=user, requestee=opponent
        ).first() or ChatRequest.objects.filter(
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


class ChatRequestSerializer(serializers.ModelSerializer):
    requester_detail = UserMinimalSerializer(source='requester', read_only=True)
    requestee_detail = UserMinimalSerializer(source='requestee', read_only=True)
    requestee_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = ChatRequest
        fields = ['id', 'requester_detail', 'requestee_detail', 'requestee_id',
                  'accepted', 'created_at']
        read_only_fields = ['id', 'requester_detail', 'requestee_detail', 'accepted', 'created_at']

    def validate_requestee_id(self, value):
        user = self.context['request'].user
        if value == user.id:
            raise serializers.ValidationError("You cannot send a chat request to yourself.")
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError("User not found.")
        return value


class ChatRequestUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatRequest
        fields = ['accepted']
