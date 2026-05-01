from django.contrib.auth import get_user_model
from django.test import TestCase

from chat.models import ChatRoom, Message

User = get_user_model()


class WitBotBetaLoopTests(TestCase):
    def setUp(self):
        # Operators (so the wit_admin auto-provision succeeds) + alice.
        User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        from chat.wit_bot import ensure_wit_bot_user
        self.bot = ensure_wit_bot_user()
        # The signup signal already provisioned the room + welcome message.
        from django.db.models import Q
        self.room = ChatRoom.objects.get(
            (Q(user1=self.alice) & Q(user2=self.bot))
            | (Q(user1=self.bot) & Q(user2=self.alice))
        )

    def _send_text(self, text, sender=None):
        sender = sender or self.alice
        return Message.objects.create(
            chat_room=self.room, sender=sender, receiver=self.bot,
            content=text,
        )

    def _send_choice(self, payload, label=''):
        """Simulate a frontend button tap."""
        return Message.objects.create(
            chat_room=self.room, sender=self.alice, receiver=self.bot,
            content=label or payload,
            bot_payload={'kind': 'choice', 'payload': payload},
        )

    def _bot_replies(self):
        return Message.objects.filter(chat_room=self.room, sender=self.bot)

    # ---------- Free-text loop ----------

    def test_free_text_replies_hehe_with_card(self):
        before = self._bot_replies().count()
        self._send_text('what is this app')
        replies = self._bot_replies().order_by('-created_at')
        self.assertEqual(replies.count(), before + 1)
        latest = replies.first()
        self.assertEqual(latest.content, 'hehe!')
        self.assertEqual(latest.bot_payload.get('kind'), 'card')
        labels = [b['label'] for b in latest.bot_payload['buttons']]
        self.assertEqual(labels, [
            'Get started with onboarding',
            "I'm confused",
            'tehehe',
            'Call in the admin',
        ])

    # ---------- Joke buttons all loop the same way ----------

    def test_onboarding_choice_replies_hehe(self):
        before = self._bot_replies().count()
        self._send_choice('onboarding', 'Get started with onboarding')
        latest = self._bot_replies().order_by('-created_at').first()
        self.assertEqual(self._bot_replies().count(), before + 1)
        self.assertEqual(latest.content, 'hehe!')
        self.assertEqual(latest.bot_payload['kind'], 'card')

    def test_confused_choice_replies_hehe(self):
        before = self._bot_replies().count()
        self._send_choice('confused', "I'm confused")
        latest = self._bot_replies().order_by('-created_at').first()
        self.assertEqual(self._bot_replies().count(), before + 1)
        self.assertEqual(latest.content, 'hehe!')

    def test_tehehe_choice_replies_hehe(self):
        before = self._bot_replies().count()
        self._send_choice('tehehe', 'tehehe')
        latest = self._bot_replies().order_by('-created_at').first()
        self.assertEqual(self._bot_replies().count(), before + 1)
        self.assertEqual(latest.content, 'hehe!')

    # ---------- Admin button escalates ----------

    def test_admin_choice_escalates_and_acks(self):
        from chat.wit_admin import ensure_wit_admin_user
        admin = ensure_wit_admin_user()
        self._send_choice('admin', 'Call in the admin')
        # Room is now a 3-member group with admin added.
        self.room.refresh_from_db()
        self.assertTrue(self.room.is_group)
        member_ids = set(self.room.members.values_list('id', flat=True))
        self.assertEqual(member_ids, {self.alice.id, self.bot.id, admin.id})
        # Bot acknowledged the escalation (no buttons on the ack).
        ack = self._bot_replies().order_by('-created_at').first()
        self.assertEqual(ack.content, 'Admin has been called in 👀')
        self.assertIsNone(ack.bot_payload)

    # ---------- Loop guards ----------

    def test_bot_does_not_reply_to_self(self):
        before = self._bot_replies().count()
        Message.objects.create(
            chat_room=self.room, sender=self.bot, receiver=self.alice,
            content='hi from bot',
        )
        # Only the message we just created — no engine reply on top.
        self.assertEqual(self._bot_replies().count(), before + 1)

    def test_system_event_does_not_trigger_engine(self):
        before = self._bot_replies().count()
        Message.objects.create(
            chat_room=self.room, sender=self.alice, receiver=self.bot,
            event_type='member_added',
        )
        self.assertEqual(self._bot_replies().count(), before)

    def test_engine_silent_on_promoted_group(self):
        # Manually mark the room as a group (simulating post-escalation) and
        # verify the engine no longer responds to user messages there.
        self.room.is_group = True
        self.room.save(update_fields=['is_group'])
        before = self._bot_replies().count()
        Message.objects.create(
            chat_room=self.room, sender=self.alice, receiver=None,
            content='still here?',
        )
        self.assertEqual(self._bot_replies().count(), before)

    # ---------- Welcome ----------

    def test_room_creation_posts_welcome_card(self):
        # alice's room (created in setUp) should already have a welcome message.
        welcome = (
            self._bot_replies()
            .filter(content__startswith="Hi! I'm your onboarding assistant")
            .first()
        )
        self.assertIsNotNone(welcome)
        self.assertEqual(welcome.bot_payload['kind'], 'card')
        labels = [b['label'] for b in welcome.bot_payload['buttons']]
        self.assertEqual(labels, [
            'Get started with onboarding',
            "I'm confused",
            'tehehe',
            'Call in the admin',
        ])
