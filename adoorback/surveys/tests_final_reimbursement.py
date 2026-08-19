import importlib

from django.test import SimpleTestCase

from surveys import reimbursement_config
from surveys.final_reimbursement import (
    InviteeRecord, best_boss_quiz_score, friend_invite_outcome,
    interview_points_for_email, wit_bot_outcome, wit_bot_points_for_score,
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
