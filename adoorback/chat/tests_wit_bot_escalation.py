from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from chat.models import ChatRoom, GroupReadCursor, Message

User = get_user_model()


class WitBotEscalationTests(TestCase):
    def setUp(self):
        User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        self.bob = User.objects.create_user(username='bob', email='b@e.com', password='x')
        from chat.wit_bot import ensure_wit_bot_room, ensure_wit_bot_user
        from chat.wit_admin import ensure_wit_admin_user
        self.bot = ensure_wit_bot_user()
        self.admin = ensure_wit_admin_user()
        self.alice_room = ensure_wit_bot_room(self.alice)
        self.bob_room = ensure_wit_bot_room(self.bob)

    def test_escalate_promotes_room_in_place(self):
        from chat.wit_bot import escalate_to_human
        # Pre-populate some history so we can check it survives.
        Message.objects.create(
            chat_room=self.alice_room, sender=self.alice, receiver=self.bot, content='msg1',
        )
        Message.objects.create(
            chat_room=self.alice_room, sender=self.bot, receiver=self.alice, content='reply1',
        )
        pre_count = Message.objects.filter(chat_room=self.alice_room).count()
        room = escalate_to_human(self.alice)
        room.refresh_from_db()
        # Same room, now flagged as a group with all 3 members.
        self.assertEqual(room.id, self.alice_room.id)
        self.assertTrue(room.is_group)
        self.assertEqual(
            set(room.members.values_list('id', flat=True)),
            {self.alice.id, self.bot.id, self.admin.id},
        )
        # History is preserved (plus 1 system 'member_added' event).
        post_count = Message.objects.filter(chat_room=room).count()
        self.assertEqual(post_count, pre_count + 1)

    def test_escalate_initializes_admin_read_cursor(self):
        from chat.wit_bot import escalate_to_human
        # Send a few messages, then escalate.
        for i in range(3):
            Message.objects.create(
                chat_room=self.alice_room, sender=self.alice, receiver=self.bot,
                content=f'msg{i}',
            )
        latest = Message.objects.filter(chat_room=self.alice_room).order_by('-created_at').first()
        escalate_to_human(self.alice)
        cursor = GroupReadCursor.objects.get(user=self.admin, chat_room=self.alice_room)
        self.assertIsNotNone(cursor.last_read_message)
        self.assertEqual(cursor.last_read_message_id, latest.id)

    def test_escalate_creates_admin_notification(self):
        from chat.wit_bot import escalate_to_human
        from notification.models import Notification
        escalate_to_human(self.alice)
        notis = Notification.objects.filter(user=self.admin)
        self.assertGreaterEqual(notis.count(), 1)
        # The latest one we just created should point at the chat group.
        latest = notis.order_by('-id').first()
        self.assertIn(f'/chats/group/{self.alice_room.id}', latest.redirect_url)

    def test_admin_can_read_escalated_group_history(self):
        from chat.wit_bot import escalate_to_human
        Message.objects.create(
            chat_room=self.alice_room, sender=self.alice, receiver=self.bot,
            content='private message',
        )
        escalate_to_human(self.alice)

        from chat.views import GroupChatUpdate
        factory = APIRequestFactory()
        req = factory.get(f'/api/chat/groups/{self.alice_room.id}/')
        force_authenticate(req, user=self.admin)
        resp = GroupChatUpdate.as_view()(req, pk=self.alice_room.id)
        self.assertEqual(resp.status_code, 200)

    def test_admin_cannot_read_non_escalated_other_room(self):
        # Bob's wit_bot 1-on-1 was never escalated; admin should NOT have access.
        # Convert it to a group ad-hoc to test the GroupChatUpdate path; 1-on-1
        # rooms aren't reachable via /chat/groups/ anyway, so the membership
        # check on the escalated room is the load-bearing one.
        from chat.wit_bot import escalate_to_human
        escalate_to_human(self.alice)
        # Admin is NOT a member of bob_room; admin querying chat list should
        # not see bob_room.
        from chat.views import ChatRoomList
        factory = APIRequestFactory()
        req = factory.get('/api/chat/rooms/')
        force_authenticate(req, user=self.admin)
        resp = ChatRoomList.as_view()(req)
        result_ids = {r['id'] for r in resp.data.get('results', resp.data)}
        self.assertNotIn(self.bob_room.id, result_ids)
        self.assertIn(self.alice_room.id, result_ids)

    def test_admin_loses_access_after_being_removed(self):
        from chat.wit_bot import escalate_to_human
        escalate_to_human(self.alice)
        # Alice removes admin via the standard PATCH flow.
        from chat.views import GroupChatUpdate
        factory = APIRequestFactory()
        req = factory.patch(
            f'/api/chat/groups/{self.alice_room.id}/',
            {'remove_member_ids': [self.admin.id]},
            format='json',
        )
        force_authenticate(req, user=self.alice)
        resp = GroupChatUpdate.as_view()(req, pk=self.alice_room.id)
        self.assertEqual(resp.status_code, 200)
        # Admin tries to GET the group — should now be 403.
        req2 = factory.get(f'/api/chat/groups/{self.alice_room.id}/')
        force_authenticate(req2, user=self.admin)
        resp2 = GroupChatUpdate.as_view()(req2, pk=self.alice_room.id)
        self.assertEqual(resp2.status_code, 403)
        # Members shrunk to alice + bot.
        self.alice_room.refresh_from_db()
        self.assertTrue(self.alice_room.is_group)
        self.assertEqual(
            set(self.alice_room.members.values_list('id', flat=True)),
            {self.alice.id, self.bot.id},
        )

    def test_engine_does_not_reply_after_escalation(self):
        from chat.wit_bot import escalate_to_human
        escalate_to_human(self.alice)
        self.alice_room.refresh_from_db()
        before = Message.objects.filter(
            chat_room=self.alice_room, sender=self.bot,
        ).count()
        # Alice sends a follow-up in the now-group room.
        Message.objects.create(
            chat_room=self.alice_room, sender=self.alice, receiver=None,
            content='still need help',
        )
        after = Message.objects.filter(
            chat_room=self.alice_room, sender=self.bot,
        ).count()
        self.assertEqual(before, after)
