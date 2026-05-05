# Move each weekly reflection to open at the END of its week instead of
# the start. The original schedule (from 0004) had week1 covering Days
# 1-7 (May 4 - May 10), but "looking back on the past week" doesn't make
# sense before the user has spent any time using WIT — there's nothing
# to reflect on yet.
#
# New schedule: open on Day 7 (Sat) of each week, run for 7 days. The
# allow_late=True flag carries over so it lingers in late_but_accepted
# after window_end if the user misses the prompt.
#
#   week1_reflection: 2026-05-04..05-10  →  2026-05-10..05-16
#   week2_reflection: 2026-05-11..05-17  →  2026-05-17..05-23
#   week3_reflection: 2026-05-18..05-24  →  2026-05-24..05-30
#   week4_reflection: 2026-05-25..05-31  →  2026-05-31..06-06
#
# Sequence_index (1..4) is the upsert key — same as 0004's seed.
from datetime import date

from django.db import migrations


# (sequence_index, slug, new_window_start, new_window_end)
NEW_WEEKLY_SCHEDULE = [
    (1, 'week1_reflection', date(2026, 5, 10), date(2026, 5, 16)),
    (2, 'week2_reflection', date(2026, 5, 17), date(2026, 5, 23)),
    (3, 'week3_reflection', date(2026, 5, 24), date(2026, 5, 30)),
    (4, 'week4_reflection', date(2026, 5, 31), date(2026, 6, 6)),
]

# Original windows for the reverse migration.
ORIGINAL_WEEKLY_SCHEDULE = [
    (1, 'week1_reflection', date(2026, 5, 4),  date(2026, 5, 10)),
    (2, 'week2_reflection', date(2026, 5, 11), date(2026, 5, 17)),
    (3, 'week3_reflection', date(2026, 5, 18), date(2026, 5, 24)),
    (4, 'week4_reflection', date(2026, 5, 25), date(2026, 5, 31)),
]


def shift_weekly_reflections(apps, schema_editor):
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    for seq, _slug, ws, we in NEW_WEEKLY_SCHEDULE:
        ScheduledSurvey.objects.filter(
            cadence='weekly', sequence_index=seq,
        ).update(window_start=ws, window_end=we)


def revert_weekly_reflections(apps, schema_editor):
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    for seq, _slug, ws, we in ORIGINAL_WEEKLY_SCHEDULE:
        ScheduledSurvey.objects.filter(
            cadence='weekly', sequence_index=seq,
        ).update(window_start=ws, window_end=we)


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0016_reschedule_d01_honeymoon_to_may_5'),
    ]

    operations = [
        migrations.RunPython(shift_weekly_reflections, reverse_code=revert_weekly_reflections),
    ]
