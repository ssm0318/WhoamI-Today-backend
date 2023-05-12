from rest_framework import serializers

from moment.models import Moment
from account.serializers import AuthorFriendSerializer
from comment.serializers import CommentFriendSerializer, CommentResponsiveSerializer, CommentAnonymousSerializer


class MomentSerializer(serializers.ModelSerializer):
    author = serializers.HyperlinkedIdentityField(
        view_name='user-detail', read_only=True, lookup_field='author', lookup_url_kwarg='username')
    author_detail = AuthorFriendSerializer(source='author', read_only=True)
    comments = serializers.SerializerMethodField()
    like_count = serializers.SerializerMethodField(read_only=True)
    current_user_liked = serializers.SerializerMethodField(read_only=True)

    def get_comments(self, obj):
        current_user = self.context.get('request', None).user
        comments = obj.moment_comments.exclude(author_id__in=current_user.user_report_blocked_ids)
        if obj.author == current_user:
            comments = comments.order_by('is_anonymous', 'id')
            return CommentResponsiveSerializer(comments, many=True, read_only=True, context=self.context).data
        else: 
            comments = comments.filter(is_anonymous=False, is_private=False) | \
                       comments.filter(author=current_user, is_anonymous=False).order_by('id')
            return CommentFriendSerializer(comments, many=True, read_only=True, context=self.context).data

    def get_like_count(self, obj):
        current_user = self.context['request'].user
        if obj.author != current_user:
            return None
        return obj.liked_user_ids.count()

    def get_current_user_liked(self, obj):
        current_user_id = self.context['request'].user.id
        return current_user_id in obj.liked_user_ids
    
    class Meta:
        model = Moment
        fields = ['id', 'type', 'like_count', 'current_user_liked', 'created_at', 
                  'date', 'mood', 'photo', 'description', 'author', 'author_detail', 'comments']

