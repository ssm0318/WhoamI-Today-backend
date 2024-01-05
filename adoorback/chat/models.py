from django.db import models

from django.contrib.auth import get_user_model

from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE

User = get_user_model()

class ChatRoom(SafeDeleteModel):
    users = models.ManyToManyField(User, related_name='chat_rooms')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    _safedelete_policy = SOFT_DELETE_CASCADE

    def __str__(self):
        return ', '.join([user.username for user in self.users.all()])

    @property
    def last_message_content(self):
        return self.messages.last().content

    @property
    def last_message_time(self):
        return self.messages.last().created_at

class Message(SafeDeleteModel):
    sender = models.ForeignKey(User, related_name='sent_messages', on_delete=models.CASCADE)
    content = models.TextField()
    chat_room = models.ForeignKey(ChatRoom, related_name='messages', on_delete=models.CASCADE)
    timestamp = models.DateTimeField(blank=False, null=False, default='2008-10-03')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    _safedelete_policy = SOFT_DELETE_CASCADE

