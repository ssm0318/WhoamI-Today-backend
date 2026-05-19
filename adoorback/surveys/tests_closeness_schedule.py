from datetime import date, datetime
from importlib import import_module
from unittest.mock import patch

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from account.models import Connection
from surveys.models import (
    CADENCE_BIWEEKLY,
    ScheduledSurvey,
    Survey,
    SurveyQuestion,
    SurveyResponse,
)
from surveys.scheduling import _required_tokens_for_survey, get_survey_index


class ClosenessScheduleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create(username='alice', email='alice@example.com')
        phase1 = Survey.objects.create(
            slug='phase1_friend_closeness',
            title_en='Phase 1 friend closeness',
            title_ko='',
        )
        SurveyQuestion.objects.create(
            survey=phase1,
            order=1,
            type='per_friend_likert_5',
            prompt_en='How close do you feel to {{friend_name}}?',
            prompt_ko='{{friend_name}}',
        )
        SurveyQuestion.objects.create(
            survey=phase1,
            order=2,
            type='per_friend_likert_5',
            prompt_en='Earlier baseline was {{baseline_closeness}}/5.',
            prompt_ko='{{baseline_closeness}}',
            required=False,
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
        self.assertEqual(_required_tokens_for_survey(phase1.survey), set())

        with patch('surveys.scheduling._today_la_7am', return_value=date(2026, 5, 18)):
            due_today = get_survey_index(self.user)
        self.assertIn(phase1, due_today['available_now'])
        self.assertNotIn(phase1, due_today['late_but_accepted'])

        with patch('surveys.scheduling._today_la_7am', return_value=date(2026, 5, 19)):
            late_after_due_date = get_survey_index(self.user)
        self.assertNotIn(phase1, late_after_due_date['available_now'])
        self.assertIn(phase1, late_after_due_date['late_but_accepted'])

    def test_answered_phase1_closeness_does_not_stay_available_if_editable_flag_is_stale(self):
        seed_module = import_module('surveys.migrations.0021_seed_closeness_schedule')
        seed_module.seed_closeness(django_apps, None)

        phase1 = Survey.objects.get(slug='phase1_friend_closeness')
        phase1.editable = True
        phase1.save(update_fields=['editable'])
        SurveyResponse.objects.create(user=self.user, survey=phase1)

        with patch('surveys.scheduling._today_la_7am', return_value=date(2026, 5, 18)):
            index = get_survey_index(self.user)

        available_slugs = {entry.survey.slug for entry in index['available_now']}
        completed_slugs = {entry.survey.slug for entry in index['completed']}
        self.assertNotIn('phase1_friend_closeness', available_slugs)
        self.assertIn('phase1_friend_closeness', completed_slugs)

    def test_phase1_friend_closeness_is_not_editable(self):
        migration_module = import_module('surveys.migrations.0043_phase1_friend_closeness_noneditable')

        migration_module.make_phase1_friend_closeness_noneditable(django_apps, None)

        phase1 = Survey.objects.get(slug='phase1_friend_closeness')
        phase2 = Survey.objects.get(slug='phase2_friend_closeness')
        self.assertFalse(phase1.editable)
        self.assertFalse(phase1.repeatable)
        self.assertFalse(phase2.editable)


class ClosenessFriendEligibilityApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create(username='alice_api', email='alice_api@example.com')
        self.old_friend = User.objects.create(username='old_friend', email='old@example.com')
        self.new_friend = User.objects.create(username='new_friend', email='new@example.com')
        self.client.force_authenticate(user=self.user)

        self.survey = Survey.objects.create(
            slug='phase1_friend_closeness',
            title_en='Phase 1 friend closeness',
            title_ko='',
        )
        self.question = SurveyQuestion.objects.create(
            survey=self.survey,
            order=1,
            type='per_friend_likert_5',
            slug='phase1_friend_closeness_current',
            prompt_en='How close do you feel to {{friend_name}}?',
            prompt_ko='{{friend_name}}',
        )
        ScheduledSurvey.objects.create(
            survey=self.survey,
            cadence=CADENCE_BIWEEKLY,
            sequence_index=6,
            window_start=date(2026, 5, 18),
            window_end=date(2026, 5, 18),
            allow_late=True,
        )
        old_connection = Connection.objects.create(
            user1=self.user,
            user2=self.old_friend,
            user1_choice='friend',
            user2_choice='friend',
        )
        new_connection = Connection.objects.create(
            user1=self.user,
            user2=self.new_friend,
            user1_choice='friend',
            user2_choice='friend',
        )
        Connection.objects.filter(id=old_connection.id).update(
            created_at=datetime(2026, 5, 15, 12, tzinfo=timezone.get_current_timezone()),
        )
        Connection.objects.filter(id=new_connection.id).update(
            created_at=datetime(2026, 5, 18, 12, tzinfo=timezone.get_current_timezone()),
        )

    def test_detail_excludes_friends_connected_less_than_two_days_before_window(self):
        response = self.client.get('/api/surveys/phase1_friend_closeness/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usernames = [
            q['target_user_username']
            for q in response.json()['questions']
            if q.get('target_user_username')
        ]
        self.assertEqual(usernames, ['old_friend'])

    def test_submit_rejects_too_new_friend_for_closeness_survey(self):
        with patch('surveys.points._today_la_7am', return_value=date(2026, 5, 18)):
            response = self.client.post(
                '/api/surveys/phase1_friend_closeness/responses/',
                {
                    'answers': [
                        {
                            'question_id': self.question.id,
                            'target_user_id': self.new_friend.id,
                            'value': 4,
                        },
                    ],
                },
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(SurveyResponse.objects.filter(user=self.user, survey=self.survey).exists())
