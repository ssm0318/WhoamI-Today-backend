import datetime

from rest_framework import status
from rest_framework.test import APITestCase

from surveys._test_helpers import connect, make_likert_survey, make_user, respond


class ResultsViewTests(APITestCase):
    def test_403_when_user_has_not_responded(self):
        viewer = make_user('viewer')
        s = make_likert_survey('s', schedule_date=datetime.date.today() - datetime.timedelta(days=1))
        self.client.force_authenticate(user=viewer)
        r = self.client.get(f'/api/surveys/{s.slug}/results/')
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(r.json()['needs_submission'])

    def test_403_when_survey_day_is_today(self):
        viewer = make_user('viewer')
        s = make_likert_survey('s', schedule_date=datetime.date.today())
        respond(viewer, s, [3, 3])
        self.client.force_authenticate(user=viewer)
        r = self.client.get(f'/api/surveys/{s.slug}/results/')
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(r.json()['needs_submission'])
        self.assertEqual(r.json()['available_at'], datetime.date.today().isoformat())

    def test_200_with_buckets_when_gates_pass(self):
        viewer = make_user('viewer')
        s = make_likert_survey('s', schedule_date=datetime.date.today() - datetime.timedelta(days=1))
        respond(viewer, s, [4, 2])
        # 5 close-friends respond + 5 friends-only respond → friends_responders=10, cf_responders=5
        # (viewer counted in population only, not friends)
        for i in range(5):
            cf = make_user(f'cf{i}')
            connect(viewer, cf, a_choice='close_friend', b_choice='close_friend')
            respond(cf, s, [3, 3])
        for i in range(5):
            f = make_user(f'fr{i}')
            connect(viewer, f)
            respond(f, s, [4, 2])
        self.client.force_authenticate(user=viewer)
        r = self.client.get(f'/api/surveys/{s.slug}/results/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        body = r.json()
        self.assertTrue(body['friends_available'])
        self.assertTrue(body['close_friends_available'])
        self.assertIsNotNone(body['friends'])
        self.assertIsNotNone(body['close_friends'])
        self.assertEqual(body['friends']['n'], 10)
        self.assertEqual(body['close_friends']['n'], 5)

    def test_population_suppressed_when_below_threshold(self):
        viewer = make_user('viewer')
        s = make_likert_survey('s', schedule_date=datetime.date.today() - datetime.timedelta(days=1))
        respond(viewer, s, [3, 3])
        for i in range(3):  # 3 strangers respond → total 4 responders, below 5
            u = make_user(f'u{i}')
            respond(u, s, [3, 3])
        self.client.force_authenticate(user=viewer)
        r = self.client.get(f'/api/surveys/{s.slug}/results/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        body = r.json()
        self.assertFalse(body['population_available'])
        self.assertEqual(body['population_suppressed_reason'], 'too_few_responders')
        self.assertIsNone(body['population'])
