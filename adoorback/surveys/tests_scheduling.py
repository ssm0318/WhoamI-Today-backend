import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from surveys.models import (
    CADENCE_ANYTIME, CADENCE_BIWEEKLY, CADENCE_DAILY, CADENCE_ENDPOINT,
    CADENCE_WEEKLY, ScheduledSurvey, Survey, SurveyResponse,
)
from surveys.scheduling import get_survey_index, get_today_daily


class SchedulingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create(username='alice', email='a@x.com')
        self.today = datetime.date.today()
        self.yesterday = self.today - datetime.timedelta(days=1)
        self.tomorrow = self.today + datetime.timedelta(days=1)

    def _survey(self, slug, *, priority=0):
        return Survey.objects.create(slug=slug, title_en='T', title_ko='T', priority=priority)

    # get_today_daily ------------------------------------------------------

    def test_today_daily_returns_today_unanswered(self):
        s = self._survey('daily_base')
        ScheduledSurvey.objects.create(
            survey=s, cadence=CADENCE_DAILY,
            window_start=self.today, window_end=self.today,
            allow_late=False, sequence_index=1,
        )
        result = get_today_daily(self.user)
        self.assertIsNotNone(result)
        self.assertEqual(result.survey, s)

    def test_today_daily_returns_survey_even_when_answered(self):
        """Card stays after answering so the user can see Done / View results."""
        s = self._survey('daily_base')
        ScheduledSurvey.objects.create(
            survey=s, cadence=CADENCE_DAILY,
            window_start=self.today, window_end=self.today,
            allow_late=False, sequence_index=1,
        )
        SurveyResponse.objects.create(user=self.user, survey=s)
        result = get_today_daily(self.user)
        self.assertIsNotNone(result)
        self.assertEqual(result.survey, s)
        self.assertTrue(result.user_answered)

    def test_today_daily_returns_none_when_not_today(self):
        s = self._survey('daily_base')
        ScheduledSurvey.objects.create(
            survey=s, cadence=CADENCE_DAILY,
            window_start=self.yesterday, window_end=self.yesterday,
            allow_late=False, sequence_index=1,
        )
        self.assertIsNone(get_today_daily(self.user))

    # get_survey_index buckets --------------------------------------------

    def test_index_buckets_available_correctly(self):
        s = self._survey('week1_reflection')
        ScheduledSurvey.objects.create(
            survey=s, cadence=CADENCE_WEEKLY,
            window_start=self.today, window_end=self.today + datetime.timedelta(days=3),
            allow_late=True, sequence_index=1,
        )
        result = get_survey_index(self.user)
        self.assertEqual(len(result['available_now']), 1)
        self.assertEqual(result['available_now'][0].survey, s)
        self.assertEqual(result['late_but_accepted'], [])
        self.assertEqual(result['completed'], [])

    def test_index_buckets_late_correctly(self):
        s = self._survey('mid_study')
        ScheduledSurvey.objects.create(
            survey=s, cadence=CADENCE_BIWEEKLY,
            window_start=self.yesterday, window_end=self.yesterday,
            allow_late=True, sequence_index=1,
        )
        result = get_survey_index(self.user)
        self.assertEqual(len(result['late_but_accepted']), 1)
        self.assertEqual(result['late_but_accepted'][0].survey, s)
        self.assertEqual(result['available_now'], [])
        self.assertEqual(result['completed'], [])

    def test_index_excludes_expired_daily(self):
        """Expired-and-hidden bucket: missed daily, allow_late=False → in no bucket."""
        s = self._survey('daily_base')
        ScheduledSurvey.objects.create(
            survey=s, cadence=CADENCE_DAILY,
            window_start=self.yesterday, window_end=self.yesterday,
            allow_late=False, sequence_index=1,
        )
        result = get_survey_index(self.user)
        self.assertEqual(result['available_now'], [])
        self.assertEqual(result['late_but_accepted'], [])
        self.assertEqual(result['completed'], [])

    def test_late_weekday_sotd_remains_visible_on_weekend(self):
        s = self._survey('sotd_d26_transition')
        friday = datetime.date(2026, 5, 29)
        sunday = datetime.date(2026, 5, 31)
        ScheduledSurvey.objects.create(
            survey=s, cadence=CADENCE_DAILY,
            window_start=friday, window_end=friday,
            allow_late=True, sequence_index=126,
        )

        with patch('surveys.scheduling._today_la_7am', return_value=sunday):
            result = get_survey_index(self.user)

        self.assertEqual(result['available_now'], [])
        self.assertEqual([row.survey.slug for row in result['late_but_accepted']], [s.slug])
        self.assertEqual(result['completed'], [])

    def test_index_buckets_completed(self):
        s = self._survey('week1_reflection')
        ScheduledSurvey.objects.create(
            survey=s, cadence=CADENCE_WEEKLY,
            window_start=self.yesterday, window_end=self.today,
            allow_late=True, sequence_index=1,
        )
        SurveyResponse.objects.create(user=self.user, survey=s)
        result = get_survey_index(self.user)
        self.assertEqual(len(result['completed']), 1)
        self.assertEqual(result['completed'][0].survey, s)
        self.assertEqual(result['available_now'], [])
        self.assertEqual(result['late_but_accepted'], [])

    def test_index_handles_open_ended_window_end(self):
        """Anytime: window_end=None, started in past, not answered → available_now."""
        s = self._survey('anytime_reflection')
        ScheduledSurvey.objects.create(
            survey=s, cadence=CADENCE_ANYTIME,
            window_start=self.today - datetime.timedelta(days=5), window_end=None,
            allow_late=True, sequence_index=1,
        )
        result = get_survey_index(self.user)
        self.assertEqual(len(result['available_now']), 1)
        self.assertEqual(result['available_now'][0].survey, s)

    def test_index_endpoint_before_open(self):
        """Endpoint scheduled in the future is hidden."""
        s = self._survey('study_endpoint')
        ScheduledSurvey.objects.create(
            survey=s, cadence=CADENCE_ENDPOINT,
            window_start=self.tomorrow, window_end=None,
            allow_late=True, sequence_index=1,
        )
        result = get_survey_index(self.user)
        self.assertEqual(result['available_now'], [])
        self.assertEqual(result['late_but_accepted'], [])
        self.assertEqual(result['completed'], [])

    def test_index_endpoint_after_open(self):
        """Endpoint open-ended after its open date stays in available_now."""
        s = self._survey('study_endpoint')
        ScheduledSurvey.objects.create(
            survey=s, cadence=CADENCE_ENDPOINT,
            window_start=self.yesterday, window_end=None,
            allow_late=True, sequence_index=1,
        )
        result = get_survey_index(self.user)
        self.assertEqual(len(result['available_now']), 1)
        self.assertEqual(result['available_now'][0].survey, s)

    def test_index_user_submitted_at_annotated(self):
        """Completed entries carry the user's submitted_at on the queryset annotation."""
        s = self._survey('week1_reflection')
        ScheduledSurvey.objects.create(
            survey=s, cadence=CADENCE_WEEKLY,
            window_start=self.yesterday, window_end=self.today,
            allow_late=True, sequence_index=1,
        )
        response = SurveyResponse.objects.create(user=self.user, survey=s)
        result = get_survey_index(self.user)
        self.assertEqual(len(result['completed']), 1)
        self.assertEqual(result['completed'][0].user_submitted_at, response.submitted_at)

    def test_sidebar_order_overrides_priority_with_priority_fallback(self):
        high = self._survey('high_priority_unordered', priority=200)
        second = self._survey('explicit_second', priority=10)
        first = self._survey('explicit_first', priority=50)

        ScheduledSurvey.objects.create(
            survey=high, cadence=CADENCE_WEEKLY,
            window_start=self.today, window_end=self.today,
            allow_late=True, sequence_index=201,
        )
        ScheduledSurvey.objects.create(
            survey=second, cadence=CADENCE_WEEKLY,
            window_start=self.today, window_end=self.today,
            allow_late=True, sequence_index=202, sidebar_order=2,
        )
        ScheduledSurvey.objects.create(
            survey=first, cadence=CADENCE_WEEKLY,
            window_start=self.today, window_end=self.today,
            allow_late=True, sequence_index=203, sidebar_order=1,
        )

        result = get_survey_index(self.user)
        self.assertEqual(
            [row.survey.slug for row in result['available_now']],
            ['explicit_first', 'explicit_second', 'high_priority_unordered'],
        )
