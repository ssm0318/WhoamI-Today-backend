from django.db import models

from django.contrib.auth import get_user_model

from adoorback.models import AdoorModel, AdoorTimestampedModel
from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE

User = get_user_model()

class ChatRoom(AdoorTimestampedModel, SafeDeleteModel):
    users = models.ManyToManyField(User, related_name='chat_rooms')
    active = models.BooleanField(default=True)

    _safedelete_policy = SOFT_DELETE_CASCADE

    def __str__(self):
        return f"chatroom of {', '.join([user.username for user in self.users.all()])}"

    @property
    def last_message_content(self):
        return self.messages.last().content

    @property
    def last_message_time(self):
        return self.messages.last().timestamp


class Message(AdoorModel, SafeDeleteModel):
    sender = models.ForeignKey(User, related_name='sent_messages', on_delete=models.CASCADE)
    chat_room = models.ForeignKey(ChatRoom, related_name='messages', on_delete=models.CASCADE)
    timestamp = models.DateTimeField(blank=False, null=False, default='2008-10-03')

    _safedelete_policy = SOFT_DELETE_CASCADE
