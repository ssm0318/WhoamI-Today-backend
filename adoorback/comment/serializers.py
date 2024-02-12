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

    def get_is_reply(self, obj):
        return obj.target.type == 'Comment'

    def get_target_id(self, obj):
        return obj.object_id

    def get_user_tags(self, obj):
        user_tags = obj.comment_user_tags
        return UserTagSerializer(user_tags, many=True, read_only=True, context=self.context).data

    class Meta(AdoorBaseSerializer.Meta):
        model = Comment
        fields = AdoorBaseSerializer.Meta.fields + ['is_reply', 'is_private', 'target_id', 'user_tags']


class PostCommentsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = '__all__'

    def to_representation(self, obj):
        current_user = self.context.get('request', None).user
        if isinstance(obj, Response):
            comments = obj.response_comments
        elif isinstance(obj, Note):
            comments = obj.note_comments
        else:
            return None
        comments = comments.exclude(author_id__in=current_user.user_report_blocked_ids)
        if obj.author == current_user:
            comments = comments.order_by('id')
            return CommentFriendSerializer(comments, many=True, read_only=True, context=self.context).data
        else:
            comments = comments.filter(is_private=False) | \
                       comments.filter(author=current_user).order_by('id')
            return CommentFriendSerializer(comments, many=True, read_only=True, context=self.context).data


class PostCommentsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = '__all__'

    def to_representation(self, obj):
        current_user = self.context.get('request', None).user
        if isinstance(obj, Response):
            comments = obj.response_comments
        elif isinstance(obj, Note):
            comments = obj.note_comments
        else:
            return None
        comments = comments.exclude(author_id__in=current_user.user_report_blocked_ids)
        if obj.author == current_user:
            comments = comments.order_by('id')
            return CommentFriendSerializer(comments, many=True, read_only=True, context=self.context).data
        else:
            comments = comments.filter(is_private=False) | \
                       comments.filter(author=current_user).order_by('id')
            return CommentFriendSerializer(comments, many=True, read_only=True, context=self.context).data



class CommentFriendSerializer(CommentBaseSerializer):
    author = serializers.SerializerMethodField(read_only=True)
    author_detail = UserMinimalSerializer(source='author', read_only=True)
    replies = serializers.SerializerMethodField()

    def get_author(self, obj):
        return settings.BASE_URL + reverse('user-detail', kwargs={'username': obj.author.username})

    def get_replies(self, obj):
        current_user = self.context.get('request', None).user
        if obj.target.type == 'Comment':
            replies = Comment.objects.none()
        elif obj.target.author == current_user or obj.author == current_user:
            replies = obj.replies.order_by('id')
        else:
            replies = obj.replies.filter(is_private=False) | \
                      obj.replies.filter(author=current_user).order_by('id')
        return self.__class__(replies, many=True, read_only=True, context=self.context).data

    class Meta(CommentBaseSerializer.Meta):
        model = Comment
        fields = CommentBaseSerializer.Meta.fields + ['author', 'author_detail', 'replies']


class ReplySerializer(CommentFriendSerializer):

    class Meta(CommentFriendSerializer.Meta):
        model = Comment
