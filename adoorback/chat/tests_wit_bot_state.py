from django.contrib.auth import get_user_model
from django.test import TestCase

from chat.models import WitBotConversationState
from chat import wit_bot_state as s

User = get_user_model()


class StateHelperTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            username='alice', email='a@e.com', password='x',
        )
        self.alice.current_ver = 'version_w'
        self.alice.save(update_fields=['current_ver'])

    def test_get_or_create_state_returns_state(self):
        state = s.get_or_create_state(self.alice)
        self.assertIsInstance(state, WitBotConversationState)
        self.assertEqual(state.user, self.alice)
        self.assertEqual(state.current_intent, '')

    def test_set_intent_persists(self):
        state = s.get_or_create_state(self.alice)
        s.set_intent(state, 'kickoff_welcome', step=0)
        state.refresh_from_db()
        self.assertEqual(state.current_intent, 'kickoff_welcome')
        self.assertEqual(state.step, 0)

    def test_progress_for_version_default(self):
        state = s.get_or_create_state(self.alice)
        prog = s.progress_for(state, 'version_w')
        self.assertEqual(prog, {})

    def test_set_progress_persists(self):
        state = s.get_or_create_state(self.alice)
        s.set_progress(state, 'version_w', 'kickoff', {'welcomed': True})
        state.refresh_from_db()
        self.assertEqual(
            state.context['version_w']['kickoff'],
            {'welcomed': True},
        )

    def test_set_progress_merges(self):
        state = s.get_or_create_state(self.alice)
        s.set_progress(state, 'version_w', 'kickoff', {'welcomed': True})
        s.set_progress(state, 'version_w', 'kickoff', {'quiz_1_passed': True})
        state.refresh_from_db()
        self.assertEqual(
            state.context['version_w']['kickoff'],
            {'welcomed': True, 'quiz_1_passed': True},
        )
