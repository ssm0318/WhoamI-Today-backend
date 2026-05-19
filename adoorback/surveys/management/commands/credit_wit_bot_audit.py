from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from surveys.models import PointAward
from surveys.points import (
    credit_manual_award, wit_bot_audit_source_for_phase,
    wit_bot_audit_version_for_group,
)


class Command(BaseCommand):
    help = 'Credit a participant for passing the Wit_bot audit.'

    def add_arguments(self, parser):
        parser.add_argument('--user', required=True, help='Username to credit.')
        parser.add_argument(
            '--phase',
            required=True,
            type=int,
            choices=(1, 2),
            help='Study phase to credit. Phase determines the W/Q version by user group.',
        )
        parser.add_argument(
            '--pts',
            type=int,
            default=None,
            help='Points to credit. Defaults to the configured phase-specific Wit_bot audit max.',
        )
        parser.add_argument('--note', default='', help='Optional audit note.')

    def handle(self, *args, **opts):
        User = get_user_model()
        try:
            user = User.objects.get(username=opts['user'])
        except User.DoesNotExist as exc:
            raise CommandError(f"User not found: {opts['user']}") from exc

        phase = opts['phase']
        phase_source = wit_bot_audit_source_for_phase(phase)
        phase_version = wit_bot_audit_version_for_group(user.user_group, phase)
        points = opts['pts'] if opts['pts'] is not None else phase_source['max_points']

        award = credit_manual_award(
            user=user,
            source_kind=PointAward.SOURCE_WIT_BOT_AUDIT,
            source_slug=phase_source['source_slug'],
            points=points,
            note=opts['note'],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Credited {award.awarded_points} {phase_source["title_en"]} '
                f'points to {user.username} ({phase_version})'
            )
        )
