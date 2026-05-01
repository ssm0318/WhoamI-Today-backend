import datetime

from rest_framework import status
from rest_framework.test import APITestCase

from surveys._test_helpers import (
    connect, make_likert_survey, make_mixed_survey, make_user, respond,
)
from surveys.models import FREE_TEXT, LIKERT_5, Survey, SurveyAnswer, SurveyQuestion, SurveyResponse


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

    def test_404_when_results_hidden(self):
        viewer = make_user('viewer')
        s = make_likert_survey('s', schedule_date=datetime.date.today() - datetime.timedelta(days=1))
        s.results_hidden = True
        s.save()
        respond(viewer, s, [3, 3])
        self.client.force_authenticate(user=viewer)
        r = self.client.get(f'/api/surveys/{s.slug}/results/')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_200_with_panels_when_gates_pass(self):
        viewer = make_user('viewer')
        s = make_likert_survey('s', schedule_date=datetime.date.today() - datetime.timedelta(days=1))
        respond(viewer, s, [4, 2])
        # 5 close-friends respond + 5 friends-only respond → friends_responders=10, cf_responders=5
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
        self.assertEqual(len(body['panels']), 1)
        panel = body['panels'][0]
        self.assertEqual(panel['kind'], 'aggregated_likert')
        self.assertTrue(panel['friends_available'])
        self.assertTrue(panel['close_friends_available'])
        self.assertEqual(panel['friends']['n'], 10)
        self.assertEqual(panel['close_friends']['n'], 5)

    def test_population_suppressed_when_below_threshold(self):
        viewer = make_user('viewer')
        s = make_likert_survey('s', schedule_date=datetime.date.today() - datetime.timedelta(days=1))
        respond(viewer, s, [3, 3])
        for i in range(3):
            u = make_user(f'u{i}')
            respond(u, s, [3, 3])
        self.client.force_authenticate(user=viewer)
        r = self.client.get(f'/api/surveys/{s.slug}/results/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        panel = r.json()['panels'][0]
        self.assertFalse(panel['population_available'])
        self.assertEqual(panel['population_suppressed_reason'], 'too_few_responders')
        self.assertIsNone(panel['population'])

    def test_mixed_survey_yields_two_panels(self):
        viewer = make_user('viewer')
        s = make_mixed_survey('m', n_likert=2, n_free_text=1,
                              schedule_date=datetime.date.today() - datetime.timedelta(days=1))
        # Viewer + 5 mock responders to clear population gate
        respond(viewer, s, [4, 2, "feeling great about this week"])
        for i in range(5):
            u = make_user(f'u{i}')
            respond(u, s, [3, 3, "feeling great about everything"])
        self.client.force_authenticate(user=viewer)
        r = self.client.get(f'/api/surveys/{s.slug}/results/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        panels = r.json()['panels']
        self.assertEqual(len(panels), 2)
        kinds = {p['kind'] for p in panels}
        self.assertEqual(kinds, {'aggregated_likert', 'wordcloud'})
        # Wordcloud panel must have friend buckets disabled (privacy posture).
        wc = next(p for p in panels if p['kind'] == 'wordcloud')
        self.assertEqual(wc['friends_suppressed_reason'], 'view_friend_disabled')
        self.assertEqual(wc['close_friends_suppressed_reason'], 'view_friend_disabled')

    def test_hidden_question_excluded_from_panels(self):
        viewer = make_user('viewer')
        s = Survey.objects.create(slug='h', title_en='T', title_ko='T')
        SurveyQuestion.objects.create(
            survey=s, order=1, type=LIKERT_5, prompt_en='Q1', prompt_ko='Q1',
        )
        SurveyQuestion.objects.create(
            survey=s, order=2, type=FREE_TEXT, prompt_en='Q2', prompt_ko='Q2',
            result_hidden=True,
        )
        from surveys.models import CADENCE_DAILY, ScheduledSurvey
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        ScheduledSurvey.objects.create(
            survey=s, cadence=CADENCE_DAILY,
            window_start=yesterday, window_end=yesterday,
            allow_late=False, sequence_index=1,
        )
        # 5 responders to clear gate
        for i in range(6):
            u = make_user(f'u{i}') if i > 0 else viewer
            response = SurveyResponse.objects.create(user=u, survey=s)
            for q in s.questions.order_by('order'):
                v = 3 if q.type == LIKERT_5 else "text response here"
                SurveyAnswer.objects.create(response=response, question=q, value=v)
        self.client.force_authenticate(user=viewer)
        r = self.client.get(f'/api/surveys/{s.slug}/results/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        # Only the likert panel should appear; the hidden free_text question is excluded.
        panels = r.json()['panels']
        self.assertEqual(len(panels), 1)
        self.assertEqual(panels[0]['kind'], 'aggregated_likert')
