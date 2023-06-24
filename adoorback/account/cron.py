from datetime import timedelta, datetime

from django.utils.timezone import make_aware
from django.contrib.auth import get_user_model
from django_cron import CronJobBase, Schedule

from feed.models import Question
from notification.models import Notification

User = get_user_model()


class SendSelectQuestionsNotiCronJob(CronJobBase):
    RUN_EVERY_MINS = 60 * 16  # every 16 hours

    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'feed.algorithms.data_crawler.select_daily_questions'

    def do(self):
        print('=========================')
        print("Creating notifications for select questions...............")
        threshold_date = make_aware(datetime.now()) - timedelta(days=3)
        users = User.objects.filter(created_at__gt=threshold_date)
        admin = User.objects.filter(is_superuser=True).first()

        num_notis_before = Notification.objects.admin_only().count()

        for user in users:
            if user.question_history is None:
                Notification.objects.create(user=user,
                                            actor=admin,
                                            target=admin,
                                            origin=admin,
                                            message=f"{user.username}님, 답하고 싶은 질문을"
                                                    f" 고르고 취향에 맞는 질문을 추천 받아 보실래요?",
                                            redirect_url='/select-questions')
        num_notis_after = Notification.objects.admin_only().count()
        print(f'{num_notis_after - num_notis_before} notifications sent!')
        print('=========================')
        print("Cron job complete...............")
        print('=========================')


class SendAddFriendsNotiCronJob(CronJobBase):
    RUN_EVERY_MINS = 60 * 12  # every 12 hours

    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'feed.algorithms.data_crawler.select_daily_questions'

    def do(self):
        print('=========================')
        print("Creating notifications for adding friends...............")
        threshold_date = make_aware(datetime.now()) - timedelta(days=3)
        users = User.objects.filter(created_at__gt=threshold_date)
        admin = User.objects.filter(is_superuser=True).first()

        num_notis_before = Notification.objects.admin_only().count()

        for user in users:
            if len(user.friend_ids) < 3:
                Notification.objects.create(user=user,
                                            actor=admin,
                                            target=admin,
                                            origin=admin,
                                            message=f"{user.username}님, 보다 재밌는 어도어 이용을 위해 친구를 추가해보세요!",
                                            redirect_url='/search')
        num_notis_after = Notification.objects.admin_only().count()
        print(f'{num_notis_after - num_notis_before} notifications sent!')
        print('=========================')
        print("Cron job complete...............")
        print('=========================')


class SendDailyWhoAmINotiCronJob(CronJobBase):
    RUN_EVERY_MINS = 1  # every minute

    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'account.send_daily_who_am_i_noti_cron_job'

    def do(self):
        print('=========================')
        print("Creating daily notifications for WhoAmI...............")
        users = User.objects.filter(noti_time=datetime.now().time())
        admin = User.objects.filter(is_superuser=True).first()
        try:
            daily_question = Question.objects.daily_questions[0].content
        except:
            print('=========================')
            print('daily question does not exist!')
            print('Cron job did not perform successfully.')
            print('=========================')
            return

        num_notis_before = Notification.objects.admin_only().count()

        for user in users:
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

>>>>>>> 12af4db (feat: #26 add noti_time field to user model and add SendDailyWhoAmINotiCronJob)
