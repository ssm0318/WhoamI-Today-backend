from django.db import models, transaction
from django.db.models import Q, F
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from safedelete.models import SafeDeleteModel, SOFT_DELETE_CASCADE, HARD_DELETE

from adoorback.models import AdoorTimestampedModel


class PingRoom(AdoorTimestampedModel, SafeDeleteModel):
    user1 = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name='ping_rooms_as_user1'
    )
    user2 = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name='ping_rooms_as_user2'
    )

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user1', 'user2'], condition=Q(deleted__isnull=True), name='unique_ping_room'
            ),
            models.CheckConstraint(check=~Q(user1=F('user2')), name='no_self_ping_room')
        ]
        indexes = [
            models.Index(fields=['user1', 'user2']),
        ]

    def __str__(self):
        return f"PingRoom between {self.user1} and {self.user2}"
    
    def clean(self):
        super().clean()
        if not self.user1.is_connected(self.user2):
            raise ValidationError("Users in the pingroom must be friends.")
    
    def save(self, *args, **kwargs):
        self.full_clean()

        # check if reverse Connection already exists
        if PingRoom.objects.filter(user1=self.user2, user2=self.user1).exists():
            raise ValueError("A reverse Connection already exists.")
        
        # Ensure that user1 always has the smaller ID to enforce consistency
        if self.user1.id > self.user2.id:
            self.user1, self.user2 = self.user2, self.user1
        
        super().save(*args, **kwargs)


class Ping(AdoorTimestampedModel, SafeDeleteModel):
    PING_CHOICES = (
        ('wave', '👋'),
        ('smile', '😊'),
        ('heart', '❤️'),
        ('cry', '😭'),
        ('laugh', '🤣'),
    )

    ping_room = models.ForeignKey(PingRoom, on_delete=models.CASCADE, related_name='pings')
    sender = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, related_name='sent_pings')
    receiver = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, related_name='received_pings')
    emoji = models.CharField(max_length=20, choices=PING_CHOICES, blank=True, null=True)
    content = models.TextField(blank=True)

    is_read = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['ping_room', 'created_at']),
            models.Index(fields=['receiver', 'is_read']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sender} sent a {self.get_content_display()} ping to {self.receiver}"
    
    def clean(self):
        if not self.emoji and not self.content:
            raise ValidationError("Either an emoji or a content must be provided.")
        
        if not (
            (self.ping_room.user1 == self.sender and self.ping_room.user2 == self.receiver) or
            (self.ping_room.user1 == self.receiver and self.ping_room.user2 == self.sender)
        ):
            raise ValidationError("The sender and receiver must match the users in the ping room.")


    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


@transaction.atomic
def get_or_create_ping_room(user1, user2):
    if user1.id > user2.id:
        user1, user2 = user2, user1

    ping_room, created = PingRoom.objects.get_or_create(user1=user1, user2=user2)
    return ping_room


@transaction.atomic
def get_ping_room(user1, user2):
    if user1.id > user2.id:
        user1, user2 = user2, user1

    return PingRoom.objects.filter(user1=user1, user2=user2).first()


@transaction.atomic
def mark_pings_as_read(user, ping_room):
    Ping.objects.filter(receiver=user, ping_room=ping_room, is_read=False).update(is_read=True)
