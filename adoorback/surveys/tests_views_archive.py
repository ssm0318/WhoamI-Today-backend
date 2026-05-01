import datetime

from rest_framework import status
from rest_framework.test import APITestCase

from surveys._test_helpers import make_likert_survey, make_user, respond


class PastSurveysViewTests(APITestCase):
    """Daily archive — only surfaces dailies the user answered, on-or-before
    today. Future dailies and past unanswered dailies are hidden."""

    def test_returns_only_answered_dailies_descending(self):
        viewer = make_user('viewer')
        s1 = make_likert_survey('s1', schedule_date=datetime.date.today() - datetime.timedelta(days=2))
        s2 = make_likert_survey('s2', schedule_date=datetime.date.today() - datetime.timedelta(days=1))
        respond(viewer, s1, [3, 3])
        respond(viewer, s2, [4, 4])
        self.client.force_authenticate(user=viewer)
        r = self.client.get('/api/surveys/past/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        results = r.json()['results']
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['survey']['slug'], s2.slug)  # most recent first
        self.assertEqual(results[1]['survey']['slug'], s1.slug)

    def test_user_answered_and_unlocked_flags(self):
        viewer = make_user('viewer')
        # s_old: user answered, day past → unlocked
        s_old = make_likert_survey('s_old', schedule_date=datetime.date.today() - datetime.timedelta(days=2))
        respond(viewer, s_old, [3, 3])
        # s_today: user answered, day is today → not unlocked yet
        s_today = make_likert_survey('s_today', schedule_date=datetime.date.today())
        respond(viewer, s_today, [4, 2])

        self.client.force_authenticate(user=viewer)
        r = self.client.get('/api/surveys/past/')
        results = r.json()['results']
        slugs = {row['survey']['slug']: row for row in results}
        self.assertTrue(slugs['s_old']['user_answered'])
        self.assertTrue(slugs['s_old']['results_unlocked'])
        self.assertTrue(slugs['s_today']['user_answered'])
        self.assertFalse(slugs['s_today']['results_unlocked'])

    def test_unanswered_past_dailies_hidden(self):
        """Past dailies the user didn't answer don't show up — they're
        un-submittable and have no results to view."""
        viewer = make_user('viewer')
        make_likert_survey('s_unans', schedule_date=datetime.date.today() - datetime.timedelta(days=1))
        self.client.force_authenticate(user=viewer)
        r = self.client.get('/api/surveys/past/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.json()['results'], [])

    def test_future_dailies_hidden(self):
        """Future-scheduled dailies aren't exposed in advance, even if other
        users somehow answered them already."""
        viewer = make_user('viewer')
        make_likert_survey(
            's_future',
            schedule_date=datetime.date.today() + datetime.timedelta(days=3),
        )
        self.client.force_authenticate(user=viewer)
        r = self.client.get('/api/surveys/past/')
        self.assertEqual(r.json()['results'], [])
