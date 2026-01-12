from rest_framework import serializers

from playlist.models import Song
from account.serializers import UserMinimalSerializer


class SongSerializer(serializers.ModelSerializer):
    user = UserMinimalSerializer(read_only=True)

    class Meta:
        model = Song
        fields = ['id', 'user', 'track_id', 'created_at']
