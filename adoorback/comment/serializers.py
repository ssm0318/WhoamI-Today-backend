from django.contrib.auth import get_user_model
from rest_framework import serializers
from django.urls import reverse

from comment.models import Comment

from adoorback.serializers import AdoorBaseSerializer
from django.conf import settings
from account.serializers import UserMinimalSerializer
from note.models import Note
from qna.models import Response
from user_tag.serializers import UserTagSerializer

User = get_user_model()


class RecursiveReplyField(serializers.Serializer):
    def to_representation(self, value):
        serializer = self.parent.parent.__class__(value, context=self.context)
        return serializer.data


class CommentBaseSerializer(AdoorBaseSerializer):
    is_reply = serializers.SerializerMethodField(read_only=True)
    target_id = serializers.SerializerMethodField()
    user_tags = serializers.SerializerMethodField()
    like_user_sample = serializers.SerializerMethodField(read_only=True)

    def get_is_reply(self, obj):
        return obj.target.type == 'Comment'

    def get_target_id(self, obj):
        return obj.object_id

    def get_user_tags(self, obj):
        user_tags = obj.comment_user_tags
        return UserTagSerializer(user_tags, many=True, read_only=True, context=self.context).data
    
    def get_like_user_sample(self, obj):
        from account.serializers import UserMinimalSerializer
        recent_likes = obj.comment_likes.order_by('-created_at')[:3]
        recent_users = [like.user for like in recent_likes]
        return UserMinimalSerializer(recent_users, many=True, context=self.context).data

    class Meta(AdoorBaseSerializer.Meta):
        model = Comment
        fields = AdoorBaseSerializer.Meta.fields + ['is_reply', 'is_private', 'target_id', 'user_tags', 'like_user_sample']


class CommentFriendSerializer(CommentBaseSerializer):
    author = serializers.SerializerMethodField(read_only=True)
    author_detail = UserMinimalSerializer(source='author', read_only=True)
    replies = serializers.SerializerMethodField()

    def get_author(self, obj):
        return settings.BASE_URL + reverse('user-detail', kwargs={'username': obj.author.username})

    def get_replies(self, obj):
        current_user = self.context.get('request', None).user
        replies = obj.replies.exclude(author_id__in=current_user.user_report_blocked_ids).order_by('-created_at')

        def serialize_reply(reply):
            if (reply.author != current_user
                and reply.target.author != current_user
                and reply.target.target.author != current_user
                and reply.is_private):
                return {'is_private': True}
            else:
                return self.__class__(reply, read_only=True, context=self.context).data

        return [serialize_reply(reply) for reply in replies]

    def to_representation(self, instance):
        current_user = self.context.get('request', None).user
        if (instance.author != current_user
            and instance.target.author != current_user
            and instance.is_private):
            return {'is_private': True}
        else:
            return super().to_representation(instance)


    class Meta(CommentBaseSerializer.Meta):
        model = Comment
        fields = CommentBaseSerializer.Meta.fields + ['author', 'author_detail', 'replies']


class ReplySerializer(CommentFriendSerializer):

    class Meta(CommentFriendSerializer.Meta):
        model = Comment
