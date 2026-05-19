from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from surveys.models import PointAward
from surveys.points import credit_manual_award
from surveys.reimbursement_config import INTERVIEW_SIGNUP_MAX_POINTS


class Command(BaseCommand):
    help = 'Credit a participant for completing the interview signup step.'

    def add_arguments(self, parser):
        parser.add_argument('--user', required=True, help='Username to credit.')
        parser.add_argument(
            '--pts',
            type=int,
            default=INTERVIEW_SIGNUP_MAX_POINTS,
            help='Points to credit. Defaults to the configured interview signup max.',
        )
        parser.add_argument('--note', default='', help='Optional audit note.')

    def handle(self, *args, **opts):
        User = get_user_model()
        try:
            user = User.objects.get(username=opts['user'])
        except User.DoesNotExist as exc:
            raise CommandError(f"User not found: {opts['user']}") from exc

        award = credit_manual_award(
            user=user,
            source_kind=PointAward.SOURCE_INTERVIEW_SIGNUP,
            source_slug=PointAward.SOURCE_INTERVIEW_SIGNUP,
            points=opts['pts'],
            note=opts['note'],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Credited {award.awarded_points} interview signup points to {user.username}'
            )
        )
