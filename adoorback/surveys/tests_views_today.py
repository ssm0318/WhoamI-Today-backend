import datetime

from rest_framework import status
from rest_framework.test import APITestCase

from surveys._test_helpers import make_likert_survey, make_user


class SurveyOfTheDayViewTests(APITestCase):
    def test_returns_null_when_no_survey_today(self):
        viewer = make_user('viewer')
        self.client.force_authenticate(user=viewer)
        r = self.client.get('/api/surveys/today/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIsNone(r.json()['survey'])

    def test_returns_survey_when_scheduled(self):
        viewer = make_user('viewer')
        s = make_likert_survey('today', schedule_date=datetime.date.today())
        self.client.force_authenticate(user=viewer)
        r = self.client.get('/api/surveys/today/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        body = r.json()
        self.assertEqual(body['survey']['slug'], s.slug)
        self.assertEqual(len(body['survey']['questions']), 2)
        self.assertFalse(body['survey']['user_has_responded'])

    def test_unauthenticated_returns_401_or_403(self):
        r = self.client.get('/api/surveys/today/')
        self.assertIn(r.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
