from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

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
            '--reset', action='store_true',
            help='Reset all user content data before swapping versions. '
                 'Takes a pg_dump backup first, then hard-deletes content.',
        )

    def handle(self, *args, **options):
        # Run experiment data reset before swapping if --reset is set
        if options['reset']:
            if options['dry_run']:
                self.stdout.write(self.style.MIGRATE_HEADING(
                    '--- Reset (dry-run): showing what would be deleted ---'
                ))
                call_command('reset_experiment_data', dry_run=True)
            else:
                self.stdout.write(self.style.MIGRATE_HEADING(
                    '--- Resetting experiment data before version swap ---'
                ))
                call_command('reset_experiment_data', no_input=True)
            self.stdout.write('')

        queryset = User.objects.exclude(is_superuser=True)
        if options['user_ids']:
            queryset = queryset.filter(id__in=options['user_ids'])

        now = timezone.now()
        count = 0
        for user in queryset:
            old_ver = user.current_ver
            user.current_ver = 'version_q' if old_ver == 'version_w' else 'version_w'
            user.ver_changed_at = now
            if not options['dry_run']:
                user.save(update_fields=['current_ver', 'ver_changed_at'])
            self.stdout.write(f'  {user.username}: {old_ver} -> {user.current_ver}')
            count += 1

        action = 'Would swap' if options['dry_run'] else 'Swapped'
        self.stdout.write(self.style.SUCCESS(f'{action} {count} users.'))
