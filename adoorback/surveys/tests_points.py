import datetime

from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from surveys._test_helpers import make_likert_survey, make_user
from surveys.models import (
    CADENCE_DAILY, CADENCE_WEEKLY, PointAward, ScheduledSurvey, Survey,
    SurveyResponse,
)


class SurveyPointAwardSubmitTests(APITestCase):
    def _payload_for(self, survey):
        questions = list(survey.questions.order_by('order'))
        return {'answers': [
            {'question_id': questions[0].id, 'value': 4},
            {'question_id': questions[1].id, 'value': 2},
        ]}

    def test_first_submit_creates_one_award_for_scheduled_opportunity(self):
        viewer = make_user('viewer')
        survey = make_likert_survey('rewarded')
        survey.point_value = 12
        survey.save(update_fields=['point_value'])
        today = datetime.date.today()
        scheduled = ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_WEEKLY,
            window_start=today,
            window_end=today,
            allow_late=True,
            sequence_index=1,
        )
        self.client.force_authenticate(user=viewer)

        response = self.client.post(
            f'/api/surveys/{survey.slug}/responses/',
            self._payload_for(survey),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        award = PointAward.objects.get(user=viewer, scheduled_survey=scheduled)
        self.assertEqual(award.response_id, response.json()['id'])
        self.assertEqual(award.source_kind, 'survey')
        self.assertEqual(award.source_slug, 'rewarded')
        self.assertEqual(award.awarded_points, 12)
        self.assertEqual(response.json()['point_award']['effective_points'], 12)

    def test_editable_resubmit_does_not_create_second_award(self):
        viewer = make_user('viewer')
        survey = make_likert_survey('editable_reward')
        survey.point_value = 20
        survey.editable = True
        survey.save(update_fields=['point_value', 'editable'])
        today = datetime.date.today()
        ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_WEEKLY,
            window_start=today,
            window_end=today,
            allow_late=True,
            sequence_index=1,
        )
        self.client.force_authenticate(user=viewer)

        first = self.client.post(
            f'/api/surveys/{survey.slug}/responses/',
            self._payload_for(survey),
            format='json',
        )
        second = self.client.post(
            f'/api/surveys/{survey.slug}/responses/',
            self._payload_for(survey),
            format='json',
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PointAward.objects.filter(user=viewer, source_slug=survey.slug).count(), 1)
        award = PointAward.objects.get(user=viewer, source_slug=survey.slug)
        self.assertEqual(award.response_id, first.json()['id'])

    def test_repeatable_submit_same_schedule_does_not_create_second_award(self):
        viewer = make_user('viewer')
        survey = make_likert_survey('repeatable_reward')
        survey.point_value = 7
        survey.repeatable = True
        survey.save(update_fields=['point_value', 'repeatable'])
        today = datetime.date.today()
        ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_WEEKLY,
            window_start=today,
            window_end=today,
            allow_late=True,
            sequence_index=1,
        )
        self.client.force_authenticate(user=viewer)

        self.client.post(f'/api/surveys/{survey.slug}/responses/', self._payload_for(survey), format='json')
        self.client.post(f'/api/surveys/{survey.slug}/responses/', self._payload_for(survey), format='json')

        self.assertEqual(SurveyResponse.objects.filter(user=viewer, survey=survey).count(), 2)
        self.assertEqual(PointAward.objects.filter(user=viewer, source_slug=survey.slug).count(), 1)

    def test_unmet_point_prereq_creates_zero_point_award(self):
        viewer = make_user('viewer')
        prereq = make_likert_survey('prereq')
        survey = make_likert_survey('locked_reward')
        survey.point_value = 9
        survey.point_prereq_slug = prereq.slug
        survey.save(update_fields=['point_value', 'point_prereq_slug'])
        today = datetime.date.today()
        ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_WEEKLY,
            window_start=today,
            window_end=today,
            allow_late=True,
            sequence_index=1,
        )
        self.client.force_authenticate(user=viewer)

        response = self.client.post(
            f'/api/surveys/{survey.slug}/responses/',
            self._payload_for(survey),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        award = PointAward.objects.get(user=viewer, source_slug=survey.slug)
        self.assertEqual(award.awarded_points, 0)
        self.assertIn('Prereq prereq not completed', award.note)
        self.assertEqual(response.json()['point_award']['note'], award.note)

    def test_zero_point_survey_creates_no_award(self):
        viewer = make_user('viewer')
        survey = make_likert_survey('unrewarded')
        today = datetime.date.today()
        ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_WEEKLY,
            window_start=today,
            window_end=today,
            allow_late=True,
            sequence_index=1,
        )
        self.client.force_authenticate(user=viewer)

        response = self.client.post(
            f'/api/surveys/{survey.slug}/responses/',
            self._payload_for(survey),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.json()['point_award'])
        self.assertFalse(PointAward.objects.filter(user=viewer, source_slug=survey.slug).exists())


class ReimbursementApiTests(APITestCase):
    def test_reimbursement_state_returns_totals_awards_and_available_max(self):
        viewer = make_user('viewer')
        survey = make_likert_survey('weekly_reward')
        survey.point_value = 16
        survey.save(update_fields=['point_value'])
        today = datetime.date.today()
        scheduled = ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_WEEKLY,
            window_start=today,
            window_end=today,
            allow_late=True,
            sequence_index=1,
        )
        response = SurveyResponse.objects.create(user=viewer, survey=survey)
        PointAward.objects.create(
            user=viewer,
            source_kind='survey',
            source_slug=survey.slug,
            scheduled_survey=scheduled,
            response=response,
            awarded_points=16,
            adjusted_points=4,
            note='Downgraded after audit.',
        )
        self.client.force_authenticate(user=viewer)

        result = self.client.get('/api/surveys/reimbursement/')

        self.assertEqual(result.status_code, status.HTTP_200_OK)
        body = result.json()
        self.assertEqual(body['provisional_total'], 16)
        self.assertEqual(body['adjusted_total'], 4)
        self.assertGreaterEqual(body['available_max'], 16)
        self.assertEqual(body['points_per_dollar'], 8)
        self.assertEqual(body['awards'][0]['effective_points'], 4)
        self.assertEqual(body['awards'][0]['awarded_points'], 16)
        self.assertEqual(body['awards'][0]['title_en'], 'T')
        self.assertEqual(body['awards'][0]['scheduled_survey_id'], scheduled.id)


class SurveyPointStateSerializerTests(APITestCase):
    def test_index_entries_include_point_state_and_prereq_lock(self):
        viewer = make_user('viewer')
        prereq = make_likert_survey('point_prereq')
        survey = make_likert_survey('locked_index')
        survey.point_value = 11
        survey.point_prereq_slug = prereq.slug
        survey.save(update_fields=['point_value', 'point_prereq_slug'])
        today = datetime.date.today()
        ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_WEEKLY,
            window_start=today,
            window_end=today,
            allow_late=True,
            sequence_index=1,
        )
        self.client.force_authenticate(user=viewer)

        result = self.client.get('/api/surveys/index/')

        self.assertEqual(result.status_code, status.HTTP_200_OK)
        entry = result.json()['available_now'][0]
        self.assertEqual(entry['point_value'], 11)
        self.assertEqual(entry['point_locked_by_prereq_slug'], 'point_prereq')
        self.assertEqual(entry['point_locked_by_prereq_title_en'], 'T')
        self.assertIsNone(entry['point_award'])


class PointManualCreditCommandTests(TestCase):
    def test_credit_wit_bot_audit_is_idempotent(self):
        viewer = make_user('viewer')

        call_command('credit_wit_bot_audit', '--user', viewer.username, '--pts', '10')
        call_command('credit_wit_bot_audit', '--user', viewer.username, '--pts', '10')

        awards = PointAward.objects.filter(
            user=viewer,
            source_kind='wit_bot_audit',
            source_slug='wit_bot_audit',
        )
        self.assertEqual(awards.count(), 1)
        self.assertEqual(awards.get().awarded_points, 10)
