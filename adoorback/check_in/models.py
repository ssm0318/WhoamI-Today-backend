from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.utils import timezone

from adoorback.models import AdoorTimestampedModel

from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE

from content_report.models import ContentReport

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
    thought = models.CharField(blank=True, null=True, max_length=88)
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

        if is_new:
            # Set all component timestamps on creation if content exists
            if self.social_battery:
                self.battery_updated_at = now
            if self.mood:
                self.mood_updated_at = now
            if self.thought:
                self.thought_updated_at = now
            # song_updated_at is set separately since Song is a separate model
        else:
            # On update, detect which fields changed and update their timestamps
            try:
                old = CheckIn.objects.get(pk=self.pk)
            except CheckIn.DoesNotExist:
                old = None

            if old:
                if self.social_battery != old.social_battery or self.battery_visibility != old.battery_visibility:
                    self.battery_updated_at = now
                if self.mood != old.mood or self.mood_visibility != old.mood_visibility:
                    self.mood_updated_at = now
                if self.thought != old.thought or self.thought_visibility != old.thought_visibility:
                    self.thought_updated_at = now
                if self.song_visibility != old.song_visibility:
                    self.song_updated_at = now

        super().save(*args, **kwargs)

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
@receiver(post_save, sender=Poke)
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
        redirect_url=f"/check-in/",
    )
    NotificationActor.objects.create(user=sender, notification=noti)


@transaction.atomic
@receiver(post_save, sender=CheckIn)
def add_user_to_readers(instance, created, **kwargs):
    if not created:
        return
    instance.readers.add(instance.user)
    instance.save()
