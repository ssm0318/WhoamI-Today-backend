# Shift the 4-week study schedule from May 3 → May 4 start.
#
# 0004 hardcodes STUDY_START = May 3 and seeds 37 ScheduledSurvey rows on
# that calendar. The kickoff date moved to May 4, so we add +1 day to every
# study row's window_start and window_end. Final dates after this migration:
#
#   - daily_base:           May  4 .. May 31  (28 days, sequence 1..28)
#   - week1_reflection:     May  4 .. May 10
#   - week2_reflection:     May 11 .. May 17
#   - week3_reflection:     May 18 .. May 24
#   - week4_reflection:     May 25 .. May 31
#   - pre_study:            May  3 (day before kickoff)
#   - mid_study_w/q:        May 17 (study day 14)
#   - post_study_w/q:       May 31 (study day 28)
#   - anytime_reflection:   May  4 .. May 31
#   - study_endpoint:       opens May 31, no upper bound
#
# Scope: ONLY the study-schedule slugs are shifted. Mock dailies (sequence
# 900-902, slugs `mock_test_*`) and demo schedule rows (sequence 1000+,
# slugs `demo_*`) are left in place — they're QA / dev fixtures with their
# own date semantics.
from datetime import timedelta

from django.db import migrations


# Slug whitelist for the study schedule. Daily rows reuse `daily_base`
# unless they're a special day (currently none — SPECIAL_DAILY_DAYS in 0004
# is empty). Weekly / biweekly / anytime / endpoint slugs are explicit.
STUDY_SLUGS = frozenset({
    'daily_base',
    'week1_reflection', 'week2_reflection', 'week3_reflection', 'week4_reflection',
    'pre_study',
    # W/Q-suffixed biweekly slugs land here after 0011 runs.
    'mid_study_w', 'mid_study_q',
    'post_study_w', 'post_study_q',
    # Plus the legacy slugs in case 0011 hasn't run yet on a particular DB.
    'mid_study', 'post_study',
    'anytime_reflection',
    'study_endpoint',
})

ONE_DAY = timedelta(days=1)


def shift_forward(apps, schema_editor):
    """Add 1 day to every study-schedule row's window dates."""
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    rows = ScheduledSurvey.objects.filter(survey__slug__in=STUDY_SLUGS)
    for row in rows:
        row.window_start = row.window_start + ONE_DAY
        if row.window_end is not None:
            row.window_end = row.window_end + ONE_DAY
        row.save(update_fields=['window_start', 'window_end'])


def shift_backward(apps, schema_editor):
    """Reverse: subtract 1 day from each study-schedule row."""
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    rows = ScheduledSurvey.objects.filter(survey__slug__in=STUDY_SLUGS)
    for row in rows:
        row.window_start = row.window_start - ONE_DAY
        if row.window_end is not None:
            row.window_end = row.window_end - ONE_DAY
        row.save(update_fields=['window_start', 'window_end'])


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0011_schedule_wq_biweekly'),
    ]

    operations = [
        migrations.RunPython(shift_forward, reverse_code=shift_backward),
    ]
