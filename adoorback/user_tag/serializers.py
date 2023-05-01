from rest_framework import serializers
from django.contrib.auth import get_user_model

from user_tag.models import UserTag

User = get_user_model()


class UserTagSerializer(serializers.ModelSerializer):
    tagged_username = serializers.SerializerMethodField()

    def validate(self, attrs):
        if len(attrs.get('offset')) == -1:
            raise serializers.ValidationError('offset이 -1입니다')
        if len(attrs.get('length')) == 0:
            raise serializers.ValidationError('username length가 -1입니다')
        return attrs

    def get_tagged_username(self, obj):
        return obj.username_str

    class Meta:
        model = UserTag
        fields = ['id', 'tagged_username', 'offset', 'length']
        validators = []
