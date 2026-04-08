from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from account.serializers import UserMinimalSerializer
from check_in.models import CheckIn, Song, Poke

CHECKIN_AUTO_ARCHIVE_HOURS = 12


class CheckInBaseSerializer(serializers.ModelSerializer):
    current_user_read = serializers.SerializerMethodField(read_only=True)
    battery_visibility = serializers.SerializerMethodField(read_only=True)
    mood_visibility = serializers.SerializerMethodField(read_only=True)
    song_visibility = serializers.SerializerMethodField(read_only=True)
    thought_visibility = serializers.SerializerMethodField(read_only=True)
    # Song lives in a separate model. Surface the active song's track_id here so
    # that consumers reading `checkIn.track_id` (e.g. MyCheckInCard) work without
    # an extra fetch. Mirrors the pattern in account.serializers.get_track_id.
    track_id = serializers.SerializerMethodField(read_only=True)

    def _is_archived(self, updated_at):
        """Check if a component should be auto-archived (>12h since last update)."""
        if not updated_at:
            return False
        return timezone.now() - updated_at > timedelta(hours=CHECKIN_AUTO_ARCHIVE_HOURS)

    def get_battery_visibility(self, obj):
        if self._is_archived(obj.battery_updated_at):
            return 'only_me'
        return obj.battery_visibility

    def get_mood_visibility(self, obj):
        if self._is_archived(obj.mood_updated_at):
            return 'only_me'
        return obj.mood_visibility

    def get_song_visibility(self, obj):
        if self._is_archived(obj.song_updated_at):
            return 'only_me'
        return obj.song_visibility

    def get_thought_visibility(self, obj):
        if self._is_archived(obj.thought_updated_at):
            return 'only_me'
        return obj.thought_visibility

    def get_current_user_read(self, obj):
        current_user_id = self.context['request'].user.id
        return current_user_id in obj.reader_ids

    def get_track_id(self, obj):
        song = obj.user.song_set.filter(is_active=True).first()
        return song.track_id if song else ''

    class Meta:
        model = CheckIn
        fields = ['id', 'created_at', 'is_active', 'mood',
                  'social_battery', 'description', 'current_user_read', 'visibility',
                  'battery_visibility', 'mood_visibility', 'song_visibility', 'thought_visibility',
                  'battery_updated_at', 'mood_updated_at', 'song_updated_at', 'thought_updated_at',
                  'track_id']


class MyCheckInSerializer(CheckInBaseSerializer):
    # Writable versions of the visibility fields (override read-only SerializerMethodField)
    battery_visibility = serializers.CharField(required=False)
    mood_visibility = serializers.CharField(required=False)
    song_visibility = serializers.CharField(required=False)
    thought_visibility = serializers.CharField(required=False)

    class Meta:
        model = CheckIn
        fields = CheckInBaseSerializer.Meta.fields
        extra_kwargs = {
            'visibility': {'required': False},
            'battery_updated_at': {'read_only': True},
            'mood_updated_at': {'read_only': True},
            'song_updated_at': {'read_only': True},
            'thought_updated_at': {'read_only': True},
        }

    def validate_visibility(self, value):
        if len(value) == 0:
            return value
        if len(value) != 1:
            raise serializers.ValidationError("Please select exactly one visibility option.")
        return value


class SongBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Song
        fields = ['id', 'created_at', 'is_active', 'track_id']


class MySongSerializer(SongBaseSerializer):
    class Meta:
        model = Song
        fields = SongBaseSerializer.Meta.fields


class PokeSerializer(serializers.ModelSerializer):
    receiver_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Poke
        fields = ['id', 'sender', 'receiver', 'receiver_id', 'component_type', 'created_at']
        read_only_fields = ['id', 'sender', 'receiver', 'created_at']


class TrackSerializer(serializers.Serializer):
    track_ids = serializers.ListField(child=serializers.CharField())
