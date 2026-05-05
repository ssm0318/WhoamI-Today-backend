"""Manually trigger the biweekly crossover version flip.

`account.cron.CrossoverPhaseFlipCronJob` runs this same logic on the
daily cron schedule, but it's also exposed as a one-shot command for:
  - Emergency / out-of-band recovery if the cron didn't fire
  - Operator verification ("show me what would change")
  - Local testing with --today=2026-05-18

This command does NOT do the destructive cleanup that
`process_version_switch` performs (friendships, subscriptions, chats,
notifications). The biweekly crossover keeps relationships intact —
only `current_ver` flips, since the friend-visibility filter
(`current_ver=user.current_ver`) still matches when both ends of a
same-group friendship flip together.
"""
from datetime import date

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        'Flip User.current_ver per the biweekly crossover schedule. '
        'Idempotent — only updates rows whose current_ver disagrees with '
        'the phase-aware expected value for their user_group.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--today',
            help='Override today\'s date (YYYY-MM-DD). Useful for testing '
                 'or running a flip ahead of the cron tick. Defaults to '
                 'la_today() (the same LA-7am-boundary date used by the '
                 'survey scheduling layer).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what WOULD change without writing to the DB.',
        )

    def handle(self, *args, **opts):
        from account.phase_versioning import (
            expected_version_for, flip_users_to_expected_version, la_today,
        )

        if opts['today']:
            try:
                today = date.fromisoformat(opts['today'])
            except ValueError:
                raise CommandError('--today must be YYYY-MM-DD')
        else:
            today = la_today()

        self.stdout.write(self.style.NOTICE(
            f'Crossover flip — today: {today}'
        ))
        for group in ('group_w_first', 'group_q_first'):
            expected = expected_version_for(group, today)
            self.stdout.write(f'  {group}: expected current_ver = {expected}')

        if opts['dry_run']:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            for group in ('group_w_first', 'group_q_first'):
                expected = expected_version_for(group, today)
                n = (
                    User.objects.filter(user_group=group, is_superuser=False)
                    .exclude(current_ver=expected)
                    .count()
                )
                self.stdout.write(f'  {group}: would flip {n} user(s)')
            self.stdout.write(self.style.WARNING('Dry run — no changes written.'))
            return

        summary = flip_users_to_expected_version(today)
        total = sum(summary.values())
        for group, n in summary.items():
            self.stdout.write(f'  {group}: flipped {n} user(s)')
        self.stdout.write(self.style.SUCCESS(f'Total flipped: {total}'))
