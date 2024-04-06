from rest_framework import serializers

from account.serializers import UserMinimalSerializer
from adoorback.serializers import AdoorBaseSerializer
from comment.serializers import CommentFriendSerializer
from note.models import Note


class NoteSerializer(AdoorBaseSerializer):
    author = serializers.HyperlinkedIdentityField(
        view_name='user-detail', read_only=True, lookup_field='author', lookup_url_kwarg='username')
    author_detail = UserMinimalSerializer(source='author', read_only=True)
    images = serializers.SerializerMethodField()
    like_user_sample = serializers.SerializerMethodField(read_only=True)

    def get_images(self, obj):
        images = obj.images.all()
        return [image.image.url for image in images]

    def get_like_user_sample(self, obj):
        from account.serializers import UserMinimalSerializer
        recent_likes = obj.note_likes.order_by('-created_at')[:3]
        recent_users = [like.user for like in recent_likes]
        return UserMinimalSerializer(recent_users, many=True, context=self.context).data

    class Meta(AdoorBaseSerializer.Meta):
        model = Note
        fields = AdoorBaseSerializer.Meta.fields + ['author', 'author_detail', 'images', 'like_user_sample']

