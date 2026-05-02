from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from django_cron import CronJobBase, Schedule

from check_in.models import CheckIn
from notification.models import Notification, NotificationActor

CHECKIN_EXPIRY_HOURS = 12

User = get_user_model()


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

        # Identify users experiencing their first archive before the bulk update
        first_archive_user_ids = set(
            expired.filter(user__has_received_first_archive_noti=False)
            .values_list('user_id', flat=True)
            .distinct()
        )

        count = expired.update(is_active=False)

        if first_archive_user_ids:
            self._send_first_archive_notifications(first_archive_user_ids)

        print(f"{count} check-in(s) expired.")
        print("Cron job for check-in expiry complete.")

    @staticmethod
    def _send_first_archive_notifications(user_ids):
        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            print("WARNING: No admin user found; skipping first-archive notifications.")
            return

        updated_count = User.objects.filter(
            id__in=user_ids,
            has_received_first_archive_noti=False,
        ).update(has_received_first_archive_noti=True)

        if updated_count == 0:
            return

        users = User.objects.filter(id__in=user_ids, has_received_first_archive_noti=True)
        for user in users:
            noti = Notification.objects.create(
                user=user,
                target=admin,
                origin=admin,
                message_ko="첫 번째 체크인이 아카이브되었어요! 체크인은 12시간이 지나면 아카이브되어 나만 볼 수 있어요.",
                message_en="You archived your first check-in! After 12 hours, your check-ins are archived and become visible only to you.",
                redirect_url='/check-in/archive',
            )
            NotificationActor.objects.create(user=admin, notification=noti)

        print(f"{updated_count} first-archive notification(s) sent.")
