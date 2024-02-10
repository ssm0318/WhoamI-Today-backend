from rest_framework import serializers

from account.serializers import AuthorFriendSerializer
from adoorback.serializers import AdoorBaseSerializer
from comment.serializers import CommentFriendSerializer
from note.models import Note


class ArticleFriendSerializer(AdoorBaseSerializer):
    author = serializers.HyperlinkedIdentityField(
        view_name='user-detail', read_only=True, lookup_field='author', lookup_url_kwarg='username')
    author_detail = AuthorFriendSerializer(source='author', read_only=True)
    comments = serializers.SerializerMethodField()

    def get_comments(self, obj):
        current_user = self.context.get('request', None).user
        comments = obj.article_comments.exclude(author_id__in=current_user.user_report_blocked_ids)
        if obj.author == current_user:
            comments = comments.order_by('id')
            return CommentFriendSerializer(comments, many=True, read_only=True, context=self.context).data
        else:
            comments = comments.filter(is_private=False) | \
                       comments.filter(author=current_user).order_by('id')
            return CommentFriendSerializer(comments, many=True, read_only=True, context=self.context).data

    class Meta(AdoorBaseSerializer.Meta):
        model = Note
        fields = AdoorBaseSerializer.Meta.fields + ['author', 'author_detail', 'comments']

