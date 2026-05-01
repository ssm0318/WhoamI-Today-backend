"""
Seed mock users + survey responses so privacy gates pass and the results page renders.

Usage:
    python manage.py seed_survey_mock_data --email you@example.com [--reset] \
        [--num-friends 8] [--num-close-friends 6] [--num-strangers 6] \
        [--today-slug example_week_check]

Idempotent on rerun: mock users keyed by username `mock_user_<n>`, connections deduped,
SurveyResponses skipped if already present for (user, survey).

With --reset: deletes the target user's SurveyResponses for all surveys (so they can
take the survey again from the Share tab).

With --today-slug: re-points today's daily ScheduledSurvey to the named slug
(creates a one-off daily ScheduledSurvey if none exists for today, e.g. outside
the study window).
"""
from __future__ import annotations

import random
from datetime import date as _date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from account.models import Connection
from surveys.models import (
    CADENCE_DAILY, ScheduledSurvey, Survey, SurveyAnswer, SurveyOption,
    SurveyResponse,
)


User = get_user_model()


def _ensure_connection(viewer, other, *, choice: str) -> None:
    """Create a Connection between viewer and other if absent. choice = 'friend' | 'close_friend'.
    Stored bilaterally: both user1_choice and user2_choice are set to `choice`.
    """
    if viewer.id < other.id:
        u1, u2 = viewer, other
    else:
        u1, u2 = other, viewer
    Connection.objects.get_or_create(
        user1=u1,
        user2=u2,
        defaults={'user1_choice': choice, 'user2_choice': choice},
    )


def _random_likert(rng: random.Random) -> int:
    return rng.randint(1, 5)


def _random_choice_value(rng: random.Random, values: list[int]) -> int:
    return rng.choice(values)


_FREE_TEXT_SAMPLES = [
    "feeling pretty good honestly",
    "tired but hanging in there",
    "kind of overwhelmed lately",
    "happy and grateful",
    "neutral, just another week",
    "stressed about work but otherwise fine",
    "really enjoying the small things",
    "missing my friends a lot",
    "anxious but trying to stay positive",
    "energetic and motivated",
]


def _seed_response(user, survey, rng: random.Random) -> None:
    if SurveyResponse.objects.filter(user=user, survey=survey).exists():
        return
    response = SurveyResponse.objects.create(user=user, survey=survey)
    for question in survey.questions.order_by('order'):
        # Dispatch on question.type (not survey-level type — types live per question now).
        qtype = question.type
        if qtype == 'likert_5':
            value = _random_likert(rng)
        elif qtype == 'single_choice':
            opts = list(question.options.values_list('value', flat=True))
            value = _random_choice_value(rng, opts) if opts else 0
        elif qtype == 'multi_choice':
            opts = list(question.options.values_list('value', flat=True))
            n_pick = rng.randint(1, max(1, len(opts)))
            value = rng.sample(opts, k=min(n_pick, len(opts))) if opts else []
        elif qtype == 'free_text':
            value = rng.choice(_FREE_TEXT_SAMPLES)
        elif qtype == 'slider':
            lo = question.slider_min_value if question.slider_min_value is not None else 0
            hi = question.slider_max_value if question.slider_max_value is not None else 100
            value = rng.randint(lo, hi)
        else:
            value = _random_likert(rng)
        SurveyAnswer.objects.create(response=response, question=question, value=value)


class Command(BaseCommand):
    help = 'Seed mock users and survey responses for local testing.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True, help='Email of the dev user (the one signed in).')
        parser.add_argument(
            '--num-friends', type=int, default=14,
            help='Total mock friends (must exceed close-friends by MIN_GROUP_DELTA=5 for the close-friends bucket to unlock).',
        )
        parser.add_argument('--num-close-friends', type=int, default=6, help='Mock close-friends count.')
        parser.add_argument('--num-strangers', type=int, default=6, help='Non-friend responders count.')
        parser.add_argument('--reset', action='store_true', help="Delete the dev user's responses first.")
        parser.add_argument('--today-slug', default=None, help="If set, re-point today's daily ScheduledSurvey here.")
        parser.add_argument('--seed', type=int, default=42, help='Random seed for deterministic output.')

    def handle(self, *args, **opts):
        rng = random.Random(opts['seed'])
        try:
            viewer = User.objects.get(email=opts['email'])
        except User.DoesNotExist:
            raise CommandError(f"No user with email {opts['email']!r}")

        with transaction.atomic():
            if opts['reset']:
                deleted, _ = SurveyResponse.objects.filter(user=viewer).delete()
                self.stdout.write(f'  reset: deleted {deleted} existing response rows for {viewer.username}')

            if opts['today_slug']:
                try:
                    target = Survey.objects.get(slug=opts['today_slug'])
                except Survey.DoesNotExist:
                    raise CommandError(f"No survey with slug {opts['today_slug']!r}")
                today = _date.today()
                # Re-point today's daily ScheduledSurvey row at the target survey.
                # The seed migration creates a daily ScheduledSurvey for every day
                # of the 4-week study; this just swaps the survey it points at.
                # Outside the study window (no row for today), create a one-off.
                ss = (
                    ScheduledSurvey.objects
                    .filter(cadence=CADENCE_DAILY, window_start=today)
                    .first()
                )
                if ss is None:
                    next_seq = (
                        ScheduledSurvey.objects.filter(cadence=CADENCE_DAILY)
                        .order_by('-sequence_index')
                        .values_list('sequence_index', flat=True)
                        .first()
                        or 0
                    ) + 1
                    ss = ScheduledSurvey.objects.create(
                        survey=target, cadence=CADENCE_DAILY,
                        window_start=today, window_end=today,
                        allow_late=False, sequence_index=next_seq,
                    )
                    action = 'created'
                else:
                    ss.survey = target
                    ss.save(update_fields=['survey', 'updated_at'])
                    action = 'updated'
                self.stdout.write(f'  today: {action} ScheduledSurvey({today}, daily) -> {target.slug}')

            # Provision mock users
            n_close = opts['num_close_friends']
            n_friend = opts['num_friends']  # close-friends count toward friend total
            n_stranger = opts['num_strangers']
            total = max(n_friend, n_close) + n_stranger
            mock_users: list[User] = []
            for i in range(total):
                username = f'mock_user_{i}'
                user, _created = User.objects.get_or_create(
                    username=username,
                    defaults={'email': f'{username}@example.com'},
                )
                mock_users.append(user)

            close_pool = mock_users[:n_close]
            friend_only_pool = mock_users[n_close:n_friend] if n_friend > n_close else []
            stranger_pool = mock_users[max(n_friend, n_close):]

            for u in close_pool:
                _ensure_connection(viewer, u, choice='close_friend')
            for u in friend_only_pool:
                _ensure_connection(viewer, u, choice='friend')

            self.stdout.write(
                f'  users: {n_close} close-friend + {len(friend_only_pool)} friend-only + '
                f'{len(stranger_pool)} stranger mocks'
            )

            # Seed responses for every active survey
            survey_slugs = list(Survey.objects.values_list('slug', flat=True))
            for slug in survey_slugs:
                survey = Survey.objects.get(slug=slug)
                count_before = SurveyResponse.objects.filter(survey=survey).count()
                for u in mock_users:
                    _seed_response(u, survey, rng)
                count_after = SurveyResponse.objects.filter(survey=survey).count()
                self.stdout.write(
                    f'  responses [{slug}]: {count_after - count_before} added '
                    f'({count_after} total)'
                )

        self.stdout.write(self.style.SUCCESS('seed_survey_mock_data complete.'))
