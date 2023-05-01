from rest_framework import serializers
from django.contrib.auth import get_user_model

from like.models import Like
from adoorback.serializers import AdoorBaseSerializer

User = get_user_model()


class LikeSerializer(serializers.ModelSerializer):
    user = serializers.HyperlinkedIdentityField(
        view_name='user-detail', read_only=True, lookup_field='user', lookup_url_kwarg='username')
    user_detail = serializers.SerializerMethodField()
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()

    def get_user_detail(self, obj):
        user = obj.user
        return {
            "id": user.id,
            "username": user.username,
        }

    def get_target_type(self, obj):
        return obj.target.type

    def get_target_id(self, obj):
        return obj.object_id

    class Meta(AdoorBaseSerializer.Meta):
        model = Like
        fields = ['id', 'type', 'user', 'user_detail', 'is_anonymous', 'target_type', 'target_id']
