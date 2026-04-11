from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models, transaction
from django.db.models import Q, F
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.utils import timezone
from safedelete.models import SafeDeleteModel, SOFT_DELETE_CASCADE

from adoorback.models import AdoorTimestampedModel
from notification.models import Notification, NotificationActor


MAX_GROUP_MEMBERS = 10


class ChatRoom(AdoorTimestampedModel, SafeDeleteModel):
    # 1-on-1 fields (kept for backward compat)
    user1 = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name='chat_rooms_as_user1',
        null=True, blank=True,
    )
    user2 = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name='chat_rooms_as_user2',
        null=True, blank=True,
    )

    # Group fields
    is_group = models.BooleanField(default=False)
    name = models.CharField(max_length=100, blank=True, default='')
    members = models.ManyToManyField(get_user_model(), related_name='group_chat_rooms', blank=True)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user1', 'user2'], condition=Q(deleted__isnull=True, is_group=False), name='unique_chat_room'
            ),
            models.CheckConstraint(check=~Q(user1=F('user2')), name='no_self_chat_room')
        ]
        indexes = [
            models.Index(fields=['user1', 'user2']),
        ]

    def __str__(self):
        if self.is_group:
            return f"Group: {self.name or self.id}"
        return f"ChatRoom between {self.user1} and {self.user2}"

    def get_all_member_ids(self):
        if self.is_group:
            return list(self.members.values_list('id', flat=True))
        return [self.user1_id, self.user2_id]

    def save(self, *args, **kwargs):
        if self.deleted:
            super().save(*args, **kwargs)
            return

        if not self.is_group:
            self.full_clean()
            if self.user1_id and self.user2_id:
                if ChatRoom.objects.filter(user1=self.user2, user2=self.user1).exclude(pk=self.pk).exists():
                    raise ValueError("A reverse ChatRoom already exists.")
                if self.user1.id > self.user2.id:
                    self.user1, self.user2 = self.user2, self.user1

        super().save(*args, **kwargs)


MESSAGE_EMOJI_CHOICES = (
    ('wave', '👋'),
    ('smile', '😊'),
    ('heart', '❤️'),
    ('cry', '😭'),
    ('laugh', '🤣'),
)


class Message(AdoorTimestampedModel, SafeDeleteModel):
    chat_room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, related_name='received_messages', null=True, blank=True)
    emoji = models.CharField(max_length=20, choices=MESSAGE_EMOJI_CHOICES, blank=True, null=True)
    content = models.TextField(blank=True, validators=[MaxLengthValidator(10000)])
    image = models.ImageField(upload_to='chat_images/', blank=True, null=True)
    is_read = models.BooleanField(default=False)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')

    # Shared content (Note, Response, Question, etc.)
    shared_content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    shared_object_id = models.PositiveIntegerField(null=True, blank=True)
    shared_content = GenericForeignKey('shared_content_type', 'shared_object_id')

    message_notis = GenericRelation(
        Notification, content_type_field='target_type', object_id_field='target_id'
    )

    class Meta:
        indexes = [
            models.Index(fields=['chat_room', 'created_at']),
            models.Index(fields=['receiver', 'is_read']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sender} -> {self.receiver}: {self.content or self.emoji}"

    @property
    def type(self):
        return self.__class__.__name__

    def clean(self):
        if not self.emoji and not self.content and not self.shared_object_id and not self.image:
            raise ValidationError("Either an emoji, content, image, or shared content must be provided.")

        if self.chat_room.is_group:
            return  # Group messages don't validate sender/receiver pair

        if not (
            (self.chat_room.user1 == self.sender and self.chat_room.user2 == self.receiver) or
            (self.chat_room.user1 == self.receiver and self.chat_room.user2 == self.sender)
        ):
            raise ValidationError("The sender and receiver must match the users in the chat room.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MessageReaction(AdoorTimestampedModel, SafeDeleteModel):
    user = models.ForeignKey(get_user_model(), related_name='message_reactions', on_delete=models.CASCADE)
    message = models.ForeignKey(Message, related_name='reactions', on_delete=models.CASCADE)
    emoji = models.CharField(max_length=20)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'message', 'emoji'],
                condition=Q(deleted__isnull=True),
                name='unique_message_reaction'
            ),
        ]
        ordering = ['created_at']

    def __str__(self):
        return f"{self.user} reacted {self.emoji} to message {self.message_id}"


class GroupReadCursor(models.Model):
    """Tracks the last read message per user per group chat room."""
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, related_name='group_read_cursors')
    chat_room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='read_cursors')
    last_read_message = models.ForeignKey(Message, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'chat_room'], name='unique_group_read_cursor'),
        ]

    def __str__(self):
        return f"{self.user} read up to msg {self.last_read_message_id} in room {self.chat_room_id}"


class ChatRequest(AdoorTimestampedModel, SafeDeleteModel):
    """Chat request for non-friends. Must be accepted before messaging is allowed."""
    requester = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name='sent_chat_requests'
    )
    requestee = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name='received_chat_requests'
    )
    accepted = models.BooleanField(null=True, default=None)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['requester', 'requestee'],
                condition=Q(deleted__isnull=True),
                name='unique_chat_request'
            ),
            models.CheckConstraint(
                check=~Q(requester=F('requestee')),
                name='no_self_chat_request'
            )
        ]
        ordering = ['-created_at']

    def __str__(self):
        status = 'pending' if self.accepted is None else ('accepted' if self.accepted else 'declined')
        return f"ChatRequest from {self.requester} to {self.requestee} ({status})"


@transaction.atomic
def get_or_create_chat_room(user1, user2):
    if user1.id > user2.id:
        user1, user2 = user2, user1
    chat_room, _ = ChatRoom.objects.get_or_create(user1=user1, user2=user2)
    return chat_room


@transaction.atomic
def get_chat_room(user1, user2):
    if user1.id > user2.id:
        user1, user2 = user2, user1
    return ChatRoom.objects.filter(user1=user1, user2=user2).first()


@transaction.atomic
@receiver(post_save, sender=Message)
def create_message_notification(created, instance, **kwargs):
    if not created:
        return

    receiver_user = instance.receiver
    sender = instance.sender

    # Skip notifications for group messages (no single receiver)
    if receiver_user is None:
        return

    if receiver_user.id in sender.user_report_blocked_ids:
        return

    recent_noti = Notification.objects.find_recent_message(receiver_user, sender)

    if recent_noti:
        current_count = 1
        if "메시지를" in recent_noti.message_ko:
            try:
                current_count = int(recent_noti.message_ko.split("님이 ")[1].split("메시지를")[0][0])
            except (IndexError, ValueError):
                pass

        new_count = current_count + 1
        recent_noti.message_ko = f"{sender.username}님이 {new_count}개의 메시지를 보냈습니다!"
        recent_noti.message_en = f"{sender.username} sent you {new_count} messages!"
        recent_noti.notification_updated_at = timezone.now()
        recent_noti.save()

        NotificationActor.objects.create(user=sender, notification=recent_noti)
    else:
        noti = Notification.objects.create(
            user=receiver_user,
            origin=sender,
            target=instance,
            message_ko=f"{sender.username}님이 메시지를 보냈습니다!",
            message_en=f"{sender.username} sent you a message!",
            redirect_url=f"/users/{sender.id}/chat",
        )
        NotificationActor.objects.create(user=sender, notification=noti)
