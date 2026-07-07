from datetime import date, datetime, time as dtime
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from account.cron import SendDailySurveyNotiCronJob, SendDailyWhoAmINotiCronJob
from notification.models import Notification
from surveys.models import CADENCE_DAILY, ScheduledSurvey, Survey


User = get_user_model()


class _CronUserManager:
    def __init__(self, users, admin=None):
        self.users = users
        self.admin = admin

    def all(self):
        return self.users

    def filter(self, **kwargs):
        return SimpleNamespace(get=lambda *args, **kwargs: self.admin)


class PushNotificationPreferenceProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='pref_user',
            email='pref@example.com',
            password='pw',
            timezone='UTC',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = reverse('current-user-detail')

    def test_current_user_can_update_push_preferences(self):
        response = self.client.patch(self.url, {
            'push_enabled': 'false',
            'daily_prompt_push_enabled': 'false',
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['push_enabled'])
        self.assertFalse(response.data['daily_prompt_push_enabled'])

        self.user.refresh_from_db()
        self.assertFalse(self.user.push_enabled)
        self.assertFalse(self.user.daily_prompt_push_enabled)


class DailyPromptPushPreferenceCronTests(TestCase):
    @patch('notification.models.CustomFCMDevice.objects.filter')
    def test_daily_whoami_prompt_is_created_without_push_when_daily_prompt_push_is_off(
        self,
        mock_device_filter,
    ):
        admin = User.objects.create_superuser(
            username='admin',
            email='whoami.today.official@gmail.com',
            password='pw',
        )
        fake_now = timezone.make_aware(datetime.combine(date.today(), dtime(16, 0)), timezone.utc)
        user = User.objects.create_user(
            username='quiet',
            email='quiet@example.com',
            password='pw',
            timezone='UTC',
            current_ver='version_w',
            noti_time=fake_now.time(),
            noti_period_days=[str(fake_now.weekday())],
        )
        user.daily_prompt_push_enabled = False
        user.save(update_fields=['daily_prompt_push_enabled'])

        before = Notification.objects.filter(user=user).count()
        mock_device_filter.reset_mock()
        fake_user_model = SimpleNamespace(objects=_CronUserManager([user], admin=admin))
        with patch('account.cron.User', fake_user_model):
            with patch('account.cron.timezone.now', return_value=fake_now):
                SendDailyWhoAmINotiCronJob().do()

        self.assertEqual(Notification.objects.filter(user=user).count(), before + 1)
        called_user_ids = [
            kwargs.get('user_id') for args, kwargs in mock_device_filter.call_args_list
        ]
        self.assertNotIn(user.id, called_user_ids)

    @patch('notification.models.CustomFCMDevice.objects.filter')
    def test_daily_survey_prompt_is_created_without_push_when_daily_prompt_push_is_off(
        self,
        mock_device_filter,
    ):
        survey = Survey.objects.create(slug='daily', title_en='Daily', title_ko='Daily')
        today = date.today()
        ScheduledSurvey.objects.create(
            survey=survey,
            cadence=CADENCE_DAILY,
            window_start=today,
            window_end=today,
            allow_late=False,
            sequence_index=1,
        )
        user = User.objects.create_user(
            username='survey_quiet',
            email='survey_quiet@example.com',
            password='pw',
            timezone='UTC',
        )
        user.daily_prompt_push_enabled = False
        user.save(update_fields=['daily_prompt_push_enabled'])

        before = Notification.objects.filter(user=user).count()
        fake_now = timezone.make_aware(datetime.combine(today, dtime(20, 0)), timezone.utc)
        mock_device_filter.reset_mock()
        fake_user_model = SimpleNamespace(objects=_CronUserManager([user]))
        with patch('account.cron.User', fake_user_model):
            with patch('account.cron.timezone.now', return_value=fake_now):
                SendDailySurveyNotiCronJob().do()

        self.assertEqual(Notification.objects.filter(user=user).count(), before + 1)
        called_user_ids = [
            kwargs.get('user_id') for args, kwargs in mock_device_filter.call_args_list
        ]
        self.assertNotIn(user.id, called_user_ids)
