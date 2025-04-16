from django.core.management.base import BaseCommand
from django.db.models import Q, F
from account.models import FriendRequest


class Command(BaseCommand):
    help = 'Delete stale friend requests that were created before requestee\'s ver_changed_at and not accepted yet.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('Starting deletion of stale friend requests...'))

        stale_requests = FriendRequest.objects.filter(
            accepted__isnull=True,
            requestee__ver_changed_at__isnull=False,
            created_at__lt=F('requestee__ver_changed_at')
        )

        count = stale_requests.count()

        if count == 0:
            self.stdout.write('No stale friend requests found.')
        else:
            stale_requests.delete()
            self.stdout.write(self.style.SUCCESS(f'{count} stale friend request(s) deleted.'))
