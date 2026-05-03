from datetime import timedelta

from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.db import models, transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.utils import timezone

from adoorback.models import AdoorTimestampedModel

from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE, HARD_DELETE

from content_report.models import ContentReport
from comment.models import Comment
from like.models import Like
from notification.models import Notification

User = get_user_model()


def list_public():
    return ['public']


class CheckIn(AdoorTimestampedModel, SafeDeleteModel):
    SOCIAL_BATTERY_CHOICES = [
        ('completely_drained', 'Completely Drained'),
        ('low', 'Low Social Battery'),
        ('needs_recharge', 'Needs Recharge'),
        ('moderately_social', 'Moderately Social'),
        ('fully_charged', 'Fully Charged'),
        ('super_social', 'Super Social Mode (HMU!)'),
    ]

    user = models.ForeignKey(User, related_name='check_in_set', on_delete=models.CASCADE)
    is_active = models.BooleanField(default=False)
    mood = models.JSONField(default=list, blank=True)  # Array of emoji strings, max 5
    social_battery = models.CharField(blank=True, null=True, max_length=30, choices=SOCIAL_BATTERY_CHOICES)
    thought = models.CharField(blank=True, null=True, max_length=100)
    visibility = ArrayField(
        models.CharField(max_length=20),
        blank=True,
        default=list_public
    )

    # Per-component visibility
    VISIBILITY_CHOICES = [
        ('public', 'Public'),
        ('friends', 'Friends'),
        ('close_friends', 'Close Friends'),
        ('only_me', 'Only Me'),
    ]
    battery_visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='friends')
    mood_visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='friends')
    song_visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='public')
    thought_visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='friends')

    # Per-component update timestamps (for auto-archive after 12h)
    battery_updated_at = models.DateTimeField(null=True, blank=True)
    mood_updated_at = models.DateTimeField(null=True, blank=True)
    song_updated_at = models.DateTimeField(null=True, blank=True)
    thought_updated_at = models.DateTimeField(null=True, blank=True)

    readers = models.ManyToManyField(User, related_name='read_check_ins')

    _safedelete_policy = SOFT_DELETE_CASCADE

    def __str__(self):
        return self.thought or ""

    def save(self, *args, **kwargs):
        now = timezone.now()
        is_new = self.pk is None
        content_changed = False

        # Each item: (component, kind, data_or_None, visibility_or_None)
        # Replayed post-super() to keep CheckInComponentEntry in sync.
        pending_entry_ops = []

        if is_new:
            # Set all component timestamps on creation if content exists
            if self.social_battery:
                self.battery_updated_at = now
                pending_entry_ops.append((
                    'battery', 'create_or_update',
                    {'social_battery': self.social_battery},
                    self.battery_visibility,
                ))
            if self.mood:
                self.mood_updated_at = now
                pending_entry_ops.append((
                    'mood', 'create_or_update',
                    {'mood': list(self.mood)},
                    self.mood_visibility,
                ))
            if self.thought:
                self.thought_updated_at = now
                pending_entry_ops.append((
                    'thought', 'create_or_update',
                    {'thought': self.thought},
                    self.thought_visibility,
                ))
            # song_updated_at is set separately since Song is a separate model
        else:
            # On update, detect which fields changed and update their timestamps
            try:
                old = CheckIn.objects.get(pk=self.pk)
            except CheckIn.DoesNotExist:
                old = None

            if old:
                # Battery
                b_data_changed = self.social_battery != old.social_battery
                b_vis_changed = self.battery_visibility != old.battery_visibility
                if b_data_changed or b_vis_changed:
                    self.battery_updated_at = now
                    content_changed = True
                    if b_data_changed:
                        if self.social_battery:
                            pending_entry_ops.append((
                                'battery', 'create_or_update',
                                {'social_battery': self.social_battery},
                                self.battery_visibility,
                            ))
                        else:
                            pending_entry_ops.append(
                                ('battery', 'clear', None, None)
                            )
                    else:
                        pending_entry_ops.append((
                            'battery', 'visibility_only',
                            None, self.battery_visibility,
                        ))

                # Mood
                m_data_changed = self.mood != old.mood
                m_vis_changed = self.mood_visibility != old.mood_visibility
                if m_data_changed or m_vis_changed:
                    self.mood_updated_at = now
                    content_changed = True
                    if m_data_changed:
                        if self.mood:
                            pending_entry_ops.append((
                                'mood', 'create_or_update',
                                {'mood': list(self.mood)},
                                self.mood_visibility,
                            ))
                        else:
                            pending_entry_ops.append(
                                ('mood', 'clear', None, None)
                            )
                    else:
                        pending_entry_ops.append((
                            'mood', 'visibility_only',
                            None, self.mood_visibility,
                        ))

                # Thought
                t_data_changed = self.thought != old.thought
                t_vis_changed = self.thought_visibility != old.thought_visibility
                if t_data_changed or t_vis_changed:
                    self.thought_updated_at = now
                    content_changed = True
                    if t_data_changed:
                        if self.thought:
                            pending_entry_ops.append((
                                'thought', 'create_or_update',
                                {'thought': self.thought},
                                self.thought_visibility,
                            ))
                        else:
                            pending_entry_ops.append(
                                ('thought', 'clear', None, None)
                            )
                    else:
                        pending_entry_ops.append((
                            'thought', 'visibility_only',
                            None, self.thought_visibility,
                        ))

                # Song (data owned by Song model; visibility lives here)
                if self.song_visibility != old.song_visibility:
                    self.song_updated_at = now
                    content_changed = True
                    pending_entry_ops.append((
                        'song', 'visibility_only',
                        None, self.song_visibility,
                    ))

        super().save(*args, **kwargs)

        # 콘텐츠 변경 시 readers 초기화 (author만 유지)
        # outer transaction 밖에서 실행해 readers M2M 의 동시 INSERT 와의 deadlock 회피
        if content_changed and not is_new:
            ci_pk = self.pk
            author_id = self.user_id
            Through = type(self).readers.through

            def _reset_readers():
                Through.objects.filter(checkin_id=ci_pk).exclude(user_id=author_id).delete()
                Through.objects.get_or_create(checkin_id=ci_pk, user_id=author_id)

            transaction.on_commit(_reset_readers)

        # Replay component diffs into the entry table.
        if pending_entry_ops:
            with transaction.atomic():
                for component, kind, data, visibility in pending_entry_ops:
                    if kind == 'create_or_update':
                        CheckInComponentEntry.upsert_live(
                            owner=self.user,
                            component=component,
                            data=data,
                            visibility=visibility,
                            at=now,
                        )
                    elif kind == 'clear':
                        CheckInComponentEntry.supersede_live(
                            owner=self.user,
                            component=component,
                            at=now,
                        )
                    elif kind == 'visibility_only':
                        CheckInComponentEntry.update_live_visibility(
                            owner=self.user,
                            component=component,
                            visibility=visibility,
                        )

    @property
    def author(self):
        return self.user

    @property
    def content(self):
        return self.thought or (', '.join(self.mood) if self.mood else "") or ""

    @property
    def type(self):
        return self.__class__.__name__

    @property
    def reader_ids(self):
        return self.readers.values_list('id', flat=True)
    
    def is_audience(self, user):
        from account.models import Connection

        content_type = ContentType.objects.get_for_model(self)
        if ContentReport.objects.filter(user=user, content_type=content_type, object_id=self.pk).exists():
            return False

        if self.user.id in user.user_report_blocked_ids:
            return False

        if self.user == user:
            return True

        # Hierarchical Visibility Checks
        if 'public' in self.visibility:
            return True

        # Check Friend
        if 'friends' in self.visibility:
             # Check for connection
             if Connection.objects.filter(
                (models.Q(user1=self.user) & models.Q(user2=user)) | 
                (models.Q(user1=user) & models.Q(user2=self.user))
             ).exists():
                 return True
                 
        # Check Close Friend
        if 'close_friends' in self.visibility:
            if user.is_close_friend(self.user):
                # Upgrade logic
                connection = Connection.get_connection_between(self.user, user)
                if connection:
                    if self.user == connection.user1:
                        update_past_posts = connection.user1_update_past_posts
                        upgrade_time = connection.user1_upgrade_time
                    else:
                        update_past_posts = connection.user2_update_past_posts
                        upgrade_time = connection.user2_upgrade_time

                    if update_past_posts:
                        return True
                    elif upgrade_time is None:
                        return True
                    elif self.created_at > upgrade_time:
                        return True
        
        return False

    class Meta:
        indexes = [
            models.Index(fields=['is_active']),
        ]


class Song(AdoorTimestampedModel, SafeDeleteModel):
    user = models.ForeignKey(User, related_name='song_set', on_delete=models.CASCADE)
    is_active = models.BooleanField(default=False)
    track_id = models.CharField(max_length=50)

    _safedelete_policy = SOFT_DELETE_CASCADE

    def __str__(self):
        return self.track_id or ""

    class Meta:
        indexes = [
            models.Index(fields=['is_active']),
        ]


class CheckInComponentEntry(AdoorTimestampedModel, SafeDeleteModel):
    """
    A single snapshot of one check-in component (battery/mood/thought/song).

    Every component save creates a new entry. An entry is considered *live*
    when it is the most recent non-superseded row for (owner, component) and
    its created_at is within the 12h archive window. Once a newer entry is
    written for the same component, the prior row's superseded_at is set.

    Pinning is independent of the live/archive state: is_pinned + pin_visibility
    let the owner surface any past entry on their profile and on each friend
    card, with its own visibility decoupled from the original.
    """

    COMPONENT_CHOICES = [
        ('battery', 'Battery'),
        ('mood', 'Mood'),
        ('thought', 'Thought'),
        ('song', 'Song'),
    ]

    VISIBILITY_CHOICES = [
        ('public', 'Public'),
        ('friends', 'Friends'),
        ('close_friends', 'Close Friends'),
        ('only_me', 'Only Me'),
    ]

    owner = models.ForeignKey(
        User,
        related_name='check_in_entry_set',
        on_delete=models.CASCADE,
    )
    component = models.CharField(max_length=20, choices=COMPONENT_CHOICES)
    # Shape varies per component:
    #   battery: {"social_battery": "<choice>"}
    #   mood:    {"mood": ["🙂", ...]}            (up to 5 emoji strings)
    #   thought: {"thought": "<string>"}
    #   song:    {"track_id": "<spotify id>", "title": "<str>",
    #             "artist": "<str>", "album_cover_url": "<str>"}
    data = models.JSONField(default=dict, blank=True)
    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default='friends',
    )
    superseded_at = models.DateTimeField(null=True, blank=True)

    is_pinned = models.BooleanField(default=False)
    # null when not pinned; otherwise the pin's independent visibility
    pin_visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        null=True,
        blank=True,
    )

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner', 'component', '-created_at']),
            models.Index(fields=['owner', 'is_pinned']),
            models.Index(fields=['owner', 'component', 'superseded_at']),
        ]

    def __str__(self):
        return f"{self.owner.username} · {self.component} · {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def type(self):
        return self.__class__.__name__

    @classmethod
    def upsert_live(cls, *, owner, component, data, visibility, at=None):
        """
        Create or refresh the live entry for (owner, component).

        If the current live entry has identical `data`, only its `visibility`
        is updated in place (no new archive row). Otherwise the prior live
        entry's `superseded_at` is stamped with `at` and a new entry is
        inserted. Returns the entry that is live after the call.
        """
        at = at or timezone.now()
        current = (
            cls.objects
            .filter(owner=owner, component=component, superseded_at__isnull=True)
            .order_by('-created_at')
            .first()
        )
        if current and current.data == data:
            if current.visibility != visibility:
                current.visibility = visibility
                current.save(update_fields=['visibility', 'updated_at'])
            return current
        if current:
            cls.objects.filter(pk=current.pk).update(superseded_at=at)
        return cls.objects.create(
            owner=owner,
            component=component,
            data=data,
            visibility=visibility,
        )

    @classmethod
    def supersede_live(cls, *, owner, component, at=None):
        """Stamp the live entry (if any) for (owner, component) as superseded."""
        at = at or timezone.now()
        return cls.objects.filter(
            owner=owner, component=component, superseded_at__isnull=True
        ).update(superseded_at=at)

    @classmethod
    def update_live_visibility(cls, *, owner, component, visibility):
        """
        Update the live entry's visibility in place without creating a new row.

        Used when the user changes only the visibility setting for a component
        whose data is unchanged.
        """
        current = (
            cls.objects
            .filter(owner=owner, component=component, superseded_at__isnull=True)
            .order_by('-created_at')
            .first()
        )
        if current and current.visibility != visibility:
            current.visibility = visibility
            current.save(update_fields=['visibility', 'updated_at'])
        return current


class Poke(AdoorTimestampedModel, SafeDeleteModel):
    DAILY_POKE_LIMIT = 5

    COMPONENT_TYPE_CHOICES = [
        ('song', 'Song'),
        ('mood', 'Mood'),
        ('thought', 'Thought Snippet'),
        ('battery', 'Battery'),
    ]

    sender = models.ForeignKey(User, related_name='sent_pokes', on_delete=models.CASCADE)
    receiver = models.ForeignKey(User, related_name='received_pokes', on_delete=models.CASCADE)
    component_type = models.CharField(max_length=20, choices=COMPONENT_TYPE_CHOICES)

    poke_targetted_notis = GenericRelation(
        'notification.Notification',
        content_type_field='target_type',
        object_id_field='target_id',
    )

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        indexes = [
            models.Index(fields=['sender', 'created_at']),
            models.Index(fields=['receiver']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sender} poked {self.receiver} ({self.component_type})"

    @property
    def type(self):
        return self.__class__.__name__


@transaction.atomic
@receiver(post_save, sender=Poke, dispatch_uid='create_poke_notification')
def create_poke_notification(created, instance, **kwargs):
    if not created:
        return

    from notification.models import Notification, NotificationActor

    sender = instance.sender
    receiver = instance.receiver

    if receiver.id in sender.user_report_blocked_ids:
        return

    COMPONENT_LABELS_KO = {
        'song': '노래',
        'mood': '기분',
        'thought': '한마디',
        'battery': '소셜 배터리',
    }
    COMPONENT_LABELS_EN = {
        'song': 'song',
        'mood': 'mood',
        'thought': 'thought snippet',
        'battery': 'social battery',
    }

    label_ko = COMPONENT_LABELS_KO.get(instance.component_type, instance.component_type)
    label_en = COMPONENT_LABELS_EN.get(instance.component_type, instance.component_type)

    noti = Notification.objects.create(
        user=receiver,
        origin=sender,
        target=instance,
        message_ko=f"{sender.username}님이 {label_ko}을(를) 공유해달라고 콕 찔렀어요!",
        message_en=f"{sender.username} pinged you to share your {label_en}!",
        redirect_url=f"/update",
    )
    NotificationActor.objects.create(user=sender, notification=noti)


@transaction.atomic
@receiver(post_save, sender=CheckIn, dispatch_uid='add_user_to_readers')
def add_user_to_readers(instance, created, **kwargs):
    if not created:
        return
    instance.readers.add(instance.user)
    instance.save()


def _fetch_spotify_oembed(track_id, timeout=2):
    """Best-effort Spotify oEmbed resolution. Returns a dict or None on failure.

    Called synchronously from the Song post_save signal; the short timeout
    keeps the save path bounded even if Spotify is slow or unreachable.
    """
    import requests

    clean_id = track_id.rsplit(':', 1)[-1] if ':' in track_id else track_id
    url = (
        'https://open.spotify.com/oembed'
        f'?url=https://open.spotify.com/track/{clean_id}'
    )
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
    except (requests.RequestException, ValueError):
        pass
    return None


@transaction.atomic
@receiver(post_save, sender=Song, dispatch_uid='write_song_component_entry')
def write_song_component_entry(instance, created, **kwargs):
    """Mirror Song saves into the CheckInComponentEntry archive.

    * When a new active Song is created, resolve Spotify oEmbed best-effort
      and upsert a live song entry with the resolved metadata (or just
      `{track_id}` on fetch failure). Visibility is inherited from the user's
      active CheckIn's `song_visibility` (defaults to `public`).
    * When an existing Song is deactivated *and* it matches the current live
      song entry's track_id, supersede that entry. We guard on track_id so
      deactivating an old song right after a replacement doesn't accidentally
      retire the freshly-written new live entry.
    """
    if instance.is_active and created:
        active_ci = CheckIn.objects.filter(
            user=instance.user, is_active=True
        ).first()
        visibility = active_ci.song_visibility if active_ci else 'public'

        if active_ci:
            ci_pk = active_ci.pk
            author_id = instance.user_id
            Through = CheckIn.readers.through

            def _reset_readers():
                Through.objects.filter(checkin_id=ci_pk).exclude(user_id=author_id).delete()
                Through.objects.get_or_create(checkin_id=ci_pk, user_id=author_id)

            transaction.on_commit(_reset_readers)

        data = {'track_id': instance.track_id}
        oembed = _fetch_spotify_oembed(instance.track_id)
        if oembed:
            data['title'] = oembed.get('title')
            data['album_cover_url'] = oembed.get('thumbnail_url')
            # Spotify oEmbed does not expose artist separately; left blank
            # so the frontend can fall back to its own resolver if needed.
            data['artist'] = None

        CheckInComponentEntry.upsert_live(
            owner=instance.user,
            component='song',
            data=data,
            visibility=visibility,
        )
        return

    if not instance.is_active and not created:
        current_live = (
            CheckInComponentEntry.objects
            .filter(
                owner=instance.user,
                component='song',
                superseded_at__isnull=True,
            )
            .order_by('-created_at')
            .first()
        )
        if current_live and current_live.data.get('track_id') == instance.track_id:
            now = timezone.now()
            CheckInComponentEntry.objects.filter(pk=current_live.pk).update(
                superseded_at=now
            )


# ---------------------------------------------------------------------------
# CheckInPost (Ver.Q image+text "check-in" — Instagram-style story entity)
# ---------------------------------------------------------------------------

import urllib
import uuid
from django.conf import settings
from django.core.files.storage import FileSystemStorage


class CheckInPostStorage(FileSystemStorage):
    base_url = urllib.parse.urljoin(settings.BASE_URL, settings.MEDIA_URL)

    def get_available_name(self, name, max_length=None):
        if self.exists(name):
            self.delete(name)
        return name


def check_in_post_image_path(instance, filename):
    unique_id = str(uuid.uuid4())[:8]
    return f'check_in_post_images/{instance.author_id}/{unique_id}_{filename}'


def check_in_post_video_path(instance, filename):
    import os as _os
    unique_id = str(uuid.uuid4())[:8]
    ext = _os.path.splitext(filename)[1].lower() or '.mp4'
    return f'check_in_post_videos/{instance.author_id}/{unique_id}{ext}'


def check_in_post_video_thumbnail_path(instance, filename):
    unique_id = str(uuid.uuid4())[:8]
    return f'check_in_post_video_thumbnails/{instance.author_id}/{unique_id}.jpg'


CHECK_IN_POST_EXPIRY_HOURS = 24


class CheckInPost(AdoorTimestampedModel, SafeDeleteModel):
    VISIBILITY_CHOICES = [
        ('public', 'Public'),
        ('friends', 'Friends'),
        ('close_friends', 'Close Friends'),
    ]

    author = models.ForeignKey(User, related_name='check_in_post_set', on_delete=models.CASCADE)
    image = models.ImageField(upload_to=check_in_post_image_path, storage=CheckInPostStorage(), null=True, blank=True)
    caption = models.TextField(blank=True, default='')
    video = models.FileField(
        upload_to=check_in_post_video_path, storage=CheckInPostStorage(),
        null=True, blank=True,
    )
    video_thumbnail = models.ImageField(
        upload_to=check_in_post_video_thumbnail_path, storage=CheckInPostStorage(),
        null=True, blank=True,
    )
    video_duration_seconds = models.FloatField(null=True, blank=True)
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='friends')

    is_pinned = models.BooleanField(default=False)
    pin_visibility = models.CharField(
        max_length=20, choices=VISIBILITY_CHOICES, null=True, blank=True,
    )

    check_in_post_comments = GenericRelation(Comment)
    check_in_post_likes = GenericRelation(Like)
    readers = models.ManyToManyField(User, related_name='read_check_in_posts', blank=True)

    check_in_post_targetted_notis = GenericRelation(
        Notification,
        content_type_field='target_type',
        object_id_field='target_id',
    )
    check_in_post_originated_notis = GenericRelation(
        Notification,
        content_type_field='origin_type',
        object_id_field='origin_id',
    )

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['author', '-created_at']),
            models.Index(fields=['author', 'is_pinned'], name='check_in_ch_author_pinned_idx'),
        ]

    def __str__(self):
        return f'CheckInPost #{self.pk} by {self.author_id} ({self.visibility})'

    @property
    def type(self):
        return self.__class__.__name__

    @property
    def is_expired(self):
        return timezone.now() - self.created_at > timedelta(hours=CHECK_IN_POST_EXPIRY_HOURS)

    @property
    def participants(self):
        return self.check_in_post_comments.values_list('author_id', flat=True).distinct()

    def is_audience(self, user):
        """Visibility check for CheckInPost.

        Expired (>24h) posts are visible only to the author unless pinned; when pinned,
        the post's `pin_visibility` (set independently by the author) governs access.
        """
        content_type = ContentType.objects.get_for_model(self)
        if ContentReport.objects.filter(user=user, content_type=content_type, object_id=self.pk).exists():
            return False
        if self.author.id in user.user_report_blocked_ids:
            return False
        if self.author == user:
            return True

        if self.is_expired:
            if not self.is_pinned:
                return False
            visibility = self.pin_visibility
        else:
            visibility = self.visibility

        if visibility == 'public':
            return True
        if visibility == 'friends':
            return user.is_connected(self.author)
        if visibility == 'close_friends':
            return user.is_close_friend(self.author)
        return False


@receiver(post_delete, sender=CheckInPost, dispatch_uid='delete_check_in_post_files')
def delete_check_in_post_files(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)
    if instance.video:
        instance.video.delete(save=False)
    if instance.video_thumbnail:
        instance.video_thumbnail.delete(save=False)


@receiver(post_save, sender=CheckInPost, dispatch_uid='add_author_to_check_in_post_readers')
def add_author_to_check_in_post_readers(instance, created, **kwargs):
    # Author is NOT auto-added to readers so that the own-story bubble
    # shows the unread (purple ring) state until the author views it.
    pass
