from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from account.serializers import UserMinimalSerializer
from check_in.models import CheckIn, CheckInComponentEntry, Song, Poke

CHECKIN_AUTO_ARCHIVE_HOURS = 12


class CheckInBaseSerializer(serializers.ModelSerializer):
    # Live-read source: CheckInComponentEntry. The CheckIn table and Song
    # model are still being dual-written by the save path (see
    # CheckIn.save and the Song post_save signal) so auth/read parity is
    # preserved during the transition.

    current_user_read = serializers.SerializerMethodField(read_only=True)

    # Data fields sourced from the live component entries.
    social_battery = serializers.SerializerMethodField(read_only=True)
    mood = serializers.SerializerMethodField(read_only=True)
    thought = serializers.SerializerMethodField(read_only=True)

    # Visibility fields with the 12h auto-archive collapse applied.
    battery_visibility = serializers.SerializerMethodField(read_only=True)
    mood_visibility = serializers.SerializerMethodField(read_only=True)
    song_visibility = serializers.SerializerMethodField(read_only=True)
    thought_visibility = serializers.SerializerMethodField(read_only=True)

    # Updated-at fields sourced from the live entry's created_at.
    battery_updated_at = serializers.SerializerMethodField(read_only=True)
    mood_updated_at = serializers.SerializerMethodField(read_only=True)
    song_updated_at = serializers.SerializerMethodField(read_only=True)
    thought_updated_at = serializers.SerializerMethodField(read_only=True)

    # Song track_id still resolves via the Song model for this branch —
    # the song entry's data.track_id matches it by dual-write.
    track_id = serializers.SerializerMethodField(read_only=True)

    # ------ live-entry lookup, cached per request via self.context ------

    def _get_live_map(self, user):
        """Return {component: entry} of live entries for `user`.

        Cached on `self.context` so a list view renders N users with N
        queries (one per user) rather than 4N.
        """
        cache = self.context.setdefault('_ci_live_entries', {})
        if user.id not in cache:
            entries = (
                CheckInComponentEntry.objects
                .filter(owner=user, superseded_at__isnull=True)
                .order_by('component', '-created_at')
            )
            per_component = {}
            for e in entries:
                # order_by puts the most recent first within each component
                per_component.setdefault(e.component, e)
            cache[user.id] = per_component
        return cache[user.id]

    def _live_entry(self, obj, component):
        return self._get_live_map(obj.user).get(component)

    @staticmethod
    def _is_archived(entry):
        if entry is None:
            return True
        age = timezone.now() - entry.created_at
        return age > timedelta(hours=CHECKIN_AUTO_ARCHIVE_HOURS)

    # ------ data fields ------

    def get_social_battery(self, obj):
        entry = self._live_entry(obj, 'battery')
        return entry.data.get('social_battery', '') if entry else ''

    def get_mood(self, obj):
        entry = self._live_entry(obj, 'mood')
        return entry.data.get('mood', []) if entry else []

    def get_thought(self, obj):
        entry = self._live_entry(obj, 'thought')
        return entry.data.get('thought', '') if entry else ''

    # ------ visibility fields (12h archive collapse) ------

    def get_battery_visibility(self, obj):
        entry = self._live_entry(obj, 'battery')
        if self._is_archived(entry):
            return 'only_me'
        return entry.visibility

    def get_mood_visibility(self, obj):
        entry = self._live_entry(obj, 'mood')
        if self._is_archived(entry):
            return 'only_me'
        return entry.visibility

    def get_song_visibility(self, obj):
        entry = self._live_entry(obj, 'song')
        if self._is_archived(entry):
            return 'only_me'
        return entry.visibility

    def get_thought_visibility(self, obj):
        entry = self._live_entry(obj, 'thought')
        if self._is_archived(entry):
            return 'only_me'
        return entry.visibility

    # ------ *_updated_at fields ------

    def get_battery_updated_at(self, obj):
        entry = self._live_entry(obj, 'battery')
        return entry.created_at if entry else None

    def get_mood_updated_at(self, obj):
        entry = self._live_entry(obj, 'mood')
        return entry.created_at if entry else None

    def get_song_updated_at(self, obj):
        entry = self._live_entry(obj, 'song')
        return entry.created_at if entry else None

    def get_thought_updated_at(self, obj):
        entry = self._live_entry(obj, 'thought')
        return entry.created_at if entry else None

    # ------ misc ------

    def get_current_user_read(self, obj):
        current_user_id = self.context['request'].user.id
        return current_user_id in obj.reader_ids

    def get_track_id(self, obj):
        song = obj.user.song_set.filter(is_active=True).first()
        return song.track_id if song else ''

    class Meta:
        model = CheckIn
        fields = ['id', 'created_at', 'is_active', 'mood',
                  'social_battery', 'thought', 'current_user_read', 'visibility',
                  'battery_visibility', 'mood_visibility', 'song_visibility', 'thought_visibility',
                  'battery_updated_at', 'mood_updated_at', 'song_updated_at', 'thought_updated_at',
                  'track_id']


class MyCheckInSerializer(CheckInBaseSerializer):
    # Writable versions of the data + visibility fields. These overrides
    # restore write-ability (the base declares them as SerializerMethodField
    # for live-read from CheckInComponentEntry). CheckIn.save handles the
    # dual-write back into the entry table.
    social_battery = serializers.ChoiceField(
        choices=CheckIn.SOCIAL_BATTERY_CHOICES,
        required=False, allow_blank=True, allow_null=True,
    )
    mood = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True,
    )
    thought = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=100,
    )
    battery_visibility = serializers.ChoiceField(
        choices=['public', 'friends', 'close_friends', 'only_me'],
        required=False,
    )
    mood_visibility = serializers.ChoiceField(
        choices=['public', 'friends', 'close_friends', 'only_me'],
        required=False,
    )
    song_visibility = serializers.ChoiceField(
        choices=['public', 'friends', 'close_friends', 'only_me'],
        required=False,
    )
    thought_visibility = serializers.ChoiceField(
        choices=['public', 'friends', 'close_friends', 'only_me'],
        required=False,
    )

    class Meta:
        model = CheckIn
        fields = CheckInBaseSerializer.Meta.fields
        extra_kwargs = {
            'visibility': {'required': True},
            'mood': {'required': False},
            'battery_updated_at': {'read_only': True},
            'mood_updated_at': {'read_only': True},
            'song_updated_at': {'read_only': True},
            'thought_updated_at': {'read_only': True},
        }

    def to_representation(self, instance):
        # Base class's SerializerMethodField getters drive the response so
        # the owner's own view is also sourced from the entry table — keeping
        # a single source of truth for reads.
        return super().to_representation(instance)

    def validate_mood(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("mood must be a list of emoji strings.")
        if len(value) > 5:
            raise serializers.ValidationError("Maximum 5 mood emojis allowed.")
        return value

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
