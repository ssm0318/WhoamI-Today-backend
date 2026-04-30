from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from chat.models import ChatRoom, Message

User = get_user_model()


class WitBotChatListTests(TestCase):
    def setUp(self):
        # Operators + alice + charlie (regular peer).
        User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        self.charlie = User.objects.create_user(username='charlie', email='c@e.com', password='x')
        from chat.wit_bot import ensure_wit_bot_user
        from chat.wit_admin import ensure_wit_admin_user
        self.bot = ensure_wit_bot_user()
        self.admin = ensure_wit_admin_user()

    def _list(self, user):
        from chat.views import ChatRoomList
        factory = APIRequestFactory()
        req = factory.get('/api/chat/rooms/')
        force_authenticate(req, user=user)
        resp = ChatRoomList.as_view()(req)
        return resp.data.get('results', resp.data)

    def _wit_bot_room(self, user):
        u1 = min(user, self.bot, key=lambda u: u.id)
        u2 = max(user, self.bot, key=lambda u: u.id)
        return ChatRoom.objects.get(user1=u1, user2=u2)

    def _wit_admin_room(self, user):
        u1 = min(user, self.admin, key=lambda x: x.id)
        u2 = max(user, self.admin, key=lambda x: x.id)
        return ChatRoom.objects.get(user1=u1, user2=u2, is_wit_admin_proxy=False)

    def test_wit_admin_pinned_first_then_wit_bot(self):
        results = self._list(self.alice)
        # Both system rooms must appear; wit_admin strictly precedes wit_bot.
        bot_room = self._wit_bot_room(self.alice)
        admin_room = self._wit_admin_room(self.alice)
        ids = [r['id'] for r in results]
        self.assertIn(bot_room.id, ids)
        self.assertIn(admin_room.id, ids)
        self.assertLess(ids.index(admin_room.id), ids.index(bot_room.id))

    def test_wit_bot_appears_even_with_no_messages(self):
        results = self._list(self.alice)
        bot_room = self._wit_bot_room(self.alice)
        ids = {r['id'] for r in results}
        self.assertIn(bot_room.id, ids)

    def test_promoted_group_keeps_pin_zero(self):
        from chat.wit_bot import escalate_to_human
        bot_room = self._wit_bot_room(self.alice)
        escalate_to_human(self.alice)
        # Make charlie chat with alice so a regular room competes for the top.
        from chat.models import get_or_create_chat_room
        peer = get_or_create_chat_room(self.alice, self.charlie)
        Message.objects.create(
            chat_room=peer, sender=self.charlie, receiver=self.alice, content='hey',
        )
        ids = [r['id'] for r in self._list(self.alice)]
        # Promoted group still leads.
        self.assertEqual(ids[0], bot_room.id)

    def test_version_isolation_does_not_hide_wit_bot(self):
        # Force alice and bot to different versions to confirm wit_bot rooms
        # are exempt from cross-version filtering.
        self.alice.current_ver = 'version_w'
        self.alice.save(update_fields=['current_ver'])
        self.bot.current_ver = 'version_q'
        self.bot.save(update_fields=['current_ver'])
        results = self._list(self.alice)
        bot_room = self._wit_bot_room(self.alice)
        ids = {r['id'] for r in results}
        self.assertIn(bot_room.id, ids)
