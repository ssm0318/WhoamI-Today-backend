from django.contrib.auth import get_user_model
from rest_framework import serializers

from adoorback.utils.content_types import get_generic_relation_type
from like.models import Like

User = get_user_model()


class AdoorBaseSerializer(serializers.ModelSerializer):
    comment_count = serializers.SerializerMethodField(read_only=True)
    like_count = serializers.SerializerMethodField(read_only=True)
    current_user_like_id = serializers.SerializerMethodField(read_only=True)

    def validate(self, attrs):
        if len(attrs.get('content')) == 0:
            raise serializers.ValidationError('내용은 최소 한 글자 이상 써야해요...')
        return attrs

    def get_comment_count(self, obj):
        if obj.type == "Note":
            return obj.note_comments.count()
        elif obj.type == "Response":
            return obj.response_comments.count()
        elif obj.type == "Comment":
            return obj.replies.count()
        return None

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
        model = None
        fields = ['id', 'type', 'content', 'comment_count' ,'like_count', 'current_user_like_id', 'created_at',
                  'updated_at']
        validators = []
