from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.signals import m2m_changed, post_save, pre_save, post_delete
from django.dispatch import receiver

from firebase_admin.messaging import Message
from fcm_django.models import FCMDevice

from adoorback.models import AdoorModel, AdoorTimestampedModel
from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE


DEFAULT_TIMESTAMP = '2008-10-03'
User = get_user_model()


class ChatRoom(AdoorTimestampedModel, SafeDeleteModel):
    users = models.ManyToManyField(User, related_name='chat_rooms')
    active = models.BooleanField(default=True)

    _safedelete_policy = SOFT_DELETE_CASCADE

    def __str__(self):
        return f"chatroom of {', '.join([user.username for user in self.users.all()])}"

    def clean(self):
        super().clean()
        # Check if users in the chatroom are friends
        for user in self.users.all():
            for other_user in self.users.exclude(id=user.id):
                if not User.are_friends(user, other_user):
                    raise ValidationError("All users in the chatroom must be friends.")

    @property
    def last_message_content(self):
        return self.messages.last().content

    @property
    def last_message_time(self):
        return self.messages.last().timestamp

    def unread_cnt(self, user):
        if user not in self.users.all():
            return -1

        user_last_msg = self.chat_activities.filter(user=user).first().last_read_message
        if user_last_msg:
            threshold_id = user_last_msg.id
        else:
            threshold_id = 0
        return self.messages.filter(id__gt=threshold_id).count()


class Message(AdoorModel, SafeDeleteModel):
    sender = models.ForeignKey(User, related_name='sent_messages', on_delete=models.CASCADE)
    chat_room = models.ForeignKey(ChatRoom, related_name='messages', on_delete=models.CASCADE)
    timestamp = models.DateTimeField(blank=False, null=False, default=DEFAULT_TIMESTAMP)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')

    _safedelete_policy = SOFT_DELETE_CASCADE

    def __str__(self):
        return f"Message from {self.sender} in {self.chat_room}: {self.content}"
    
    @property
    def read_users_cnt(self):
        return UserChatActivity.objects.filter(
            last_read_message__chat_room=self.chat_room, 
            last_read_message__id__gte=self.id
        ).count()

    @property
    def unread_users_cnt(self):
        return self.chat_room.users.count() - self.read_users_cnt()


class UserChatActivity(AdoorTimestampedModel, SafeDeleteModel):
    user = models.ForeignKey(User, related_name='chat_activities', on_delete=models.CASCADE)
    chat_room = models.ForeignKey(ChatRoom, related_name='chat_activities', on_delete=models.CASCADE)
    last_read_message = models.ForeignKey(Message, on_delete=models.SET_NULL, null=True, blank=True)

    _safedelete_policy = SOFT_DELETE_CASCADE

    def __str__(self):
        last_read_message_id = self.last_read_message.id if self.last_read_message else "None"
        return f"{self.user} in chat room {self.chat_room.id} last read message {last_read_message_id}"

    class Meta:
        unique_together = ('user', 'chat_room')


@transaction.atomic
@receiver(m2m_changed, sender=ChatRoom.users.through)
def create_user_chat_activities(sender, instance, action, pk_set, **kwargs):
    if action == "post_add":
        for user_id in pk_set:
            user = User.objects.get(pk=user_id)
            UserChatActivity.objects.create(user=user, chat_room=instance)


@transaction.atomic
@receiver(post_save, sender=Message)
def sender_read_message(created, instance, **kwargs):
    if created:
        # Update last read message for the sender
        user_activity, _ = UserChatActivity.objects.get_or_create(
            user_id=instance.sender.id, chat_room_id=instance.chat_room.id
        )
        user_activity.last_read_message_id = instance.id
        user_activity.save()


@receiver(post_save, sender=ChatRoom)
def validate_chatroom(sender, instance, **kwargs):
    instance.full_clean()
