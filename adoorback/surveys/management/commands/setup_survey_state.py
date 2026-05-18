"""One-shot setup of the survey app's runtime state.

Brings a freshly-migrated DB to a working state for the long-form study:

  1. Loads every survey fixture in `surveys/fixtures/`. Order matters
     because some fixtures depend on others' anchors:
       - daily.yaml          — daily_base diary
       - pre.yaml            — mid_study_w/q + post_study_w/q
       - endpoint.yaml       — study_endpoint
       - weekly_anytime.yaml — week1..week4_reflection + anytime_reflection
       - sotd.yaml           — daily SOTD instruments
       - closeness_reeval.yaml — phase1/phase2 per-friend closeness re-rating
       - pre_study_catchup.yaml — habit_platform catch-up (mid-study add)
       - _archive/mock_test_today.yaml — May 1-3 mock dailies (only with --mock-dailies)
  2. Seeds the 4-week study schedule (37 ScheduledSurvey rows from
     `0004_seed_study_schedule.seed_schedule`).
  3. Re-applies the W/Q biweekly schedule (`0011_schedule_wq_biweekly.
     seed_wq_biweekly`) — replaces the legacy `mid_study` / `post_study`
     biweekly rows with the version-suffixed pair.
  4. Retires the removed `pre_study` survey so it is not re-created by
     the legacy seed schedule.
  5. Applies schedule overrides: pre-study catch-up, SOTD reschedules,
     SOTD late-answer rules,
     and weekend-only weekly reflections.
  6. (Optional, `--mock-dailies`) Loads `mock_test_today.yaml` and creates
     the May 1-3 mock daily ScheduledSurvey rows.
  7. (Optional, `--include-demos --demo-email <email>`) Loads demo
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

# Fixture files loaded in order. Earlier study_2026q2.yaml lived at the
# top of this list as a baseline placeholder; it has since been archived
# (surveys/fixtures/_archive/) and its surviving slugs (daily_base,
# study_endpoint) are authored in their dedicated fixtures below. The
# legacy slugs pre_study / mid_study / post_study are referenced by
# 0004's SCHEDULE but seed_schedule now skips them when missing — see
# LEGACY_REPLACED_SLUGS in 0004_seed_study_schedule.py.
LONG_FORM_FIXTURES = [
    'daily.yaml',
    'pre.yaml',
    'endpoint.yaml',
    'weekly_anytime.yaml',
    'sotd.yaml',
    'closeness_reeval.yaml',
    'pre_study_catchup.yaml',
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

        # 3b. Remove the retired pre-study survey after the legacy schedule
        #    seeders have had a chance to re-create it. Existing responses are
        #    preserved by closing the survey; fresh/dev DBs delete it entirely.
        self.stdout.write(self.style.NOTICE('[3b] Retiring pre-study survey ...'))
        retire_pre_study_module = import_module('surveys.migrations.0022_retire_pre_study')
        retire_pre_study_module.retire_pre_study(django_apps, None)

        # 3c. Re-seed the catch-up prerequisite for the SHI SOTD. The
        #    migration can short-circuit on fresh DBs before YAML has been
        #    loaded, so setup_survey_state reapplies it after fixtures.
        self.stdout.write(
            self.style.NOTICE('[3c] Re-seeding pre-study catch-up prerequisite ...')
        )
        catchup_module = import_module(
            'surveys.migrations.0024_seed_pre_study_catchup_schedule'
        )
        catchup_module.seed_catchup(django_apps, None)

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

        # 4c. Re-apply migration 0017's weekly schedule shift. Step 2
        #    above runs 0004's pristine schedule which puts week1
        #    starting on Day 1 (May 4) — but week1 is "looking back on
        #    the past week" and shouldn't be visible until Day 7 (May 10)
        #    when there's actually a past week to reflect on. Without
        #    this step, every setup_survey_state run silently re-exposes
        #    week1 from Day 1.
        self.stdout.write(
            self.style.NOTICE('[4c] Shifting weekly reflections to end-of-week ...')
        )
        weekly_module = import_module(
            'surveys.migrations.0017_shift_weekly_reflections_to_end_of_week'
        )
        weekly_module.shift_weekly_reflections(django_apps, None)

        # 4c2. Narrow weekly reflections to the weekend-only windows and
        #    prune the instrument to the three retained weekly questions.
        #    This runs after 0017 because setup_survey_state deliberately
        #    replays historical seeders in order, then converges via the
        #    latest overlays.
        self.stdout.write(
            self.style.NOTICE('[4c2] Applying weekend-only weekly reflections ...')
        )
        weekend_weekly_module = import_module(
            'surveys.migrations.0023_weekly_reflections_weekend_only'
        )
        weekend_weekly_module.apply_weekend_weekly_reflections(django_apps, None)

        # 4d. Apply the May-7 reschedule for sotd_d02_rsds. May 5 was
        #    already double-booked with d01_honeymoon; pushing RSDS to
        #    May 7 (alongside sotd_d04_iscs_bridge) spreads load and
        #    leverages the auto-chain UX.
        self.stdout.write(
            self.style.NOTICE('[4d] Applying day-2 RSDS reschedule (May 7) ...')
        )
        rsds_module = import_module(
            'surveys.migrations.0018_reschedule_d02_rsds_to_may_7'
        )
        rsds_module.reschedule_rsds(django_apps, None)

        # 4e. Re-apply the late-answer rule for trait-level SOTDs. Step 4
        #    replays 0013's original SOTD schedule with allow_late=False;
        #    0019 corrected that for SOTD instruments while keeping
        #    daily_base state diaries expiring at end-of-day.
        self.stdout.write(
            self.style.NOTICE('[4e] Applying SOTD late-answer rules ...')
        )
        sotd_late_module = import_module('surveys.migrations.0019_sotd_allow_late_true')
        sotd_late_module.forward(django_apps, None)

        # 5. Re-seed the persistent / editable evaluation surveys (feature_eval_w
        #    and goal_comparison_p1/p2). Endpoint cadence with no window_end —
        #    researchers manually close them at study end via Survey.closed.
        self.stdout.write(self.style.NOTICE('[5] Re-seeding persistent evaluation surveys ...'))
        persistent_module = import_module('surveys.migrations.0015_seed_persistent_eval_surveys')
        persistent_module.seed_persistent(django_apps, None)

        # 6. May 1-3 mock dailies (optional).
        if opts['mock_dailies']:
            mock_yaml = FIXTURES_DIR / '_archive' / 'mock_test_today.yaml'
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
