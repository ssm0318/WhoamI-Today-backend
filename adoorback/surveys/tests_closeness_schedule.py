from datetime import date
from importlib import import_module
from unittest.mock import patch

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from surveys.models import CADENCE_BIWEEKLY, ScheduledSurvey, Survey
from surveys.scheduling import get_survey_index


class ClosenessScheduleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create(username='alice', email='alice@example.com')
        Survey.objects.create(
            slug='phase1_friend_closeness',
            title_en='Phase 1 friend closeness',
            title_ko='',
        )
        Survey.objects.create(
            slug='phase2_friend_closeness',
            title_en='Phase 2 friend closeness',
            title_ko='',
        )

    def test_phase1_friend_closeness_is_due_may_18_and_late_afterward(self):
        seed_module = import_module('surveys.migrations.0021_seed_closeness_schedule')
        seed_module.seed_closeness(django_apps, None)

        phase1 = ScheduledSurvey.objects.get(
            cadence=CADENCE_BIWEEKLY,
            sequence_index=6,
            survey__slug='phase1_friend_closeness',
        )
        self.assertEqual(phase1.window_start, date(2026, 5, 18))
        self.assertEqual(phase1.window_end, date(2026, 5, 18))
        self.assertTrue(phase1.allow_late)

        with patch('surveys.scheduling._today_la_7am', return_value=date(2026, 5, 18)):
            due_today = get_survey_index(self.user)
        self.assertIn(phase1, due_today['available_now'])
        self.assertNotIn(phase1, due_today['late_but_accepted'])

        with patch('surveys.scheduling._today_la_7am', return_value=date(2026, 5, 19)):
            late_after_due_date = get_survey_index(self.user)
        self.assertNotIn(phase1, late_after_due_date['available_now'])
        self.assertIn(phase1, late_after_due_date['late_but_accepted'])
