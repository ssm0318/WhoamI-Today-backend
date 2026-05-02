from django_cron import CronJobBase, Schedule

from mission.algorithms.data_crawler import select_daily_missions


class DailyMissionCronJob(CronJobBase):
    schedule = Schedule(run_every_mins=0)
    code = 'mission.algorithms.data_crawler.select_daily_missions'

    def do(self):
        print('=========================')
        print("Checking for daily missions...............")
        select_daily_missions()
        print("Cron job complete...............")
        print('=========================')
