from django.contrib.auth import get_user_model
from django.test import TestCase

from chat.models import ChatRoom, Message
from chat import wit_bot_state as state_mod

User = get_user_model()


class EngineDispatchTests(TestCase):
    def setUp(self):
        # Operators (so the wit_admin auto-provision succeeds) + alice.
        User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(
            username='alice', email='a@e.com', password='x',
        )
        self.alice.current_ver = 'version_w'
        self.alice.save(update_fields=['current_ver'])

        from chat.wit_bot import ensure_wit_bot_user
        self.bot = ensure_wit_bot_user()
        from django.db.models import Q
        self.room = ChatRoom.objects.get(
            (Q(user1=self.alice) & Q(user2=self.bot))
            | (Q(user1=self.bot) & Q(user2=self.alice))
        )

    def _send_choice(self, payload):
        return Message.objects.create(
            chat_room=self.room, sender=self.alice, receiver=self.bot,
            content=payload, bot_payload={'kind': 'choice', 'payload': payload},
        )

    def _send_text(self, text):
        return Message.objects.create(
            chat_room=self.room, sender=self.alice, receiver=self.bot,
            content=text,
        )

    def _bot_replies(self):
        return Message.objects.filter(chat_room=self.room, sender=self.bot)

    def test_admin_choice_still_escalates(self):
        before = self._bot_replies().count()
        self._send_choice('admin')
        self.assertGreater(self._bot_replies().count(), before)
        self.room.refresh_from_db()
        self.assertTrue(self.room.is_group)

    def test_start_onboarding_enters_kickoff_welcome(self):
        before = self._bot_replies().count()
        self._send_choice('start_onboarding')
        state = state_mod.get_or_create_state(self.alice)
        self.assertEqual(state.current_intent, 'kickoff_welcome')
        self.assertGreater(self._bot_replies().count(), before)

    def test_unknown_text_idle_response(self):
        before = self._bot_replies().count()
        self._send_text('huh')
        self.assertGreater(self._bot_replies().count(), before)
