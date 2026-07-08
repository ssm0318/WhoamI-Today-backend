from django_cron import CronJobBase, Schedule

from qna.algorithms.data_crawler import select_daily_questions, \
    create_question_csv, create_user_csv
from qna.algorithms.recommender import create_ranks_csv
from qna.models import Question
from adoorback.utils.alerts import send_msg_to_slack


# Days of never-shown daily questions remaining at which to post a heads-up.
# One question is shown per day, so the never-shown count equals the number of
# days of fresh supply left before the picker starts repeating. Because supply
# descends by ~1/day and this cron runs once daily, each threshold is crossed on
# a single day, so every heads-up fires at most once as the count drops.
FRESH_QUESTION_ALERT_THRESHOLDS = (7, 3, 1)


def alert_if_daily_questions_low():
    # SafeDeleteManager already excludes soft-deleted questions. Never-shown
    # questions have an empty selected_dates array.
    fresh = Question.objects.filter(selected_dates__len=0).count()

    if fresh == 0:
        send_msg_to_slack(
            text="🚨 Daily question supply exhausted — every question has been "
                 "shown, so the picker is now recycling and repeating questions. "
                 "Author more daily questions ASAP.",
            level="CRITICAL",
        )
    elif fresh in FRESH_QUESTION_ALERT_THRESHOLDS:
        send_msg_to_slack(
            text=f"⏳ ~{fresh} days of fresh daily questions left — time to author more.",
            level="WARNING",
        )


class DailyQuestionCronJob(CronJobBase):
    schedule = Schedule(run_every_mins=0)

    code = 'qna.algorithms.data_crawler.select_daily_questions'

    def do(self):
        print('=========================')
        print("Checking for daily questions...............")
        select_daily_questions()
        alert_if_daily_questions_low()
        print("Cron job complete...............")
        print('=========================')


class RankQuestionsCronJob(CronJobBase):
    RUN_EVERY_MINS = 60 * 24 * 14

    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'qna.algorithms.recommender.create_ranks_csv'

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
