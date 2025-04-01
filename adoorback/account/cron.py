from datetime import timedelta

from django.utils import timezone
from zoneinfo import ZoneInfo
from django.contrib.auth import get_user_model
from django_cron import CronJobBase, Schedule

from account.models import AppSession
from notification.models import Notification, NotificationActor
from qna.models import Question


User = get_user_model()

SESSION_TIMEOUT_MINUTES = 2 


class SendDailyWhoAmINotiCronJob(CronJobBase):
    schedule = Schedule(run_every_mins=0)
    code = 'account.send_daily_who_am_i_noti_cron_job'

    def do(self):
        print('=========================')
        print("Creating daily notifications for WhoAmI...............")

        admin = User.objects.filter(is_superuser=True).get(email='whoami.today.official@gmail.com')

        num_notis_before = Notification.objects.admin_only().count()
        all_users = User.objects.all()

        for user in all_users:
            if user.noti_time is None:
                continue

            user_local_time = timezone.now().astimezone(ZoneInfo(user.timezone))
            
            current_weekday = user_local_time.weekday()  # Monday=0, Sunday=6
            if str(current_weekday) not in user.noti_period_days:
                continue

            try:
                daily_question = Question.objects.daily_questions(user)[0]
                daily_question_en = daily_question.content_en
                daily_question_ko = daily_question.content_ko
                daily_question_id = daily_question.id
            except:
                print(f'🚨 ERROR: daily question does not exist for user {user.username} ({user.id})!')
                print("Failed to send daily notification for this user.")
                continue

            user_now = user_local_time
            noti_datetime = user_now.replace(hour=user.noti_time.hour, minute=user.noti_time.minute)
            time_diff = abs(user_now - noti_datetime)
            if time_diff <= timedelta(minutes=10):
                # daily notification
                if user.current_ver == 'default':
                    noti = Notification.objects.create(user=user,
                                                    target=admin,
                                                    origin=admin,
                                                    message_ko=f"{user.username}님, 오늘 친구들에게 한 마디 남겨보세요!",
                                                    message_en=f"{user.username}, quick reminder to share something with your friends today!",
                                                    redirect_url=f'/friends/feed')
                    NotificationActor.objects.create(user=admin, notification=noti)
                elif user.current_ver == 'experiment':
                    noti = Notification.objects.create(user=user,
                                                    target=admin,
                                                    origin=admin,
                                                    message_ko=f"{user.username}님, 오늘 친구들에게 한 마디 남겨보세요! — {daily_question_ko}",
                                                    message_en=f"{user.username}, quick reminder to share something with your friends today! — {daily_question_en}",
                                                    redirect_url=f'/questions/{daily_question_id}/new')
                    NotificationActor.objects.create(user=admin, notification=noti)

        num_notis_after = Notification.objects.admin_only().count()
        print(f'{num_notis_after - num_notis_before} notifications sent!')
        print('=========================')
        print("Cron job complete...............")
        print('=========================')


class SendDailySurveyNotiCronJob(CronJobBase):
    schedule = Schedule(run_every_mins=0)
    code = 'account.send_daily_survey_noti_cron_job'

    def do(self):
        print('=========================')
        print("Creating daily survey notifications...............")

        admin = User.objects.filter(is_superuser=True).get(email='whoami.today.official@gmail.com')

        num_notis_before = Notification.objects.admin_only().count()
        all_users = User.objects.all()

        for user in all_users:
            user_local_time = timezone.now().astimezone(ZoneInfo(user.timezone))
            user_now = user_local_time
            noti_time = user_now.replace(hour=20, minute=0, second=0, microsecond=0)
            time_diff = abs(user_now - noti_time)
            if time_diff <= timedelta(minutes=10):
                noti = Notification.objects.create(user=user,
                                                target=admin,
                                                origin=admin,
                                                message_ko=f"{user.username}님, 데일리 설문을 작성해주세요!",
                                                message_en=f"{user.username}, time to fill out the daily survey!",
                                                redirect_url=f'')
                NotificationActor.objects.create(user=admin, notification=noti)

            if user.username == 'gina_park' or user.username == 'yuri':
                noti_time = user_now.replace(hour=12, minute=40, second=0, microsecond=0)
                time_diff = abs(user_now - noti_time)
                if time_diff <= timedelta(minutes=10):
                    noti = Notification.objects.create(user=user,
                                                    target=admin,
                                                    origin=admin,
                                                    message_ko=f"{user.username}님, 데일리 설문을 작성해주세요!",
                                                    message_en=f"{user.username}, time to fill out the daily survey!",
                                                    redirect_url=f'')
                    NotificationActor.objects.create(user=admin, notification=noti)

        num_notis_after = Notification.objects.admin_only().count()
        print(f'{num_notis_after - num_notis_before} notifications sent!')
        print('=========================')
        print("Cron job complete...............")
        print('=========================')


class AutoCloseSessionsCronJob(CronJobBase):
    schedule = Schedule(run_every_mins=0)
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
