import datetime

from django.test import TestCase

from surveys.cron import RotateDailySurveyCronJob
from surveys.models import DailySurvey, Survey


class RotationCronTests(TestCase):
    def setUp(self):
        self.s1 = Survey.objects.create(slug='s1', type=Survey.LIKERT_5, title_en='1', title_ko='1')
        self.s2 = Survey.objects.create(slug='s2', type=Survey.LIKERT_5, title_en='2', title_ko='2')

    def test_schedules_tomorrow(self):
        RotateDailySurveyCronJob().do()
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        ds = DailySurvey.objects.get(date=tomorrow)
        self.assertIn(ds.survey, [self.s1, self.s2])

    def test_idempotent_on_rerun(self):
        RotateDailySurveyCronJob().do()
        RotateDailySurveyCronJob().do()
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        self.assertEqual(DailySurvey.objects.filter(date=tomorrow).count(), 1)

    def test_cycles_when_all_used(self):
        # Simulate both surveys used
        Survey.objects.update(last_used_date=datetime.date.today())
        RotateDailySurveyCronJob().do()
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        self.assertTrue(DailySurvey.objects.filter(date=tomorrow).exists())

    def test_no_op_when_no_surveys(self):
        Survey.objects.all().delete()
        RotateDailySurveyCronJob().do()
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        self.assertFalse(DailySurvey.objects.filter(date=tomorrow).exists())
