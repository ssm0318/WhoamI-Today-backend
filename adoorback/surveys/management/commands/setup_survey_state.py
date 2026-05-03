"""One-shot setup of the survey app's runtime state.

Brings a freshly-migrated DB to a working state:

  1. Loads the real-study Survey content from `study_2026q2.yaml`.
  2. Seeds the 37-row 4-week study schedule (re-runs the seed migration's
     `seed_schedule` function, which short-circuits if Survey rows are missing
     — that's why step 1 must run first; the actual migration ran on an
     empty DB during `migrate` and did nothing).
  3. (Optional, `--mock-dailies`) Loads `mock_test_today.yaml` and creates the
     three May 1-3 mock daily ScheduledSurvey rows for pre-study testing.
  4. (Optional, `--include-demos --demo-email <email>`) Loads demo
     question-type surveys + populates them with mock responses + seeds a
     viewer response so each `/surveys/<slug>/results` page renders unlocked.
     Dev-only — never pass on production.

Idempotent on every step:
  - `load_surveys` is upsert-by-slug.
  - `seed_schedule` uses `update_or_create` keyed on (cadence, sequence_index).
  - The mock-daily loop uses the same upsert pattern.
  - `seed_question_type_demos` is idempotent (skips already-seeded responses).

Local dev (one-liner — covers everything QA-related):

    DB_HOST=localhost python manage.py setup_survey_state \\
        --mock-dailies --include-demos --demo-email <your-email>

Production deploy (one-liner — never include demos):

    docker compose exec web python manage.py setup_survey_state --mock-dailies
"""
from datetime import date
from importlib import import_module
from pathlib import Path

from django.apps import apps as django_apps
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from surveys.models import CADENCE_DAILY, ScheduledSurvey, Survey


FIXTURES_DIR = Path(__file__).resolve().parents[2] / 'fixtures'

# May 1-3 mock daily slots — see mock_test_today.yaml for the matching Survey
# content. sequence_index 900-902 stays clear of the study schedule's 1..28.
MOCK_DAILY_SLOTS = [
    ('mock_test_2026q2',     date(2026, 5, 1), 900),
    ('mock_test_2026_05_02', date(2026, 5, 2), 901),
    ('mock_test_2026_05_03', date(2026, 5, 3), 902),
]


class Command(BaseCommand):
    help = (
        'Bring a freshly-migrated DB to a working survey state: load the study '
        'YAML, seed the 4-week study schedule, optionally load+schedule the May '
        '1-3 mock dailies, and optionally seed demo surveys + mock responses '
        'for QA.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--mock-dailies',
            action='store_true',
            help='Also load and schedule the May 1-3 mock daily surveys.',
        )
        parser.add_argument(
            '--include-demos',
            action='store_true',
            help='Also load demo question-type surveys and seed mock responses. '
                 'Dev-only — do not pass on production.',
        )
        parser.add_argument(
            '--demo-email',
            help='Dev viewer email; required with --include-demos.',
        )

    def handle(self, *args, **opts):
        if opts['include_demos'] and not opts['demo_email']:
            raise CommandError('--include-demos requires --demo-email')

        study_yaml = FIXTURES_DIR / 'study_2026q2.yaml'
        if not study_yaml.exists():
            raise CommandError(f'Required fixture missing: {study_yaml}')

        # 1. Load study Survey content. Idempotent upsert by slug.
        self.stdout.write(self.style.NOTICE(f'[1] Loading {study_yaml.name} ...'))
        call_command('load_surveys', str(study_yaml))

        # 2. Seed the 4-week study schedule. The seed migration short-circuits
        #    when Survey rows don't exist (which is the state during `migrate`
        #    on a fresh DB), so we always re-run after step 1. Idempotent —
        #    `update_or_create` keyed on (cadence, sequence_index).
        self.stdout.write(self.style.NOTICE('[2] Seeding 4-week study schedule ...'))
        seed_module = import_module('surveys.migrations.0004_seed_study_schedule')
        seed_module.seed_schedule(django_apps, None)

        # 3. May 1-3 mock dailies (optional).
        if opts['mock_dailies']:
            mock_yaml = FIXTURES_DIR / 'mock_test_today.yaml'
            if not mock_yaml.exists():
                raise CommandError(f'Required fixture missing: {mock_yaml}')
            self.stdout.write(self.style.NOTICE(f'[3a] Loading {mock_yaml.name} ...'))
            call_command('load_surveys', str(mock_yaml))

            self.stdout.write(self.style.NOTICE('[3b] Scheduling May 1-3 mock dailies ...'))
            for slug, day, seq in MOCK_DAILY_SLOTS:
                try:
                    survey = Survey.objects.get(slug=slug)
                except Survey.DoesNotExist:
                    raise CommandError(
                        f'Survey {slug!r} not found in DB after load_surveys — '
                        'check mock_test_today.yaml.'
                    )
                ScheduledSurvey.objects.update_or_create(
                    cadence=CADENCE_DAILY, sequence_index=seq,
                    defaults={
                        'survey': survey,
                        'window_start': day,
                        'window_end': day,
                        'allow_late': True,
                    },
                )
                self.stdout.write(f'    scheduled {slug} on {day} (seq={seq})')
        else:
            self.stdout.write(self.style.NOTICE('[3] Skipping mock dailies (no --mock-dailies)'))

        # 4. Demo surveys + mock responses (optional, dev-only).
        if opts['include_demos']:
            self.stdout.write(self.style.NOTICE('[4] Seeding demo question-type surveys ...'))
            call_command('seed_question_type_demos', email=opts['demo_email'])
        else:
            self.stdout.write(self.style.NOTICE('[4] Skipping demos (no --include-demos)'))

        self.stdout.write(self.style.SUCCESS(
            f'Done. Surveys={Survey.objects.count()} '
            f'ScheduledSurveys={ScheduledSurvey.objects.count()}'
        ))
