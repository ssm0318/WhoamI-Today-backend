from datetime import timedelta

from django.utils import timezone
from django_cron import CronJobBase, Schedule

from check_in.models import CheckIn

CHECKIN_EXPIRY_HOURS = 12


class ExpireCheckInsCronJob(CronJobBase):
    schedule = Schedule(run_every_mins=0)
    code = 'check_in.expire_check_ins'

    def do(self):
        print("Checking for expired check-ins...")

        expiry_threshold = timezone.now() - timedelta(hours=CHECKIN_EXPIRY_HOURS)

        expired = CheckIn.objects.filter(
            is_active=True,
            created_at__lt=expiry_threshold,
        )

        count = expired.update(is_active=False)

        print(f"{count} check-in(s) expired.")
        print("Cron job for check-in expiry complete.")
