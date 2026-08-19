import importlib
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.test import SimpleTestCase

from surveys import reimbursement_config
from surveys.app_usage import app_usage_metrics_for_user
from surveys.final_reimbursement import (
    FinalAwardSpec, InviteeRecord, best_boss_quiz_score,
    build_final_award_specs, friend_invite_outcome,
    interview_points_for_email, reconcile_user_awards,
    validate_interview_accounts, wit_bot_outcome, wit_bot_points_for_score,
)
from surveys.models import PointAward


class FinalReimbursementConfigTests(SimpleTestCase):
    def test_final_source_values(self):
        expected_constants = {
            'WIT_BOT_AUDIT_PARTIAL_POINTS': 10,
            'INTERVIEW_COMPLETED_POINTS': 100,
            'INTERVIEW_REBECCA_POINTS': 125,
            'FRIEND_INVITE_POINTS_PER_FRIEND': 100,
            'FRIEND_INVITE_MAX_POINTS': 500,
            'INTERVIEW_SIGNUP_URL': 'https://calendly.com/jaewonkim/60min',
        }

        self.assertEqual(
            getattr(PointAward, 'SOURCE_FRIEND_INVITE', None),
            'friend_invite',
        )
        for name, expected in expected_constants.items():
            self.assertEqual(getattr(reimbursement_config, name, None), expected)
        self.assertEqual(reimbursement_config.WIT_BOT_AUDIT_PHASES[1]['max_points'], 50)
        self.assertEqual(reimbursement_config.WIT_BOT_AUDIT_PHASES[2]['max_points'], 50)


class FinalReimbursementScoringInterfaceTests(SimpleTestCase):
    def test_scoring_module_exposes_final_source_interfaces(self):
        try:
            scoring = importlib.import_module('surveys.final_reimbursement')
        except ModuleNotFoundError:
            scoring = None

        self.assertIsNotNone(scoring)
        for name in (
            'WitBotOutcome',
            'InviteeRecord',
            'FriendInviteOutcome',
            'best_boss_quiz_score',
            'wit_bot_points_for_score',
            'wit_bot_outcome',
            'friend_invite_outcome',
            'interview_points_for_email',
            'FinalAwardSpec',
            'ReconciliationResult',
            'build_final_award_specs',
            'reconcile_user_awards',
        ):
            self.assertTrue(hasattr(scoring, name), name)


class WitBotFinalScoringTests(SimpleTestCase):
    def test_best_score_uses_attempt_history_and_final_score(self):
        progress = {
            'attempts_history': [
                {'score': 0.7},
                {'score': 0.9},
                {'score': 'not-a-number'},
            ],
            'final_score': 0.8,
        }

        self.assertEqual(best_boss_quiz_score(progress), 0.9)

    def test_thresholds_are_strict(self):
        cases = [
            (None, 0),
            (0.60, 0),
            (0.6001, 10),
            (0.85, 10),
            (0.8501, 50),
        ]

        self.assertEqual(
            [wit_bot_points_for_score(score) for score, _ in cases],
            [expected for _, expected in cases],
        )

    def test_phase_maps_to_crossover_version_and_records_audit_details(self):
        context = {
            'version_q': {
                'final_quiz': {'attempts_history': [{'score': 0.8}]},
                'audit': {'last_engaged_count': 9, 'last_missing_count': 1},
            },
        }

        outcome = wit_bot_outcome(context, 'group_q_first', phase=1)

        self.assertEqual(outcome.version, 'version_q')
        self.assertEqual(outcome.best_score, 0.8)
        self.assertEqual(outcome.points, 10)
        self.assertIn('engaged=9', outcome.note)
        self.assertIn('missing=1', outcome.note)


class ManualSourceScoringTests(SimpleTestCase):
    def test_invites_ignore_staff_and_cap_at_five(self):
        invitees = [InviteeRecord(i, f'user{i}', False) for i in range(1, 7)]
        invitees.append(InviteeRecord(99, 'staff', True))

        outcome = friend_invite_outcome(invitees)

        self.assertEqual(outcome.eligible_count, 6)
        self.assertEqual(outcome.credited_count, 5)
        self.assertEqual(outcome.points, 500)
        self.assertIn('1:user1', outcome.note)
        self.assertIn('6:user6', outcome.note)
        self.assertNotIn('staff', outcome.note)

    def test_interview_email_matching_and_rebecca_exception(self):
        self.assertEqual(interview_points_for_email(' JENNYLNINH@GMAIL.COM '), 100)
        self.assertEqual(interview_points_for_email('rebecca.laba@gmail.com'), 125)
        self.assertEqual(interview_points_for_email('nasiu21321@gmail.com'), 0)


class DatabaseAwareAppUsageTests(TestCase):
    @patch('surveys.app_usage._events_for_user')
    def test_metrics_passes_the_selected_database_to_event_queries(self, events_for_user):
        user = get_user_model().objects.create(
            username='restore_reader',
            email='restore_reader@example.com',
        )
        events_for_user.return_value = [
            (datetime(2026, 5, 4, 12, tzinfo=timezone.utc), 'note'),
            (datetime(2026, 5, 5, 12, tzinfo=timezone.utc), 'comment'),
        ]

        app_usage_metrics_for_user(user, 1, using='phase1_restore')

        events_for_user.assert_called_once_with(user, 1, using='phase1_restore')


class FinalLedgerReconciliationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(
            username='participant',
            email='participant@example.com',
            user_group='group_q_first',
        )

    @patch('surveys.app_usage.app_usage_metrics_for_user')
    def test_build_specs_returns_every_final_non_survey_source(self, app_metrics):
        app_metrics.side_effect = [
            type('Metrics', (), {'points': 20, 'active_days': 2, 'first_four_days': 2,
                                 'later_days': 0, 'core_event_count': 2})(),
            type('Metrics', (), {'points': 0, 'active_days': 0, 'first_four_days': 0,
                                 'later_days': 0, 'core_event_count': 0})(),
        ]
        get_user_model().objects.create(
            username='invitee',
            email='invitee@example.com',
            invited_from=self.user,
        )

        specs = build_final_award_specs(
            self.user,
            phase1_database='phase1_restore',
            phase2_database='default',
        )

        keys = {(spec.source_kind, spec.source_slug) for spec in specs}
        self.assertEqual(keys, {
            ('app_usage', 'app_usage_phase_1'),
            ('app_usage', 'app_usage_phase_2'),
            ('wit_bot_audit', 'wit_bot_audit_phase_1'),
            ('wit_bot_audit', 'wit_bot_audit_phase_2'),
            ('friend_invite', 'friend_invite'),
        })
        friend_spec = next(spec for spec in specs if spec.source_kind == 'friend_invite')
        self.assertEqual(friend_spec.awarded_points, 100)
        app_metrics.assert_any_call(self.user, 1, using='phase1_restore')
        app_metrics.assert_any_call(self.user, 2, using='default')

    def test_dry_run_writes_nothing_and_apply_is_idempotent(self):
        specs = [
            FinalAwardSpec(
                'friend_invite',
                'friend_invite',
                100,
                None,
                'Eligible invites=1.',
            ),
        ]

        dry = reconcile_user_awards(self.user, specs, apply=False)

        self.assertEqual(dry.created, 1)
        self.assertFalse(PointAward.objects.filter(user=self.user).exists())

        reconcile_user_awards(self.user, specs, apply=True)
        second = reconcile_user_awards(self.user, specs, apply=True)

        self.assertEqual(second.unchanged, 1)
        self.assertEqual(
            PointAward.objects.filter(
                user=self.user,
                source_kind='friend_invite',
                source_slug='friend_invite',
            ).count(),
            1,
        )

    def test_existing_survey_adjustments_are_never_overwritten(self):
        award = PointAward.objects.create(
            user=self.user,
            source_kind='survey',
            source_slug='post_study_q',
            awarded_points=50,
            adjusted_points=0,
            note='Good-faith survey audit exclusion.',
        )

        reconcile_user_awards(self.user, [], apply=True)

        award.refresh_from_db()
        self.assertEqual(award.adjusted_points, 0)
        self.assertEqual(award.note, 'Good-faith survey audit exclusion.')


class FinalReimbursementCommandTests(TestCase):
    def _create_interview_accounts(self):
        emails = sorted({
            'jennylninh@gmail.com',
            'siddhub2001@gmail.com',
            'yixin7@uw.edu',
            'rebecca.laba@gmail.com',
            'pinkchloeko@gmail.com',
            'ole2@uw.edu',
            'sai.yakumo770@gmail.com',
            'superlegos113@gmail.com',
            'anh.n.personal@gmail.com',
            'sklein3@uw.edu',
            'aishani.rao22@gmail.com',
        })
        return [
            get_user_model().objects.create(
                id=index,
                username=f'participant_{index}',
                email=email,
                user_group='group_q_first',
            )
            for index, email in enumerate(emails, start=8)
        ]

    def test_interview_validation_rejects_a_missing_approved_email(self):
        accounts = self._create_interview_accounts()

        with self.assertRaisesMessage(ValueError, 'yixin7@uw.edu'):
            validate_interview_accounts([
                account for account in accounts
                if account.email != 'yixin7@uw.edu'
            ])

    @patch('surveys.management.commands.finalize_reimbursement.build_final_award_specs')
    def test_command_is_dry_run_by_default_and_apply_is_explicit(self, build_specs):
        accounts = self._create_interview_accounts()
        build_specs.return_value = [FinalAwardSpec(
            'friend_invite', 'friend_invite', 100, None, 'Final invitation total.',
        )]
        output = StringIO()

        call_command(
            'finalize_reimbursement',
            phase1_database='default',
            stdout=output,
        )

        self.assertIn('DRY RUN', output.getvalue())
        self.assertEqual(PointAward.objects.count(), 0)

        call_command(
            'finalize_reimbursement',
            '--apply',
            phase1_database='default',
            stdout=StringIO(),
        )

        self.assertEqual(PointAward.objects.count(), len(accounts))

    @patch('surveys.management.commands.finalize_reimbursement.validate_interview_accounts')
    def test_command_converts_validation_failure_to_command_error(self, validate):
        get_user_model().objects.create(
            id=8,
            username='participant',
            email='participant@example.com',
            user_group='group_q_first',
        )
        validate.side_effect = ValueError('Interview account mismatch.')

        with self.assertRaisesMessage(CommandError, 'Interview account mismatch'):
            call_command(
                'finalize_reimbursement',
                phase1_database='default',
                stdout=StringIO(),
            )
