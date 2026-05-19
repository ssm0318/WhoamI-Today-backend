import datetime

from rest_framework import status
from rest_framework.test import APITestCase

from surveys._test_helpers import make_likert_survey, make_user
from surveys.models import CADENCE_ANYTIME, ScheduledSurvey, SurveyDraft


class SurveyDraftApiTests(APITestCase):
    def setUp(self):
        self.user = make_user('draft_viewer')
        self.survey = make_likert_survey('draftable')
        ScheduledSurvey.objects.create(
            survey=self.survey,
            cadence=CADENCE_ANYTIME,
            window_start=datetime.date(2026, 1, 1),
            window_end=None,
            allow_late=True,
            sequence_index=9101,
        )
        self.questions = list(self.survey.questions.order_by('order'))
        self.client.force_authenticate(user=self.user)

    def _draft_payload(self, *, value=4, answered_pages=1, progress_pct=50):
        return {
            'answers': {str(self.questions[0].id): value},
            'current_page_index': answered_pages - 1,
            'total_pages': 2,
            'answered_pages': answered_pages,
            'progress_pct': progress_pct,
        }

    def test_put_then_get_upserts_draft(self):
        first = self.client.put(
            f'/api/surveys/{self.survey.slug}/draft/',
            self._draft_payload(value=4),
            format='json',
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(SurveyDraft.objects.filter(user=self.user, survey=self.survey).count(), 1)
        self.assertEqual(first.json()['answers'], {str(self.questions[0].id): 4})
        self.assertEqual(first.json()['progress_pct'], 50)
        self.assertIn('saved_at', first.json())

        second = self.client.put(
            f'/api/surveys/{self.survey.slug}/draft/',
            self._draft_payload(value=2, answered_pages=2, progress_pct=100),
            format='json',
        )
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(SurveyDraft.objects.filter(user=self.user, survey=self.survey).count(), 1)
        self.assertEqual(second.json()['answers'], {str(self.questions[0].id): 2})
        self.assertEqual(second.json()['answered_pages'], 2)
        self.assertEqual(second.json()['progress_pct'], 100)

        recovered = self.client.get(f'/api/surveys/{self.survey.slug}/draft/')
        self.assertEqual(recovered.status_code, status.HTTP_200_OK)
        self.assertEqual(recovered.json()['answers'], {str(self.questions[0].id): 2})
        self.assertEqual(recovered.json()['progress_pct'], 100)

    def test_index_includes_draft_progress_for_unanswered_entry(self):
        self.client.put(
            f'/api/surveys/{self.survey.slug}/draft/',
            self._draft_payload(value=4, answered_pages=1, progress_pct=50),
            format='json',
        )

        response = self.client.get('/api/surveys/index/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry = next(
            e for e in response.json()['available_now']
            if e['survey']['slug'] == self.survey.slug
        )

        self.assertEqual(entry['draft']['progress_pct'], 50)
        self.assertEqual(entry['draft']['answered_pages'], 1)
        self.assertIn('saved_at', entry['draft'])

    def test_detail_includes_full_draft_for_immediate_recovery(self):
        self.client.put(
            f'/api/surveys/{self.survey.slug}/draft/',
            self._draft_payload(value=4, answered_pages=1, progress_pct=50),
            format='json',
        )

        response = self.client.get(f'/api/surveys/{self.survey.slug}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        draft = response.json()['draft']
        self.assertEqual(draft['answers'], {str(self.questions[0].id): 4})
        self.assertEqual(draft['progress_pct'], 50)
        self.assertIn('saved_at', draft)

    def test_submit_clears_existing_draft(self):
        self.client.put(
            f'/api/surveys/{self.survey.slug}/draft/',
            self._draft_payload(value=4),
            format='json',
        )
        self.assertEqual(SurveyDraft.objects.filter(user=self.user, survey=self.survey).count(), 1)

        submit = self.client.post(
            f'/api/surveys/{self.survey.slug}/responses/',
            {
                'answers': [
                    {'question_id': self.questions[0].id, 'value': 4},
                    {'question_id': self.questions[1].id, 'value': 2},
                ],
            },
            format='json',
        )

        self.assertEqual(submit.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SurveyDraft.objects.filter(user=self.user, survey=self.survey).count(), 0)

    def test_delete_draft_is_idempotent(self):
        self.client.put(
            f'/api/surveys/{self.survey.slug}/draft/',
            self._draft_payload(value=4),
            format='json',
        )

        first = self.client.delete(f'/api/surveys/{self.survey.slug}/draft/')
        second = self.client.delete(f'/api/surveys/{self.survey.slug}/draft/')
        recovered = self.client.get(f'/api/surveys/{self.survey.slug}/draft/')

        self.assertEqual(first.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(second.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(recovered.status_code, status.HTTP_404_NOT_FOUND)
