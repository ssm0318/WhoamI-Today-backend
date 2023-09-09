from datetime import time

from django.utils import timezone
from backports.zoneinfo import ZoneInfo
from django.contrib.auth import get_user_model
from django_cron import CronJobBase, Schedule

from feed.models import Question
from notification.models import Notification

User = get_user_model()


class SendDailyWhoAmINotiCronJob(CronJobBase):
    RUN_EVERY_MINS = 60  # every 1 hour

    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
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
            if not user.noti_on:
                continue
            if user.noti_time is None:
                continue
            if user.noti_time == time(timezone.now().astimezone(ZoneInfo(user.timezone)).hour, 0):
                Notification.objects.create(user=user,
                                            actor=admin,
                                            target=admin,
                                            origin=admin,
                                            message_ko=f"{user.username}님, 오늘의 후엠아이를 남겨보세요! - {daily_question}",
                                            message_en=f"{user.username}, time to leave your whoami for today! - {daily_question}",
                                            redirect_url='/home')

        num_notis_after = Notification.objects.admin_only().count()
        print(f'{num_notis_after - num_notis_before} notifications sent!')
        print('=========================')
        print("Cron job complete...............")
        print('=========================')
