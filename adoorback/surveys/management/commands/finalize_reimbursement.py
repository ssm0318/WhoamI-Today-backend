import os
from contextlib import nullcontext

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction

from surveys.final_reimbursement import (
    build_final_award_specs, participant_queryset, reconcile_user_awards,
    validate_interview_accounts,
)
from surveys.models import PointAward


def configure_restore_database(alias: str) -> None:
    if alias in settings.DATABASES:
        return

    required = {
        'NAME': os.environ.get('RESTORE_DB_NAME'),
        'HOST': os.environ.get('RESTORE_DB_HOST'),
        'USER': os.environ.get('RESTORE_DB_USER'),
        'PASSWORD': os.environ.get('RESTORE_DB_PASSWORD'),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise CommandError(
            f"Database alias '{alias}' is not configured and restore settings are "
            f"missing: {', '.join(missing)}"
        )

    database = settings.DATABASES['default'].copy()
    database.update(required)
    database['PORT'] = os.environ.get(
        'RESTORE_DB_PORT',
        os.environ.get('DB_PORT', database.get('PORT', '5432')),
    )
    settings.DATABASES[alias] = database
    connections.databases[alias] = database


class Command(BaseCommand):
    help = (
        'Reconcile the frozen final reimbursement ledger. Runs as a dry run '
        'unless --apply is supplied.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Write the reconciled non-survey awards in one transaction.',
        )
        parser.add_argument(
            '--phase1-database',
            default='phase1_restore',
            help='Database alias containing phase 1 app activity.',
        )
        parser.add_argument(
            '--phase2-database',
            default='default',
            help='Database alias containing phase 2 app activity.',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        phase1_database = options['phase1_database']
        phase2_database = options['phase2_database']
        for alias in {phase1_database, phase2_database} - {'default'}:
            configure_restore_database(alias)

        participants = list(participant_queryset())
        try:
            validate_interview_accounts(participants)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        mode = 'APPLY' if apply else 'DRY RUN'
        self.stdout.write(f'{mode}: {len(participants)} participants')
        totals = {'created': 0, 'updated': 0, 'unchanged': 0}
        context = transaction.atomic() if apply else nullcontext()
        with context:
            for user in participants:
                specs = build_final_award_specs(
                    user,
                    phase1_database=phase1_database,
                    phase2_database=phase2_database,
                )
                result = reconcile_user_awards(user, specs, apply=apply)
                for key in totals:
                    totals[key] += getattr(result, key)
                survey_points = sum(
                    award.effective_points
                    for award in PointAward.objects.filter(
                        user=user,
                        source_kind=PointAward.SOURCE_SURVEY,
                    )
                )
                self.stdout.write(
                    f'{user.id}\t{user.username}\t'
                    f'survey={survey_points}\tnon_survey={result.projected_points}\t'
                    f'total={survey_points + result.projected_points}\t'
                    f'created={result.created}\tupdated={result.updated}\t'
                    f'unchanged={result.unchanged}'
                )

        action = 'Reconciled' if apply else 'Would reconcile'
        self.stdout.write(self.style.SUCCESS(
            f"{action}: created={totals['created']}, updated={totals['updated']}, "
            f"unchanged={totals['unchanged']}."
        ))
