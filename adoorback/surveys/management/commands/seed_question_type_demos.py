"""Seed five demo surveys (one per question type) on past daily slots so a dev
can verify every input UI and every result renderer end-to-end.

Loads surveys/fixtures/demo_question_types.yaml, schedules each demo on a
past daily slot (today-1 .. today-5), seeds mock-user responses via
seed_survey_mock_data, and seeds a viewer response per demo so
/surveys/<slug>/results unlocks immediately for the dev user.

Usage:
    python manage.py seed_question_type_demos --email <your-dev-email>

Idempotent on re-run (load_surveys is upsert; ScheduledSurvey uses
update_or_create on (cadence, sequence_index); viewer response insert is
guarded by .exists()).
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from surveys.models import (
    CADENCE_DAILY, FREE_TEXT, LIKERT_5, MULTI_CHOICE, SINGLE_CHOICE, SLIDER,
    ScheduledSurvey, Survey, SurveyAnswer, SurveyResponse,
)


User = get_user_model()


DEMO_SLUGS = [
    'demo_likert',
    'demo_single_choice',
    'demo_multi_choice',
    'demo_free_text',
    'demo_slider',
]

# sequence_index range reserved for demos. Picked 1000+ to stay clear of the
# real study schedule (which uses 1..28 for daily, etc.).
DEMO_SEQUENCE_BASE = 1000

# Mock free-text answers — duplicated so the wordcloud's k-anonymity threshold
# (MIN_TOKEN_FREQUENCY = 3) clears for at least a few tokens.
_FREE_TEXT_SAMPLES = [
    'good',
    'tired',
    'meh',
    'productive',
    'overwhelmed',
    'happy',
    'stressed',
    'energetic',
    'calm',
    'okay honestly',
]


class Command(BaseCommand):
    help = (
        'Seed demo surveys (one per question type) on past daily slots + mock '
        'responses + viewer response so /surveys/<slug>/results renders.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--email', required=True,
            help="Dev user email — viewer gets responses too so results pages render without manual submission.",
        )
        parser.add_argument(
            '--seed', type=int, default=42,
            help='Random seed for deterministic mock answers.',
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        viewer_email = opts['email']
        try:
            viewer = User.objects.get(email=viewer_email)
        except User.DoesNotExist:
            raise CommandError(f'No user with email {viewer_email!r}')

        # 1. Load fixture (idempotent; re-runs upsert by slug).
        fixture_path = Path(__file__).resolve().parents[2] / 'fixtures' / 'demo_question_types.yaml'
        if not fixture_path.exists():
            raise CommandError(f'Demo fixture not found at {fixture_path}')
        self.stdout.write(f'Loading {fixture_path} ...')
        call_command('load_surveys', str(fixture_path), '--replace-questions')

        # 2. Schedule each demo on a past daily slot (today-1 backwards).
        today = date.today()
        for i, slug in enumerate(DEMO_SLUGS, start=1):
            schedule_date = today - timedelta(days=i)
            survey = Survey.objects.get(slug=slug)
            seq = DEMO_SEQUENCE_BASE + i
            ScheduledSurvey.objects.update_or_create(
                cadence=CADENCE_DAILY, sequence_index=seq,
                defaults={
                    'survey': survey,
                    'window_start': schedule_date,
                    'window_end': schedule_date,
                    'allow_late': False,
                },
            )
            self.stdout.write(f'  scheduled {slug} on {schedule_date} (seq={seq})')

        # 3. Seed mock users + responses across ALL surveys (covers demos too).
        self.stdout.write('Seeding mock users + responses via seed_survey_mock_data ...')
        call_command('seed_survey_mock_data', email=viewer_email, seed=opts['seed'])

        # 4. Seed a viewer response per demo so the dev user can hit
        #    /surveys/<slug>/results without first submitting through the UI.
        rng = random.Random(opts['seed'] + 1)  # different seed branch from mock-user seeding
        for slug in DEMO_SLUGS:
            survey = Survey.objects.get(slug=slug)
            if SurveyResponse.objects.filter(user=viewer, survey=survey).exists():
                self.stdout.write(f'  viewer already responded to {slug}, skipping')
                continue
            response = SurveyResponse.objects.create(user=viewer, survey=survey)
            for question in survey.questions.order_by('order'):
                value = self._mock_value(question, rng)
                SurveyAnswer.objects.create(response=response, question=question, value=value)
            self.stdout.write(f'  seeded viewer response for {slug}')

        self.stdout.write(self.style.SUCCESS(
            f'Done. Open /surveys/daily-archive (or /surveys/<slug>/results) as {viewer.username}.'
        ))

    @staticmethod
    def _mock_value(question, rng: random.Random):
        qtype = question.type
        if qtype == LIKERT_5:
            return rng.randint(1, 5)
        if qtype == SINGLE_CHOICE:
            opts = list(question.options.values_list('value', flat=True))
            return rng.choice(opts) if opts else 0
        if qtype == MULTI_CHOICE:
            opts = list(question.options.values_list('value', flat=True))
            if not opts:
                return []
            n_pick = rng.randint(1, len(opts))
            return rng.sample(opts, k=n_pick)
        if qtype == FREE_TEXT:
            return rng.choice(_FREE_TEXT_SAMPLES)
        if qtype == SLIDER:
            lo = question.slider_min_value if question.slider_min_value is not None else 0
            hi = question.slider_max_value if question.slider_max_value is not None else 100
            return rng.randint(lo, hi)
        return rng.randint(1, 5)  # safe fallback
