from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from account.models import DiscoverFeed


class Command(BaseCommand):
    help = (
        'Reset (delete) discover feed items for a user so the next API request '
        'triggers a fresh feed generation. Useful for testing the daily refresh logic.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            default=None,
            help='Username to reset discover feed for. If omitted, resets all users.',
        )

    def handle(self, *args, **options):
        User = get_user_model()
        username = options['username']

        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                self.stderr.write(self.style.ERROR(f'User "{username}" not found.'))
                return

            count, _ = DiscoverFeed.objects.filter(user=user).delete()
            self.stdout.write(self.style.SUCCESS(
                f'Deleted {count} discover feed items for user "{username}". '
                f'Next API request will generate a fresh feed.'
            ))
        else:
            count, _ = DiscoverFeed.objects.all().delete()
            self.stdout.write(self.style.SUCCESS(
                f'Deleted {count} discover feed items for ALL users. '
                f'Next API request will generate a fresh feed for each user.'
            ))
