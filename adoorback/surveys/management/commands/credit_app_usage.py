from django.core.management.base import BaseCommand, CommandError

from surveys.app_usage import sync_app_usage_awards


class Command(BaseCommand):
    help = 'Credit rule-based app usage points for phase 1 and/or phase 2.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--phase',
            type=int,
            choices=(1, 2),
            default=None,
            help='Study phase to credit. Omit to evaluate both phases.',
        )
        parser.add_argument('--user', default=None, help='Optional username to evaluate.')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print computed credits without writing PointAward rows.',
        )

    def handle(self, *args, **opts):
        rows = sync_app_usage_awards(
            phase=opts['phase'],
            username=opts['user'],
            dry_run=opts['dry_run'],
        )
        if opts['user'] and not rows:
            raise CommandError(f"User not found: {opts['user']}")

        changed = 0
        for row in rows:
            if row['status'] in {'created', 'upgraded', 'would_credit'}:
                changed += 1
            if row['points'] > 0 or opts['user']:
                metrics = row['metrics']
                self.stdout.write(
                    f"{row['user'].username}\tphase={row['phase']}\t"
                    f"points={row['points']}\tstatus={row['status']}\t"
                    f"active_days={metrics.active_days}\t"
                    f"first4_days={metrics.first_four_days}\t"
                    f"later_days={metrics.later_days}\t"
                    f"core_events={metrics.core_event_count}"
                )

        verb = 'Would credit' if opts['dry_run'] else 'Credited/updated'
        self.stdout.write(self.style.SUCCESS(f'{verb} {changed} app usage awards.'))
