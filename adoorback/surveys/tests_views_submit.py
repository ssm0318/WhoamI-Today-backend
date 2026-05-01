from rest_framework import status
from rest_framework.test import APITestCase

from surveys._test_helpers import make_likert_survey, make_user
from surveys.models import SurveyResponse


class SurveySubmitViewTests(APITestCase):
    def test_create_response_returns_201(self):
        viewer = make_user('viewer')
        s = make_likert_survey('s')
        self.client.force_authenticate(user=viewer)
        questions = list(s.questions.order_by('order'))
        payload = {'answers': [
            {'question_id': questions[0].id, 'value': 4},
            {'question_id': questions[1].id, 'value': 2},
        ]}
        r = self.client.post(f'/api/surveys/{s.slug}/responses/', payload, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SurveyResponse.objects.filter(user=viewer, survey=s).count(), 1)

    def test_duplicate_returns_409(self):
        viewer = make_user('viewer')
        s = make_likert_survey('s2')
        self.client.force_authenticate(user=viewer)
        questions = list(s.questions.order_by('order'))
        payload = {'answers': [
            {'question_id': questions[0].id, 'value': 4},
            {'question_id': questions[1].id, 'value': 2},
        ]}
        self.client.post(f'/api/surveys/{s.slug}/responses/', payload, format='json')
        r2 = self.client.post(f'/api/surveys/{s.slug}/responses/', payload, format='json')
        self.assertEqual(r2.status_code, status.HTTP_409_CONFLICT)

    def test_unknown_slug_returns_404(self):
        viewer = make_user('viewer')
        self.client.force_authenticate(user=viewer)
        r = self.client.post('/api/surveys/nonexistent/responses/', {'answers': []}, format='json')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)
