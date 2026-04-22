import contextlib

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from account.signals import suppress_version_push

User = get_user_model()


class Command(BaseCommand):
    help = 'Swap all users between Version W and Version Q. All users flip their current_ver simultaneously.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would change without saving.'
        )
        parser.add_argument(
            '--user-ids', nargs='*', type=int,
            help='Only swap specific user IDs (default: all non-superusers).'
        )
        parser.add_argument(
            '--no-push', action='store_true',
            help='Skip dispatching silent pushes for the current_ver changes.'
        )

    def handle(self, *args, **options):
        queryset = User.objects.exclude(is_superuser=True)
        if options['user_ids']:
            queryset = queryset.filter(id__in=options['user_ids'])

        now = timezone.now()
        count = 0
        push_ctx = suppress_version_push() if options['no_push'] else contextlib.nullcontext()
        with push_ctx:
            for user in queryset:
                old_ver = user.current_ver
                user.current_ver = 'version_q' if old_ver == 'version_w' else 'version_w'
                user.ver_changed_at = now
                if not options['dry_run']:
                    user.save(update_fields=['current_ver', 'ver_changed_at'])
                self.stdout.write(f'  {user.username}: {old_ver} -> {user.current_ver}')
                count += 1

        action = 'Would swap' if options['dry_run'] else 'Swapped'
        push_note = ' (pushes suppressed)' if options['no_push'] and not options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(f'{action} {count} users.{push_note}'))
