from django_cron import CronJobBase, Schedule
from django.contrib.auth import get_user_model

from feed.algorithms.data_crawler import select_daily_questions, \
    create_question_csv, create_user_csv
from feed.algorithms.recommender import create_ranks_csv
from notification.models import Notification


class DailyQuestionCronJob(CronJobBase):
    RUN_AT_TIMES = ['00:00']

    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    code = 'feed.algorithms.data_crawler.select_daily_questions'

    def do(self):
        print('=========================')
        print("Selecting daily questions...............")
        select_daily_questions()
        print('=========================')
        print("Sending daily question notifications...............")
        User = get_user_model()
        admin = User.objects.filter(is_superuser=True).first()

        for user in User.objects.all():
            Notification.objects.create(user=user,
                                        actor=admin,
                                        target=admin,
                                        origin=admin,
                                        message="딩동! 오늘의 질문 배달 왔습니다~ 지금 구경하러 가볼까요?",
                                        redirect_url='/questions')
        print('=========================')
        print("Cron job complete...............")
        print('=========================')


class RankQuestionsCronJob(CronJobBase):
    RUN_EVERY_MINS = 60 * 24 * 14

    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'feed.algorithms.recommender.create_ranks_csv'

    def do(self):
        print('=========================')
        print("Creating questions csv...............")
        create_question_csv()
        print('=========================')
        print("Creating user interactions csv...............")
        create_user_csv()
        print('=========================')
        print("Getting question ranks for all users...............")
        create_ranks_csv()
        print("Cron job complete...............")
        print('=========================')
