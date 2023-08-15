from rest_framework import serializers

from account.serializers import AuthorFriendSerializer
from adoorback.utils.content_types import get_generic_relation_type
from comment.serializers import CommentFriendSerializer, CommentResponsiveSerializer, CommentAnonymousSerializer
from like.models import Like
from moment.models import Moment


class MyMomentSerializer(serializers.ModelSerializer):
    like_count = serializers.SerializerMethodField(read_only=True)
    current_user_like_id = serializers.SerializerMethodField(read_only=True)

    def get_like_count(self, obj):
        current_user = self.context['request'].user
        if obj.author != current_user:
            return None
        return obj.liked_user_ids.count()

    def get_current_user_like_id(self, obj):
        current_user_id = self.context['request'].user.id
        content_type_id = get_generic_relation_type(obj.type).id
        like = Like.objects.filter(user_id=current_user_id, content_type_id=content_type_id, object_id=obj.id)
        return like[0].id if like else None
    
    class Meta:
        model = Moment
        fields = ['id', 'type', 'like_count', 'current_user_like_id', 'created_at', 'available_limit',
                  'date', 'mood', 'photo', 'description']


class MomentDetailSerializer(MyMomentSerializer):
    author = serializers.HyperlinkedIdentityField(
        view_name='user-detail', read_only=True, lookup_field='author', lookup_url_kwarg='username')
    author_detail = AuthorFriendSerializer(source='author', read_only=True)

    class Meta:
        model = Moment
        fields = MyMomentSerializer.Meta.fields + \
                 ['author', 'author_detail']
        