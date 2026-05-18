# 4-week study schedule seed.
#
# Creates the 37 ScheduledSurvey rows for the cohort-wide May 2026 study:
#   - 28 daily   (one per study day, May 3 → May 30; allow_late=False)
#   - 4 weekly   (one per study week, allow_late=True)
#   - 3 biweekly (pre / mid / post study, allow_late=True)
#   - 1 anytime  (full 28-day window, allow_late=True)
#   - 1 endpoint (opens day 28, no upper bound)
#
# Idempotent via update_or_create keyed on (cadence, sequence_index). Re-running
# the seed updates dates in place rather than duplicating rows. Django won't
# re-run an already-applied migration; to adjust dates after deploy, create a
# follow-up migration that imports and calls `seed_schedule` from this module
# with updated date constants.
#
# Required Survey slugs (must exist in DB before this migration runs — see
# `surveys/fixtures/study_2026q2.yaml` and `python manage.py load_surveys`):
#   daily_base, dayN_special (only for N ∈ SPECIAL_DAILY_DAYS),
#   week1_reflection..week4_reflection,
#   pre_study, mid_study, post_study,
#   anytime_reflection, study_endpoint
#
# The migration aborts with a clear error if any required slug is missing.
from datetime import date, timedelta

from django.db import migrations


# Study calendar (locked).
# Originally May 3 kickoff; shifted to May 4 in 0012. The constants below
# reflect the post-shift calendar so that fresh DBs and any re-runs of
# `seed_schedule` (e.g. via setup_survey_state) produce the canonical
# May 4-based dates directly. 0012's forward operation is now a no-op
# because the source-of-truth is here.
PRE_STUDY = date(2026, 5, 3)    # Pre-study survey lives the day before the 28-day period.
STUDY_START = date(2026, 5, 4)  # Day 1.
STUDY_END = date(2026, 5, 31)   # Day 28 = STUDY_START + 27 days.


def _day(n):
    """1-indexed study day. _day(1) = May 4, _day(14) = May 17, _day(28) = May 31."""
    return STUDY_START + timedelta(days=n - 1)


# Days in the 28-day period that have unique daily surveys instead of `daily_base`.
# Empty set = all 28 days reuse `daily_base`. Authoring a `dayN_special` survey
# requires adding a Survey row with slug `dayN_special` to the YAML fixture.
SPECIAL_DAILY_DAYS: set = set()


def _daily_slug(day_n: int) -> str:
    return f'day{day_n}_special' if day_n in SPECIAL_DAILY_DAYS else 'daily_base'


# (cadence, sequence_index, survey_slug, window_start, window_end, allow_late)
SCHEDULE = (
    # Daily — 28 entries, days 1..28 = May 3..May 30. allow_late=False.
    [('daily', n, _daily_slug(n), _day(n), _day(n), False) for n in range(1, 29)]

    # Weekly — 4 entries, one per study week (7-day window). allow_late=True.
    + [
        ('weekly', 1, 'week1_reflection', _day(1),  _day(7),  True),   # May 3–9
        ('weekly', 2, 'week2_reflection', _day(8),  _day(14), True),   # May 10–16
        ('weekly', 3, 'week3_reflection', _day(15), _day(21), True),   # May 17–23
        ('weekly', 4, 'week4_reflection', _day(22), _day(28), True),   # May 24–30
    ]

    # Biweekly — pre (day 0, May 2), mid (day 14, May 16), post (day 28, May 30).
    # allow_late=True so missed pre/mid/post stay answerable indefinitely.
    + [
        ('biweekly', 1, 'pre_study',  PRE_STUDY, PRE_STUDY, True),
        ('biweekly', 2, 'mid_study',  _day(14),  _day(14),  True),
        ('biweekly', 3, 'post_study', _day(28),  _day(28),  True),
    ]

    # Anytime — single survey, the full 28-day window.
    + [('anytime', 1, 'anytime_reflection', _day(1), _day(28), True)]

    # Endpoint — opens day 28 (May 30), no upper bound. Coexists with biweekly
    # post_study on May 30 — they are intentionally distinct surveys.
    + [('endpoint', 1, 'study_endpoint', _day(28), None, True)]
)


# Legacy biweekly slugs that downstream migrations have since retired or
# replaced — pre_study by 0022, mid_study + post_study by 0011's
# W/Q-variant rewrite. setup_survey_state.py re-invokes seed_schedule as
# a runtime helper, and after the original study_2026q2.yaml fixture was
# archived these slugs no longer exist in the DB. Skip them quietly when
# missing instead of crashing — the post-replacement rows are recreated
# by the seed_wq_biweekly / retire_pre_study steps that follow.
LEGACY_REPLACED_SLUGS = frozenset({'pre_study', 'mid_study', 'post_study'})


def seed_schedule(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')

    # Fresh dev / test DB with no surveys yet: skip cleanly. Production deploys
    # must run `python manage.py load_surveys` for the active fixtures before
    # applying this migration. The migration still aborts if some surveys
    # exist but a required non-legacy slug does not — so an incomplete YAML
    # load surfaces immediately.
    if not Survey.objects.exists():
        return

    for cadence, seq, slug, window_start, window_end, allow_late in SCHEDULE:
        try:
            survey = Survey.objects.get(slug=slug)
        except Survey.DoesNotExist:
            if slug in LEGACY_REPLACED_SLUGS:
                continue
            raise RuntimeError(
                f'Survey with slug={slug!r} not found. Author it in the '
                'appropriate fixture under surveys/fixtures/ and run '
                '`python manage.py load_surveys <path>` before applying this migration.'
            )
        ScheduledSurvey.objects.update_or_create(
            cadence=cadence,
            sequence_index=seq,
            defaults={
                'survey': survey,
                'window_start': window_start,
                'window_end': window_end,
                'allow_late': allow_late,
            },
        )


def unseed_schedule(apps, schema_editor):
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    for cadence, seq, *_ in SCHEDULE:
        ScheduledSurvey.objects.filter(cadence=cadence, sequence_index=seq).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0003_scheduledsurvey_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_schedule, reverse_code=unseed_schedule),
    ]
