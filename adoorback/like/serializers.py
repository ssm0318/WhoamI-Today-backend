from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from account.serializers import UserMinimalSerializer
from adoorback.serializers import AdoorBaseSerializer
from like.models import Like
from reaction.models import Reaction

User = get_user_model()


class LikeSerializer(serializers.ModelSerializer):
    user = serializers.HyperlinkedRelatedField(
        view_name='user-detail',
        read_only=True,
        lookup_field='username',
        lookup_url_kwarg='username'
    )
    user_detail = UserMinimalSerializer(source='user', read_only=True)
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
        fields = ['id', 'type', 'user', 'user_detail', 'target_type', 'target_id']


class InteractionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    type = serializers.SerializerMethodField()
    user = serializers.HyperlinkedRelatedField(
        view_name='user-detail', read_only=True, lookup_field='username', lookup_url_kwarg='username')
    user_detail = UserMinimalSerializer(source='user', read_only=True)
    reaction = serializers.CharField(allow_null=True)

    def get_user_detail(self, obj):
        user = obj.user
        return {
            "id": user.id,
            "username": user.username,
        }

    def get_type(self, obj):
        if isinstance(obj, Like):
            return 'Like'
        elif isinstance(obj, Reaction):
            return 'Reaction'
        return ValidationError(f"Unexpected object type: {type(obj)}")


    class Meta(AdoorBaseSerializer.Meta):
        fields = ['id', 'type', 'reaction', 'user', 'user_detail']
