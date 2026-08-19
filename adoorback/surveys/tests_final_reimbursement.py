from django.test import SimpleTestCase

from surveys import reimbursement_config
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
