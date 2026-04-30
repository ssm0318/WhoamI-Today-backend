from django.contrib.auth import get_user_model
from django.test import TestCase

from chat.models import ChatRoom, Message, WitBotConversationState

User = get_user_model()


class WitBotEngineTests(TestCase):
    def setUp(self):
        # Operators (so the wit_admin auto-provision succeeds) + alice.
        User.objects.create_user(username='jaewon', email='jaewonkim628@gmail.com', password='x')
        User.objects.create_user(username='koyrkr', email='koyrkr@gmail.com', password='x')
        User.objects.create_user(username='njs', email='njs03332@gmail.com', password='x')
        self.alice = User.objects.create_user(username='alice', email='a@e.com', password='x')
        from chat.wit_bot import ensure_wit_bot_user, ensure_wit_bot_room
        self.bot = ensure_wit_bot_user()
        self.room = ensure_wit_bot_room(self.alice)

    def _send(self, content, sender=None):
        sender = sender or self.alice
        return Message.objects.create(
            chat_room=self.room, sender=sender, receiver=self.bot,
            content=content,
        )

    def _bot_replies(self):
        return Message.objects.filter(chat_room=self.room, sender=self.bot)

    def test_first_message_triggers_onboarding(self):
        from chat.wit_bot_engine import INTENT_ONBOARDING_START
        self._send('hi')
        state = WitBotConversationState.objects.get(user=self.alice)
        self.assertEqual(state.current_intent, INTENT_ONBOARDING_START)
        self.assertGreaterEqual(self._bot_replies().count(), 1)

    def test_talk_to_human_sets_awaiting_state(self):
        from chat.wit_bot_engine import INTENT_AWAITING_ESCALATION
        self._send('I want to talk to a real person')
        state = WitBotConversationState.objects.get(user=self.alice)
        self.assertEqual(state.current_intent, INTENT_AWAITING_ESCALATION)
        # Bot posted the confirmation prompt.
        last_reply = self._bot_replies().last()
        self.assertIn('yes', (last_reply.content or '').lower())

    def test_yes_after_awaiting_escalates(self):
        # Set state directly to focus on yes-handling.
        from chat.wit_bot_engine import INTENT_AWAITING_ESCALATION, INTENT_NONE
        WitBotConversationState.objects.create(
            user=self.alice, current_intent=INTENT_AWAITING_ESCALATION,
        )
        self._send('yes')
        # Room is now a group with wit_admin added.
        from chat.wit_admin import ensure_wit_admin_user
        admin = ensure_wit_admin_user()
        self.room.refresh_from_db()
        self.assertTrue(self.room.is_group)
        member_ids = set(self.room.members.values_list('id', flat=True))
        self.assertEqual(member_ids, {self.alice.id, self.bot.id, admin.id})
        state = WitBotConversationState.objects.get(user=self.alice)
        self.assertEqual(state.current_intent, INTENT_NONE)

    def test_no_after_awaiting_clears_state(self):
        from chat.wit_bot_engine import INTENT_AWAITING_ESCALATION, INTENT_NONE
        WitBotConversationState.objects.create(
            user=self.alice, current_intent=INTENT_AWAITING_ESCALATION,
        )
        self._send('no')
        self.room.refresh_from_db()
        self.assertFalse(self.room.is_group)
        state = WitBotConversationState.objects.get(user=self.alice)
        self.assertEqual(state.current_intent, INTENT_NONE)

    def test_loop_guard_skips_bot_self_messages(self):
        # A message sent BY the bot must not trigger a recursive bot reply.
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

    def test_unknown_falls_back_to_canned_reply(self):
        # Set state to bypass onboarding-on-first-message.
        from chat.wit_bot_engine import INTENT_NONE
        WitBotConversationState.objects.create(
            user=self.alice, current_intent=INTENT_NONE,
        )
        # Send a prior message so onboarding doesn't fire (need >1 user message).
        self._send('seed message')
        before = self._bot_replies().count()
        self._send('asdfqwer random gibberish')
        replies_after = self._bot_replies().count()
        self.assertGreater(replies_after, before)
        last = self._bot_replies().last()
        self.assertIn("bot", (last.content or '').lower())
