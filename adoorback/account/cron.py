from datetime import time, datetime, timedelta

from django.utils import timezone
from backports.zoneinfo import ZoneInfo
from django.contrib.auth import get_user_model
from django_cron import CronJobBase, Schedule

from account.models import AppSession
from notification.models import Notification, NotificationActor
from qna.models import Question


User = get_user_model()

SESSION_TIMEOUT_MINUTES = 2 


class SendDailyWhoAmINotiCronJob(CronJobBase):
    # run every hour at 0 minute
    RUN_AT_TIMES = [(datetime.min + timedelta(hours=i)).strftime('%H:%M') for i in range(24)]

    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    code = 'account.send_daily_who_am_i_noti_cron_job'

    def do(self):
        print('=========================')
        print("Creating daily notifications for WhoAmI...............")

        admin = User.objects.filter(is_superuser=True).get(email='whoami.today.official@gmail.com')
        try:
            daily_question = Question.objects.daily_questions()[0]
            daily_question_en = daily_question.content_en
            daily_question_ko = daily_question.content_ko
            daily_question_id = daily_question.id
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

            user_local_time = timezone.now().astimezone(ZoneInfo(user.timezone))
            
            current_weekday = user_local_time.weekday()  # Monday=0, Sunday=6
            if str(current_weekday) not in user.noti_period_days:
                continue

            if user.noti_time == time(user_local_time.hour, 0):
                # daily notification
                if user.current_ver == 'default':
                    noti = Notification.objects.create(user=user,
                                                    target=admin,
                                                    origin=admin,
                                                    message_ko=f"{user.username}님, 오늘도 후엠아이에 글을 남기러 가볼까요?",
                                                    message_en=f"{user.username}, time to leave your whoami for today!",
                                                    redirect_url=f'/feed')
                    NotificationActor.objects.create(user=admin, notification=noti)
                elif user.current_ver == 'experiment':
                    noti = Notification.objects.create(user=user,
                                                    target=admin,
                                                    origin=admin,
                                                    message_ko=f"{user.username}님, 오늘의 후엠아이를 남겨보세요! - {daily_question_ko}",
                                                    message_en=f"{user.username}, time to leave your whoami for today! - {daily_question_en}",
                                                    redirect_url=f'/questions/{daily_question_id}/new')
                    NotificationActor.objects.create(user=admin, notification=noti)

        num_notis_after = Notification.objects.admin_only().count()
        print(f'{num_notis_after - num_notis_before} notifications sent!')
        print('=========================')
        print("Cron job complete...............")
        print('=========================')


class AutoCloseSessionsCronJob(CronJobBase):
    RUN_EVERY_MINS = SESSION_TIMEOUT_MINUTES

    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = "session.auto_close_sessions"

    def do(self):
        print("Checking for inactive sessions...")

        TIMEOUT_THRESHOLD = timezone.now() - timedelta(minutes=SESSION_TIMEOUT_MINUTES)

        # 1. Find expired sessions where a touch was received, 
        # but no new touch has been sent for more than SESSION_TIMEOUT_MINUTES minutes
        expired_sessions = AppSession.objects.filter(
            end_time__isnull=True,
            last_touch_time__lt=TIMEOUT_THRESHOLD
        )

        # 2. Include sessions where no touch was ever sent, 
        # and the session has existed for more than SESSION_TIMEOUT_MINUTES minutes
        expired_sessions |= AppSession.objects.filter(
            end_time__isnull=True,
            last_touch_time__isnull=True,
            start_time__lt=TIMEOUT_THRESHOLD
        )

        count = 0
        for session in expired_sessions:
            session.end_time = timezone.now()
            session.save()
            count += 1

        print(f"{count} sessions automatically closed.")
        print("Cron job for session cleanup complete.")
