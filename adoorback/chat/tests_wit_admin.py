from django.contrib.auth import get_user_model
from django.test import TestCase

from chat.models import ChatRoom, Message

User = get_user_model()


class WitAdminFieldsTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username='alice', email='alice@example.com', password='x')
        self.bob = User.objects.create_user(username='bob', email='bob@example.com', password='x')

    def test_chatroom_has_wit_admin_proxy_flag(self):
        room = ChatRoom.objects.create(user1=self.alice, user2=self.bob)
        self.assertFalse(room.is_wit_admin_proxy)

    def test_chatroom_has_blast_room_flag(self):
        room = ChatRoom.objects.create(user1=self.alice, user2=self.bob)
        self.assertFalse(room.is_wit_admin_blast_room)

    def test_message_has_mirror_flag(self):
        room = ChatRoom.objects.create(user1=self.alice, user2=self.bob)
        msg = Message.objects.create(chat_room=room, sender=self.alice, receiver=self.bob, content='hi')
        self.assertFalse(msg.is_wit_admin_mirror)


class WitAdminFlagsBackfillTests(TestCase):
    """Smoke check: after the backfill migration runs, every row must have False (not NULL)."""

    def test_all_chatrooms_have_non_null_flags(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        u1 = User.objects.create_user(username='u1', email='u1@example.com', password='x')
        u2 = User.objects.create_user(username='u2', email='u2@example.com', password='x')
        ChatRoom.objects.create(user1=u1, user2=u2)
        for room in ChatRoom.objects.all():
            self.assertIsNotNone(room.is_wit_admin_proxy)
            self.assertIsNotNone(room.is_wit_admin_blast_room)
