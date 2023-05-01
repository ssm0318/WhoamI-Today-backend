from django.contrib.auth import get_user_model
from rest_framework import serializers
from django.urls import reverse

from comment.models import Comment

from adoorback.serializers import AdoorBaseSerializer
from adoorback.settings.base import BASE_URL
from account.serializers import AuthorFriendSerializer, AuthorAnonymousSerializer
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
        fields = AdoorBaseSerializer.Meta.fields + ['is_reply', 'is_private',
                                                    'is_anonymous', 'target_id', 
                                                    'user_tags']


class CommentFriendSerializer(CommentBaseSerializer):
    author = serializers.SerializerMethodField(read_only=True)
    author_detail = AuthorFriendSerializer(source='author', read_only=True)
    replies = serializers.SerializerMethodField()

    def get_author(self, obj):
        return BASE_URL + reverse('user-detail', kwargs={'username': obj.author.username})

    def get_replies(self, obj):
        current_user = self.context.get('request', None).user
        if obj.target.type == 'Comment':
            replies = Comment.objects.none()
        elif obj.target.author == current_user or obj.author == current_user:
            replies = obj.replies.order_by('id')
        else:
            replies = obj.replies.filter(is_anonymous=False, is_private=False) | \
                      obj.replies.filter(author=current_user, is_anonymous=False).order_by('id')
        return self.__class__(replies, many=True, read_only=True, context=self.context).data

    class Meta(CommentBaseSerializer.Meta):
        model = Comment
        fields = CommentBaseSerializer.Meta.fields + ['author', 'author_detail', 'replies']


class CommentAnonymousSerializer(CommentBaseSerializer):
    author = serializers.SerializerMethodField(read_only=True)
    author_detail = serializers.SerializerMethodField(source='author', read_only=True)
    replies = serializers.SerializerMethodField()

    def get_author_detail(self, obj):
        if obj.author != self.context.get('request', None).user:
            return AuthorAnonymousSerializer(obj.author).data
        return AuthorFriendSerializer(obj.author).data

    def get_author(self, obj):
        if obj.author == self.context.get('request', None).user:
            return BASE_URL + reverse('user-detail', kwargs={'username': obj.author.username})
        return None

    def get_replies(self, obj):
        current_user = self.context.get('request', None).user
        if obj.target.author == current_user:
            replies = obj.replies.order_by('id')
        else:
            replies = obj.replies.filter(is_anonymous=True, is_private=False) | \
                      obj.replies.filter(author=current_user, is_anonymous=True).order_by('id')
        return self.__class__(replies, many=True, read_only=True, context=self.context).data

    class Meta(CommentBaseSerializer.Meta):
        model = Comment
        fields = CommentBaseSerializer.Meta.fields + ['author', 'author_detail', 'replies']


class CommentResponsiveSerializer(CommentBaseSerializer):
    author = serializers.SerializerMethodField(read_only=True)
    author_detail = serializers.SerializerMethodField(
        source='author', read_only=True)
    replies = serializers.SerializerMethodField()

    def get_replies(self, obj):
        current_user = self.context.get('request', None).user
        if obj.target.author == current_user:
            replies = obj.replies.order_by('id')
        else:
            replies = obj.replies.filter(is_private=False) | \
                      obj.replies.filter(author_id=current_user.id).order_by('id')
        return self.__class__(replies, many=True, read_only=True, context=self.context).data  # responsive serializer

    def get_author_detail(self, obj):
        if not obj.is_anonymous or (obj.author == self.context.get('request', None).user):
            return AuthorFriendSerializer(obj.author).data
        return AuthorAnonymousSerializer(obj.author).data

    def get_author(self, obj):
        if not obj.is_anonymous or (obj.author == self.context.get('request', None).user):
            return BASE_URL + reverse('user-detail', kwargs={'username': obj.author.username})
        return None

    class Meta(CommentBaseSerializer.Meta):
        model = Comment
        fields = CommentBaseSerializer.Meta.fields + ['author', 'author_detail', 'replies']


class ReplySerializer(CommentResponsiveSerializer):

    class Meta(CommentResponsiveSerializer.Meta):
        model = Comment
