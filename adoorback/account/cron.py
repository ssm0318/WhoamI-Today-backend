from datetime import time

from django.utils import timezone
from backports.zoneinfo import ZoneInfo
from django.contrib.auth import get_user_model
from django_cron import CronJobBase, Schedule

from qna.models import Question
from notification.models import Notification, NotificationActor

User = get_user_model()


class SendDailyWhoAmINotiCronJob(CronJobBase):
    # run every hour at 0 minute
    RUN_AT_TIMES = ['00:00', '01:00', '02:00', '03:00', '04:00', '05:00', '06:00',
                    '07:00', '08:00', '09:00', '10:00', '11:00', '12:00',
                    '13:00', '14:00', '15:00', '16:00', '17:00', '18:00',
                    '19:00', '20:00', '21:00', '22:00', '23:00']

    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    code = 'account.send_daily_who_am_i_noti_cron_job'

    def do(self):
        print('=========================')
        print("Creating daily notifications for WhoAmI...............")

        admin = User.objects.filter(is_superuser=True).first()
        try:
            daily_question = Question.objects.daily_questions()[0].content
        except:
            print('=========================')
            print('daily question does not exist!')
            print('Cron job did not perform successfully.')
            print('=========================')
            return

        num_notis_before = Notification.objects.admin_only().count()
        all_users = User.objects.all()

        for user in all_users:
            if user.noti_time is None:
                continue
            if user.noti_time == time(timezone.now().astimezone(ZoneInfo(user.timezone)).hour, 0):
                noti = Notification.objects.create(user=user,
                                                   target=admin,
                                                   origin=admin,
                                                   message_ko=f"{user.username}님, 오늘의 후엠아이를 남겨보세요! - {daily_question}",
                                                   message_en=f"{user.username}, time to leave your whoami for today! - {daily_question}",
                                                   redirect_url='/')
                NotificationActor.objects.create(user=admin, notification=noti)

        num_notis_after = Notification.objects.admin_only().count()
        print(f'{num_notis_after - num_notis_before} notifications sent!')
        print('=========================')
        print("Cron job complete...............")
        print('=========================')
