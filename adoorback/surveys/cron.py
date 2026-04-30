"""
RotateDailySurveyCronJob: select tomorrow's Survey and persist a DailySurvey row.

Runs in server time (UTC), mirroring qna.algorithms.data_crawler.select_daily_questions.
Idempotent: skip if a DailySurvey for tomorrow already exists.

Rotation: random pick from Survey.last_used_date IS NULL (i.e., never scheduled).
When all surveys have been used, reset all last_used_date to NULL and pick again,
mirroring the qna cycle.
"""
from __future__ import annotations

import datetime
import logging

from django_cron import CronJobBase, Schedule

from surveys.models import DailySurvey, Survey

logger = logging.getLogger(__name__)


class RotateDailySurveyCronJob(CronJobBase):
    schedule = Schedule(run_every_mins=0)
    code = 'surveys.rotate_daily_survey'

    def do(self):
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        if DailySurvey.objects.filter(date=tomorrow).exists():
            logger.info('RotateDailySurvey: already scheduled for %s', tomorrow)
            return
        candidate = Survey.objects.filter(last_used_date__isnull=True).order_by('?').first()
        if candidate is None:
            # cycle reset
            Survey.objects.update(last_used_date=None)
            candidate = Survey.objects.order_by('?').first()
        if candidate is None:
            logger.info('RotateDailySurvey: no surveys exist; skipping')
            return
        DailySurvey.objects.create(date=tomorrow, survey=candidate)
        candidate.last_used_date = tomorrow
        candidate.save(update_fields=['last_used_date', 'updated_at'])
        logger.info('RotateDailySurvey: scheduled %s for %s', candidate.slug, tomorrow)
