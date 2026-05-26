import datetime

from rest_framework import status
from rest_framework.test import APITestCase

from surveys._test_helpers import make_likert_survey, make_user, respond
from surveys.models import CADENCE_DAILY, PointAward, ScheduledSurvey


class PastSurveysViewTests(APITestCase):
    """Today on WIT archive — only surfaces answered daily_base rows."""

    def _schedule(self, survey, schedule_date, sequence_index, *, allow_late=False):
        return ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_DAILY,
            window_start=schedule_date,
            window_end=schedule_date,
            allow_late=allow_late,
            sequence_index=sequence_index,
        )

    def _award(self, user, survey, scheduled, values):
        response = respond(user, survey, values)
        PointAward.objects.create(
            user=user,
            source_kind=PointAward.SOURCE_SURVEY,
            source_slug=survey.slug,
            scheduled_survey=scheduled,
            response=response,
            awarded_points=1,
        )
        return response

    def test_returns_only_answered_dailies_descending(self):
        viewer = make_user('viewer')
        daily = make_likert_survey('daily_base')
        sotd = make_likert_survey('organized_default_mode')
        older = self._schedule(daily, datetime.date.today() - datetime.timedelta(days=2), 1)
        newer = self._schedule(daily, datetime.date.today() - datetime.timedelta(days=1), 2)
        other_daily = self._schedule(sotd, datetime.date.today() - datetime.timedelta(days=1), 3)
        self._award(viewer, daily, older, [3, 3])
        self._award(viewer, daily, newer, [4, 4])
        self._award(viewer, sotd, other_daily, [5, 5])

        self.client.force_authenticate(user=viewer)
        r = self.client.get('/api/surveys/past/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        results = r.json()['results']
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['survey']['slug'], daily.slug)  # most recent first
        self.assertEqual(results[0]['date'], newer.window_start.isoformat())
        self.assertEqual(results[1]['survey']['slug'], daily.slug)
        self.assertEqual(results[1]['date'], older.window_start.isoformat())

    def test_user_answered_and_unlocked_flags(self):
        viewer = make_user('viewer')
        daily = make_likert_survey('daily_base')
        old = self._schedule(daily, datetime.date.today() - datetime.timedelta(days=2), 1)
        today = self._schedule(daily, datetime.date.today(), 2)
        self._award(viewer, daily, old, [3, 3])
        self._award(viewer, daily, today, [4, 2])

        self.client.force_authenticate(user=viewer)
        r = self.client.get('/api/surveys/past/')
        results = r.json()['results']
        rows = {row['date']: row for row in results}
        self.assertTrue(rows[old.window_start.isoformat()]['user_answered'])
        self.assertTrue(rows[old.window_start.isoformat()]['results_unlocked'])
        self.assertTrue(rows[today.window_start.isoformat()]['user_answered'])
        self.assertFalse(rows[today.window_start.isoformat()]['results_unlocked'])

    def test_unanswered_past_dailies_hidden(self):
        """Past daily_base rows the user didn't answer don't show up."""
        viewer = make_user('viewer')
        daily = make_likert_survey('daily_base')
        self._schedule(
            daily,
            datetime.date.today() - datetime.timedelta(days=1),
            1,
            allow_late=True,
        )

        self.client.force_authenticate(user=viewer)
        r = self.client.get('/api/surveys/past/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()['results'], [])

    def test_future_dailies_hidden(self):
        """Future-scheduled dailies aren't exposed in advance, even if other
        users somehow answered them already."""
        viewer = make_user('viewer')
        daily = make_likert_survey('daily_base')
        future = self._schedule(
            daily,
            datetime.date.today() + datetime.timedelta(days=3),
            1,
        )
        self._award(viewer, daily, future, [4, 4])

        self.client.force_authenticate(user=viewer)
        r = self.client.get('/api/surveys/past/')
        self.assertEqual(r.json()['results'], [])

    def test_repeated_daily_base_rows_are_not_all_marked_answered_by_one_response(self):
        viewer = make_user('viewer')
        daily = make_likert_survey('daily_base')
        answered = self._schedule(daily, datetime.date.today() - datetime.timedelta(days=2), 1)
        unanswered = self._schedule(daily, datetime.date.today() - datetime.timedelta(days=1), 2)
        self._award(viewer, daily, answered, [3, 3])

        self.client.force_authenticate(user=viewer)
        r = self.client.get('/api/surveys/past/')
        results = r.json()['results']
        self.assertEqual([row['date'] for row in results], [answered.window_start.isoformat()])
        self.assertNotIn(unanswered.window_start.isoformat(), [row['date'] for row in results])
