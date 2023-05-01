from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class AdoorBaseSerializer(serializers.ModelSerializer):
    like_count = serializers.SerializerMethodField(read_only=True)
    current_user_liked = serializers.SerializerMethodField(read_only=True)

    def validate(self, attrs):
        if len(attrs.get('content')) == 0:
            raise serializers.ValidationError('내용은 최소 한 글자 이상 써야해요...')
        return attrs

    def get_like_count(self, obj):
        current_user = self.context['request'].user
        if obj.author != current_user:
            return None
        return obj.liked_user_ids.count()

    def get_current_user_liked(self, obj):
        current_user_id = self.context['request'].user.id
        return current_user_id in obj.liked_user_ids

    class Meta:
        model = None
        fields = ['id', 'type', 'content', 'like_count', 'current_user_liked', 'created_at']
        validators = []
