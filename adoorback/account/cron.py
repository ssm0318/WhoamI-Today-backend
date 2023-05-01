from datetime import timedelta, datetime

from django.utils.timezone import make_aware
from django.contrib.auth import get_user_model
from django_cron import CronJobBase, Schedule

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
