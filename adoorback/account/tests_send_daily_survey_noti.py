from datetime import date, datetime, time as dtime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from account.cron import SendDailySurveyNotiCronJob
from chat.wit_bot import WIT_BOT_USERNAME, ensure_wit_bot_user
from notification.models import Notification, NotificationActor
from surveys.models import DailySurvey, Survey


User = get_user_model()


class SendDailySurveyNotiCronTests(TestCase):
    def test_short_circuits_when_no_survey_for_today(self):
        before = Notification.objects.count()
        SendDailySurveyNotiCronJob().do()
        self.assertEqual(Notification.objects.count(), before)

    def test_authors_notification_as_wit_bot_when_survey_exists(self):
        s = Survey.objects.create(slug='s', type=Survey.LIKERT_5, title_en='T', title_ko='T')
        DailySurvey.objects.create(date=date.today(), survey=s)
        ensure_wit_bot_user()
        u = User.objects.create(username='alice', email='a@x.com', timezone='UTC')

        # Pin "now" to 20:00 UTC so the 10-minute gate fires for the UTC user.
        fake_now = timezone.make_aware(datetime.combine(date.today(), dtime(20, 0)), timezone.utc)
        with patch('account.cron.timezone.now', return_value=fake_now):
            SendDailySurveyNotiCronJob().do()

        notis = Notification.objects.filter(user=u)
        self.assertEqual(notis.count(), 1)
        actor_users = NotificationActor.objects.filter(notification=notis.first()).values_list(
            'user__username', flat=True
        )
        self.assertIn(WIT_BOT_USERNAME, actor_users)
        self.assertEqual(notis.first().redirect_url, '/share')
