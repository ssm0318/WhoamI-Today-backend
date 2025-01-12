from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Ping
from account.serializers import UserMinimalSerializer

User = get_user_model()


class PingSerializer(serializers.ModelSerializer):
    sender = UserMinimalSerializer(read_only=True)

    class Meta:
        model = Ping
        fields = ['id', 'sender', 'emoji', 'content', 'is_read', 'created_at']

