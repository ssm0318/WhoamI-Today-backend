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

        admin = User.objects.filter(is_superuser=True).get(email='team.whoami.today@gmail.com')
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
                noti = Notification.objects.create(user=user,
                                                   target=admin,
                                                   origin=admin,
                                                   message_ko=f"{user.username}님, 오늘의 후엠아이를 남겨보세요! - {daily_question_ko}",
                                                   message_en=f"{user.username}, time to leave your whoami for today! - {daily_question_en}",
                                                   redirect_url=f'/questions/{daily_question_id}/new')
                NotificationActor.objects.create(user=admin, notification=noti)

                # signup notification
                if not user.signup_noti_status:
                    user.signup_noti_status = {
                        "profile_noti_sent": False,
                        "checkin_noti_sent": False,
                        "note_noti_sent": False,
                        "ping_noti_sent": False
                    }
                    user.save()

                status = user.signup_noti_status
                if not status["ping_noti_sent"]:  # need to send signup notification
                    sent = False
                    if not status["profile_noti_sent"]:
                        if not (user.username != user.email or user.pronouns or user.bio):
                            self.send_notification(
                                user, admin, f"{user.username}님, 프로필을 업데이트 해보세요!", f"{user.username}, how about updating your profile information?", "/settings/edit-profile"
                            )
                            sent = True
                        status["profile_noti_sent"] = True
                    if not sent and not status["checkin_noti_sent"]:
                        if not user.check_in_set.exists():
                            self.send_notification(
                                user, admin, f"{user.username}님, 체크인을 꾸며보세요!", f"{user.username}, create a check-in so your friends can check your status!", "/check-in/edit"
                            )
                            sent = True
                        status["checkin_noti_sent"] = True
                    if not sent and not status["note_noti_sent"]:
                        if not user.note_set.exists():
                            self.send_notification(
                                user, admin, f"{user.username}님, 첫 노트를 작성해보세요!", f"{user.username}, write your first note and share your thoughts!", "/notes/new"
                            )
                            sent = True
                        status["note_noti_sent"] = True
                    if not sent and user.has_connected_users:
                        self.send_notification(
                            user, admin, f"{user.username}님, 친구에게 쪽지를 보내보세요!", f"{user.username}, ping your friend to say hi!", "/friends"
                        )
                        status["ping_noti_sent"] = True

                    user.signup_noti_status = status
                    user.save()

        num_notis_after = Notification.objects.admin_only().count()
        print(f'{num_notis_after - num_notis_before} notifications sent!')
        print('=========================')
        print("Cron job complete...............")
        print('=========================')

    def send_notification(self, user, admin, message_ko, message_en, redirect_url):       
        noti = Notification.objects.create(
            user=user,
            target=admin,
            origin=admin,
            message_ko=message_ko,
            message_en=message_en,
            redirect_url=redirect_url
        )
        NotificationActor.objects.create(user=admin, notification=noti)


class AutoCloseSessionsCronJob(CronJobBase):
    RUN_EVERY_MINS = SESSION_TIMEOUT_MINUTES

    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = "session.auto_close_sessions"

    def do(self):
        print("Checking for inactive sessions...")

        TIMEOUT_THRESHOLD = timezone.now() - timedelta(minutes=SESSION_TIMEOUT_MINUTES)

        # 1. Find expired sessions where a ping was received, 
        # but no new ping has been sent for more than SESSION_TIMEOUT_MINUTES minutes
        expired_sessions = AppSession.objects.filter(
            end_time__isnull=True,
            last_ping_time__lt=TIMEOUT_THRESHOLD
        )

        # 2. Include sessions where no ping was ever sent, 
        # and the session has existed for more than SESSION_TIMEOUT_MINUTES minutes
        expired_sessions |= AppSession.objects.filter(
            end_time__isnull=True,
            last_ping_time__isnull=True,
            start_time__lt=TIMEOUT_THRESHOLD
        )

        count = 0
        for session in expired_sessions:
            session.end_time = timezone.now()
            session.save()
            count += 1

        print(f"{count} sessions automatically closed.")
        print("Cron job for session cleanup complete.")
