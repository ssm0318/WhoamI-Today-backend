import datetime

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.utils import IntegrityError
from django.test import TestCase

from surveys.models import (
    CADENCE_DAILY, ScheduledSurvey, Survey, SurveyAnswer, SurveyOption,
    SurveyQuestion, SurveyResponse,
)


class SurveyModelTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create(username='alice', email='a@x.com')

    def test_survey_slug_is_unique(self):
        Survey.objects.create(slug='s1', title_en='T', title_ko='T')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Survey.objects.create(slug='s1', title_en='T2', title_ko='T2')

    def test_question_order_unique_per_survey(self):
        s = Survey.objects.create(slug='s2', title_en='T', title_ko='T')
        SurveyQuestion.objects.create(survey=s, order=1, prompt_en='Q1', prompt_ko='Q1')
        with self.assertRaises(IntegrityError), transaction.atomic():
            SurveyQuestion.objects.create(survey=s, order=1, prompt_en='Q2', prompt_ko='Q2')

    def test_option_order_unique_per_question(self):
        s = Survey.objects.create(slug='s3', title_en='T', title_ko='T')
        q = SurveyQuestion.objects.create(survey=s, order=1, prompt_en='Q', prompt_ko='Q')
        SurveyOption.objects.create(question=q, order=1, label_en='A', label_ko='A', value=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SurveyOption.objects.create(question=q, order=1, label_en='B', label_ko='B', value=2)

    def test_scheduled_survey_cadence_seq_unique(self):
        s = Survey.objects.create(slug='s4', title_en='T', title_ko='T')
        d = datetime.date(2026, 5, 1)
        ScheduledSurvey.objects.create(
            survey=s, cadence=CADENCE_DAILY, sequence_index=1,
            window_start=d, window_end=d, allow_late=False,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ScheduledSurvey.objects.create(
                survey=s, cadence=CADENCE_DAILY, sequence_index=1,
                window_start=d, window_end=d, allow_late=False,
            )

    def test_response_unique_per_user_per_survey(self):
        s = Survey.objects.create(slug='s5', title_en='T', title_ko='T')
        SurveyResponse.objects.create(user=self.user, survey=s)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SurveyResponse.objects.create(user=self.user, survey=s)

    def test_answer_unique_per_response_per_question(self):
        s = Survey.objects.create(slug='s6', title_en='T', title_ko='T')
        q = SurveyQuestion.objects.create(survey=s, order=1, prompt_en='Q', prompt_ko='Q')
        r = SurveyResponse.objects.create(user=self.user, survey=s)
        SurveyAnswer.objects.create(response=r, question=q, value=3)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SurveyAnswer.objects.create(response=r, question=q, value=4)
