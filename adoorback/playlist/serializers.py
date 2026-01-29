from rest_framework import serializers

from check_in.models import CheckIn
from account.serializers import UserMinimalSerializer


class SongSerializer(serializers.ModelSerializer):
    user = UserMinimalSerializer(read_only=True)

    class Meta:
        model = CheckIn
        fields = ['id', 'user', 'track_id', 'created_at']
