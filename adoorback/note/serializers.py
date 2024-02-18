from rest_framework import serializers

from account.serializers import AuthorFriendSerializer
from adoorback.serializers import AdoorBaseSerializer
from comment.serializers import CommentFriendSerializer
from note.models import Note


class NoteSerializer(AdoorBaseSerializer):
    author = serializers.HyperlinkedIdentityField(
        view_name='user-detail', read_only=True, lookup_field='author', lookup_url_kwarg='username')
    author_detail = AuthorFriendSerializer(source='author', read_only=True)
    image = serializers.ImageField(required=False)

    class Meta(AdoorBaseSerializer.Meta):
        model = Note
        fields = AdoorBaseSerializer.Meta.fields + ['author', 'author_detail', 'image']

