"""One-shot setup of the survey app's runtime state.

Brings a freshly-migrated DB to a working state for the long-form study:

  1. Loads every survey fixture in `surveys/fixtures/`. Order matters
     because some fixtures depend on others' anchors:
       - study_2026q2.yaml — legacy/baseline study YAML (kept for
         backward compat with existing prod data).
       - daily.yaml          — daily_base diary
       - pre.yaml            — mid_study_w/q + post_study_w/q
       - endpoint.yaml       — study_endpoint
       - weekly_anytime.yaml — week1..week4_reflection + anytime_reflection
       - sotd.yaml           — daily SOTD instruments (empty placeholder
                               while content is authored)
       - mock_test_today.yaml — May 1-3 mock dailies (only with --mock-dailies)
  2. Seeds the 4-week study schedule (37 ScheduledSurvey rows from
     `0004_seed_study_schedule.seed_schedule`).
  3. Re-applies the W/Q biweekly schedule (`0011_schedule_wq_biweekly.
     seed_wq_biweekly`) — replaces the legacy `mid_study` / `post_study`
     biweekly rows with the version-suffixed pair.
  4. (Optional, `--mock-dailies`) Loads `mock_test_today.yaml` and creates
     the May 1-3 mock daily ScheduledSurvey rows.
  5. (Optional, `--include-demos --demo-email <email>`) Loads demo
     question-type surveys + populates them with mock responses + seeds a
     viewer response so each `/surveys/<slug>/results` page renders
     unlocked. Dev-only — never pass on production.

Idempotent on every step:
  - `load_surveys` is upsert-by-slug.
  - The two seed_* functions use `update_or_create` keyed on
    (cadence, sequence_index).
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

# Fixture files loaded in order. study_2026q2.yaml stays first for backward
# compat (its slugs are referenced by 0004's seed_schedule). The new
# long-form fixtures replace placeholder content for the same slugs and
# add new ones (mid_study_w/q, post_study_w/q, etc.).
LONG_FORM_FIXTURES = [
    'study_2026q2.yaml',
    'daily.yaml',
    'pre.yaml',
    'endpoint.yaml',
    'weekly_anytime.yaml',
    'sotd.yaml',
]

# May 1-3 mock daily slots — see mock_test_today.yaml for the matching Survey
# content. sequence_index 900-902 stays clear of the study schedule's 1..28.
MOCK_DAILY_SLOTS = [
    ('mock_test_2026q2',     date(2026, 5, 1), 900),
    ('mock_test_2026_05_02', date(2026, 5, 2), 901),
    ('mock_test_2026_05_03', date(2026, 5, 3), 902),
]


class Command(BaseCommand):
    help = (
        'Bring a freshly-migrated DB to a working survey state: load every '
        'long-form study YAML, seed the 4-week study schedule, re-apply the '
        'W/Q biweekly schedule, optionally load+schedule the May 1-3 mock '
        'dailies, and optionally seed demo surveys + mock responses for QA.'
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

        # 1. Load every long-form study YAML in dependency order.
        # On a fresh DB this seeds questions correctly via the loader's
        # "questions are replaced when survey is created" rule. On an
        # existing DB it ONLY updates survey-level fields — questions
        # are kept to protect existing SurveyAnswer rows (FK PROTECT).
        # To re-import revised question content on an existing DB, run
        # `load_surveys <file> --replace-questions` manually; that fails
        # with ProtectedError if any participant has already answered,
        # which is the safe behavior.
        self.stdout.write(self.style.NOTICE('[1] Loading long-form study fixtures ...'))
        for filename in LONG_FORM_FIXTURES:
            path = FIXTURES_DIR / filename
            if not path.exists():
                self.stdout.write(f'    skip (missing): {filename}')
                continue
            self.stdout.write(f'    {filename}')
            call_command('load_surveys', str(path))

        # 2. Seed the 4-week study schedule. The seed migration short-circuits
        #    on a fresh DB (no Survey rows yet), so we always re-run after
        #    step 1. Idempotent — `update_or_create` keyed on
        #    (cadence, sequence_index).
        self.stdout.write(self.style.NOTICE('[2] Seeding 4-week study schedule ...'))
        seed_module = import_module('surveys.migrations.0004_seed_study_schedule')
        seed_module.seed_schedule(django_apps, None)

        # 3. Re-apply the W/Q biweekly schedule. Replaces the legacy
        #    mid_study / post_study biweekly rows (created by step 2) with
        #    the version-suffixed pair (mid_study_w/q + post_study_w/q).
        #    Skips silently if the W/Q surveys aren't loaded yet.
        self.stdout.write(self.style.NOTICE('[3] Re-applying W/Q biweekly schedule ...'))
        wq_module = import_module('surveys.migrations.0011_schedule_wq_biweekly')
        wq_module.seed_wq_biweekly(django_apps, None)

        # 4. Re-seed the 20-row SOTD calendar. Slugs follow `sotd_dNN_*`
        #    convention; sequence_index = 100 + day_number. Skipped silently
        #    if no SOTD surveys exist yet (sotd.yaml empty / not loaded).
        self.stdout.write(self.style.NOTICE('[4] Re-seeding SOTD daily calendar ...'))
        sotd_module = import_module('surveys.migrations.0013_seed_sotd_schedule')
        sotd_module.seed_sotd_schedule(django_apps, None)

        # 4b. Apply the May-5 reschedule for sotd_d01_honeymoon. Step 4
        #    above runs 0013's pristine schedule (Day 1 = May 4), which
        #    would un-do the migration 0016 correction. Re-applying 0016
        #    here keeps every setup_survey_state run convergent on the
        #    intended state.
        self.stdout.write(
            self.style.NOTICE('[4b] Applying day-1 honeymoon reschedule (May 5) ...')
        )
        honeymoon_module = import_module(
            'surveys.migrations.0016_reschedule_d01_honeymoon_to_may_5'
        )
        honeymoon_module.reschedule_honeymoon(django_apps, None)

        # 5. Re-seed the persistent / editable evaluation surveys (feature_eval_w
        #    and goal_comparison_p1/p2). Endpoint cadence with no window_end —
        #    researchers manually close them at study end via Survey.closed.
        self.stdout.write(self.style.NOTICE('[5] Re-seeding persistent evaluation surveys ...'))
        persistent_module = import_module('surveys.migrations.0015_seed_persistent_eval_surveys')
        persistent_module.seed_persistent(django_apps, None)

        # 6. May 1-3 mock dailies (optional).
        if opts['mock_dailies']:
            mock_yaml = FIXTURES_DIR / 'mock_test_today.yaml'
            if not mock_yaml.exists():
                raise CommandError(f'Required fixture missing: {mock_yaml}')
            self.stdout.write(self.style.NOTICE(f'[6a] Loading {mock_yaml.name} ...'))
            call_command('load_surveys', str(mock_yaml))

            self.stdout.write(self.style.NOTICE('[6b] Scheduling May 1-3 mock dailies ...'))
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
            self.stdout.write(self.style.NOTICE('[6] Skipping mock dailies (no --mock-dailies)'))

        # 7. Demo surveys + mock responses (optional, dev-only).
        if opts['include_demos']:
            self.stdout.write(self.style.NOTICE('[7] Seeding demo question-type surveys ...'))
            call_command('seed_question_type_demos', email=opts['demo_email'])
        else:
            self.stdout.write(self.style.NOTICE('[7] Skipping demos (no --include-demos)'))

        self.stdout.write(self.style.SUCCESS(
            f'Done. Surveys={Survey.objects.count()} '
            f'ScheduledSurveys={ScheduledSurvey.objects.count()}'
        ))
