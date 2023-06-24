from datetime import timedelta, datetime

from django.utils.timezone import make_aware
from django.contrib.auth import get_user_model
from django_cron import CronJobBase, Schedule

from notification.models import Notification

User = get_user_model()
