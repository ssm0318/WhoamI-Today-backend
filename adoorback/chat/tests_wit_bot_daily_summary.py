from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from chat.management.commands.wit_bot_daily_summary import build_report, render_report
from chat.models import ChatRoom, Message, OnboardingScreenshot, WitBotConversationState

User = get_user_model()


class DailySummaryTests(TestCase):
    def setUp(self):
        # Operators
        for u, e in (
            ('jaewon', 'jaewonkim628@gmail.com'),
            ('koyrkr', 'koyrkr@gmail.com'),
            ('njs', 'njs03332@gmail.com'),
        ):
            User.objects.create_user(username=u, email=e, password='x')

        # Three participants
        self.alice = User.objects.create_user(
            username='alice', email='a@e.com', password='x',
        )
        self.alice.current_ver = 'version_w'
        self.alice.save(update_fields=['current_ver'])

        self.bob = User.objects.create_user(
            username='bob', email='b@e.com', password='x',
        )
        self.bob.current_ver = 'version_w'
        self.bob.save(update_fields=['current_ver'])

        self.carol = User.objects.create_user(
            username='carol', email='c@e.com', password='x',
        )
        self.carol.current_ver = 'version_q'
        self.carol.save(update_fields=['current_ver'])

    def test_empty_state_renders(self):
        report = build_report(stale_hours=24)
        self.assertEqual(report['totals']['participants'], 3)
        self.assertEqual(report['totals']['kickoff_started'], 0)
        self.assertEqual(report['pending_screenshots']['total'], 0)
        text = render_report(report)
        self.assertIn('Participants:               3', text)
        self.assertIn('No stale pending screenshots', text)

    def _set_state(self, user, current_intent='', context=None):
        """Helper that handles the auto-created WitBotConversationState from signals."""
        state, _ = WitBotConversationState.objects.update_or_create(
            user=user,
            defaults={
                'current_intent': current_intent,
                'context': context or {},
            },
        )
        return state

    def _wit_bot_room_for(self, user):
        from chat.wit_bot import ensure_wit_bot_user
        from django.db.models import Q as _Q
        bot = ensure_wit_bot_user()
        return ChatRoom.objects.get(
            (_Q(user1=user) & _Q(user2=bot))
            | (_Q(user1=bot) & _Q(user2=user))
        )

    def test_kickoff_started_counted(self):
        self._set_state(
            self.alice,
            current_intent='kickoff_quiz_2',
            context={'version_w': {'kickoff': {'quiz_1': {'score': 0.9}}}},
        )
        report = build_report()
        self.assertEqual(report['totals']['kickoff_started'], 1)
        self.assertEqual(report['totals']['kickoff_complete'], 0)

    def test_kickoff_complete_counted(self):
        self._set_state(
            self.bob,
            context={'version_w': {'kickoff': {'completed': True}}},
        )
        report = build_report()
        self.assertEqual(report['totals']['kickoff_complete'], 1)

    def test_pending_screenshot_listed(self):
        room = self._wit_bot_room_for(self.alice)
        msg = Message.objects.create(
            chat_room=room, sender=self.alice, receiver=room.user2,
            content='widget upload',
        )
        OnboardingScreenshot.objects.create(
            user=self.alice, version='version_w', kind='widget', message=msg,
        )
        report = build_report()
        self.assertEqual(report['pending_screenshots']['total'], 1)

    def test_stale_pending_screenshot(self):
        room = self._wit_bot_room_for(self.alice)
        msg = Message.objects.create(
            chat_room=room, sender=self.alice, receiver=room.user2,
            content='widget upload',
        )
        shot = OnboardingScreenshot.objects.create(
            user=self.alice, version='version_w', kind='widget', message=msg,
        )
        OnboardingScreenshot.objects.filter(id=shot.id).update(
            created_at=timezone.now() - timedelta(hours=48),
        )
        report = build_report(stale_hours=24)
        self.assertEqual(len(report['pending_screenshots']['stale']), 1)
        text = render_report(report)
        self.assertIn('alice', text)

    def test_dry_run_writes_to_stdout(self):
        out = StringIO()
        mail.outbox = []
        call_command('wit_bot_daily_summary', '--dry-run', stdout=out)
        self.assertIn('WITty daily summary', out.getvalue())
        self.assertEqual(len(mail.outbox), 0)

    def test_email_sent_to_operators(self):
        mail.outbox = []
        call_command('wit_bot_daily_summary')
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertIn('WITty daily summary', m.subject)
        self.assertIn('jaewonkim628@gmail.com', m.recipients())

    def test_to_override(self):
        mail.outbox = []
        call_command('wit_bot_daily_summary', '--to=test@example.com')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].recipients(), ['test@example.com'])

    def test_excludes_operators_from_participant_count(self):
        report = build_report()
        # Setup created 3 operators + 3 participants. Participant count should be 3.
        self.assertEqual(report['totals']['participants'], 3)
