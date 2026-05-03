from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework import serializers

from django.db.models import Q

from account.serializers import UserMinimalSerializer
from check_in.models import CheckIn, CheckInComponentEntry, CheckInPost, Song, Poke
from comment.models import Comment
from content_report.models import ContentReport
from like.models import Like

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

    # Updated-at fields sourced from the live entry's updated_at.
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
        age = timezone.now() - entry.updated_at
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
        return entry.updated_at if entry else None

    def get_mood_updated_at(self, obj):
        entry = self._live_entry(obj, 'mood')
        return entry.updated_at if entry else None

    def get_song_updated_at(self, obj):
        entry = self._live_entry(obj, 'song')
        return entry.updated_at if entry else None

    def get_thought_updated_at(self, obj):
        entry = self._live_entry(obj, 'thought')
        return entry.updated_at if entry else None

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


class ArchiveEntrySerializer(serializers.ModelSerializer):
    """Read serializer for the owner's archive feed.

    Surfaces every field needed to render a square card in the 2-col grid:
    the component type and payload, the entry's visibility (for the pin's
    inherited value and the per-card ⋯ → modify visibility modal), the
    pin state + its independent visibility, and the original created_at
    timestamp (the grid groups by date and renders timestamps relative
    for <7d old / absolute otherwise).
    """

    class Meta:
        model = CheckInComponentEntry
        fields = [
            'id',
            'component',
            'data',
            'visibility',
            'is_pinned',
            'pin_visibility',
            'created_at',
            'superseded_at',
        ]
        read_only_fields = fields


class PokeSerializer(serializers.ModelSerializer):
    receiver_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Poke
        fields = ['id', 'sender', 'receiver', 'receiver_id', 'component_type', 'created_at']
        read_only_fields = ['id', 'sender', 'receiver', 'created_at']


class TrackSerializer(serializers.Serializer):
    track_ids = serializers.ListField(child=serializers.CharField())


class CheckInPostSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField(read_only=True)
    author_detail = UserMinimalSerializer(source='author', read_only=True)
    image_url = serializers.SerializerMethodField(read_only=True)
    image = serializers.ImageField(write_only=True, required=False)
    video = serializers.FileField(write_only=True, required=False)
    video_url = serializers.SerializerMethodField(read_only=True)
    video_thumbnail_url = serializers.SerializerMethodField(read_only=True)
    video_duration_seconds = serializers.FloatField(read_only=True)
    visibility = serializers.ChoiceField(
        choices=[('public', 'Public'), ('friends', 'Friends'), ('close_friends', 'Close Friends')],
        default='friends',
    )
    like_count = serializers.SerializerMethodField(read_only=True)
    current_user_like_id = serializers.SerializerMethodField(read_only=True)
    comment_count = serializers.SerializerMethodField(read_only=True)
    current_user_read = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CheckInPost
        fields = [
            'id', 'type',
            'author_detail',
            'image', 'image_url',
            'video', 'video_url', 'video_thumbnail_url', 'video_duration_seconds',
            'caption',
            'visibility',
            'is_pinned', 'pin_visibility',
            'created_at',
            'like_count', 'current_user_like_id',
            'comment_count',
            'current_user_read',
        ]
        read_only_fields = ['id', 'type', 'author_detail', 'image_url', 'created_at',
                            'is_pinned', 'pin_visibility',
                            'video_url', 'video_thumbnail_url', 'video_duration_seconds',
                            'like_count', 'current_user_like_id',
                            'comment_count',
                            'current_user_read']

    def validate(self, attrs):
        has_image = bool(attrs.get('image'))
        has_video = bool(attrs.get('video'))
        if not has_image and not has_video:
            raise serializers.ValidationError('이미지 또는 동영상 중 하나를 포함해야 합니다.')
        return attrs

    def get_type(self, obj):
        return 'CheckInPost'

    def get_image_url(self, obj):
        if not obj.image:
            return None
        try:
            return obj.image.url
        except Exception:
            return None

    def get_video_url(self, obj):
        if not obj.video:
            return None
        try:
            return obj.video.url
        except Exception:
            return None

    def get_video_thumbnail_url(self, obj):
        if not obj.video_thumbnail:
            return None
        try:
            return obj.video_thumbnail.url
        except Exception:
            return None

    def get_like_count(self, obj):
        request = self.context.get('request')
        if request is None or not request.user.is_authenticated:
            return None
        if not obj.is_audience(request.user):
            return None
        blocked_user_ids = request.user.user_report_blocked_ids
        return obj.check_in_post_likes.exclude(user_id__in=blocked_user_ids).count()

    def get_current_user_like_id(self, obj):
        request = self.context.get('request')
        if request is None or not request.user.is_authenticated:
            return None
        ct = ContentType.objects.get_for_model(CheckInPost)
        like = Like.objects.filter(
            user_id=request.user.id, content_type_id=ct.id, object_id=obj.id,
        ).first()
        return like.id if like else None

    def get_comment_count(self, obj):
        request = self.context.get('request')
        if request is None or not request.user.is_authenticated:
            return 0
        current_user = request.user
        blocked_user_ids = current_user.user_report_blocked_ids
        comment_ct = ContentType.objects.get_for_model(Comment)
        blocked_comment_ids = ContentReport.objects.filter(
            user=current_user, content_type=comment_ct,
        ).values_list('object_id', flat=True)

        def _filter(qs):
            return qs.exclude(
                Q(id__in=blocked_comment_ids) | Q(author_id__in=blocked_user_ids)
            )

        comments = _filter(obj.check_in_post_comments.all())
        replies = sum(_filter(c.replies.all()).count() for c in comments)
        return comments.count() + replies

    def get_current_user_read(self, obj):
        request = self.context.get('request')
        if request is None or not request.user.is_authenticated:
            return False
        return obj.readers.filter(id=request.user.id).exists()


class CheckInPostFriendStorySerializer(serializers.ModelSerializer):
    """Compact serializer for the friend's stories strip — id + author + thumbnail."""
    author_detail = UserMinimalSerializer(source='author', read_only=True)
    image_url = serializers.SerializerMethodField(read_only=True)
    video_url = serializers.SerializerMethodField(read_only=True)
    video_thumbnail_url = serializers.SerializerMethodField(read_only=True)
    current_user_read = serializers.SerializerMethodField(read_only=True)
    has_unread = serializers.SerializerMethodField(read_only=True)
    like_count = serializers.SerializerMethodField(read_only=True)
    comment_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CheckInPost
        fields = ['id', 'author_detail', 'image_url',
                  'video_url', 'video_thumbnail_url',
                  'caption', 'visibility',
                  'is_pinned', 'pin_visibility', 'created_at',
                  'current_user_read', 'has_unread', 'like_count',
                  'comment_count']

    def get_like_count(self, obj):
        request = self.context.get('request')
        if request is None or not request.user.is_authenticated:
            return None
        if not obj.is_audience(request.user):
            return None
        blocked_ids = request.user.user_report_blocked_ids
        return obj.check_in_post_likes.exclude(user_id__in=blocked_ids).count()

    def get_comment_count(self, obj):
        request = self.context.get('request')
        if request is None or obj.author != request.user:
            return None
        blocked_ids = request.user.user_report_blocked_ids
        return obj.check_in_post_comments.exclude(author_id__in=blocked_ids).count()

    def get_current_user_read(self, obj):
        request = self.context.get('request')
        if request is None or not request.user.is_authenticated:
            return False
        return obj.readers.filter(id=request.user.id).exists()

    def get_has_unread(self, obj):
        """True if the author has any live post not yet read by the viewer.
        Populated via annotation in CheckInPostStories; falls back to False."""
        return getattr(obj, '_has_unread', False)

    def get_image_url(self, obj):
        if not obj.image:
            return None
        try:
            return obj.image.url
        except Exception:
            return None

    def get_video_url(self, obj):
        if not obj.video:
            return None
        try:
            return obj.video.url
        except Exception:
            return None

    def get_video_thumbnail_url(self, obj):
        if not obj.video_thumbnail:
            return None
        try:
            return obj.video_thumbnail.url
        except Exception:
            return None
