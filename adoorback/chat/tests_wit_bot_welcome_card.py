from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from chat import wit_bot_state as state_mod
from chat import wit_bot_welcome_card as wc

User = get_user_model()


class WelcomeCardTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            username='alice', email='a@e.com', password='x',
        )
        self.alice.current_ver = 'version_w'
        self.alice.save(update_fields=['current_ver'])

    def _set_now(self, year, month, day):
        return timezone.make_aware(datetime(year, month, day, 12, 0))

    def test_pre_window_shows_no_button(self):
        payload = wc.build_welcome_card(self.alice, now=self._set_now(2026, 5, 3))
        self.assertEqual(payload['kind'], 'card')
        self.assertEqual(payload.get('buttons', []), [])
        self.assertIn('see you', payload['intro'].lower())

    def test_window_open_shows_start_button(self):
        payload = wc.build_welcome_card(self.alice, now=self._set_now(2026, 5, 4))
        labels = [b['label'] for b in payload['buttons']]
        self.assertIn('Start onboarding', labels)

    def test_kickoff_in_progress_shows_resume(self):
        state = state_mod.get_or_create_state(self.alice)
        state_mod.set_intent(state, 'kickoff_quiz_2', step=0)
        payload = wc.build_welcome_card(self.alice, now=self._set_now(2026, 5, 4))
        labels = [b['label'] for b in payload['buttons']]
        self.assertIn('Resume onboarding', labels)

    def test_kickoff_complete_shows_run_audit_button(self):
        """After kickoff but no audit run (or audit not 100%), Run audit button shows."""
        state = state_mod.get_or_create_state(self.alice)
        state_mod.set_progress(state, 'version_w', 'kickoff', {'completed': True})
        payload = wc.build_welcome_card(self.alice, now=self._set_now(2026, 5, 5))
        labels = [b['label'] for b in payload['buttons']]
        self.assertIn('Run audit', labels)

    def test_audit_complete_shows_take_boss_quiz_cta(self):
        """After audit confirms 0 missing but boss quiz not yet passed, show Take boss quiz."""
        state = state_mod.get_or_create_state(self.alice)
        state_mod.set_progress(state, 'version_w', 'kickoff', {'completed': True})
        state_mod.set_progress(state, 'version_w', 'audit', {'last_missing_count': 0})
        payload = wc.build_welcome_card(self.alice, now=self._set_now(2026, 5, 5))
        labels = [b['label'] for b in payload['buttons']]
        self.assertIn('Take the boss quiz', labels)

    def test_boss_quiz_passed_shows_no_button_pre_swap(self):
        """After boss quiz passes, no button — silent until May 18."""
        state = state_mod.get_or_create_state(self.alice)
        state_mod.set_progress(state, 'version_w', 'kickoff', {'completed': True})
        state_mod.set_progress(state, 'version_w', 'audit', {'last_missing_count': 0})
        state_mod.set_progress(state, 'version_w', 'final_quiz', {'passed': True})
        payload = wc.build_welcome_card(self.alice, now=self._set_now(2026, 5, 5))
        self.assertEqual(payload.get('buttons', []), [])
        self.assertIn('May 18', payload['intro'])
