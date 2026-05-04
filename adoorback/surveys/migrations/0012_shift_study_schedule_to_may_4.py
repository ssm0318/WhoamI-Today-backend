# Originally shifted the study schedule from May 3 → May 4 by adding +1
# day to every study-row's window dates. The shift is now baked into
# 0004 + 0011's constants directly (May 4 kickoff is the source of truth),
# so this migration is a NO-OP forward.
#
# History:
#   - Pre-this-commit: 0012 unconditionally added +1 day. On already-
#     migrated DBs, dates were correctly shifted to May 4-based.
#   - This commit: 0004 + 0011's constants now produce May 4-based dates
#     directly. Re-running their seed functions (setup_survey_state) no
#     longer un-shifts the calendar.
#   - 0012's forward = no-op (already-applied prod DBs stay at May 4
#     dates because 0004 + 0011 now confirm those dates on every re-seed).
#   - 0012's reverse = subtract 1 day, so a teardown to pre-0012 state
#     remains possible. Useful for running tests that exercise the
#     pre-shift path, or for debugging prod migration history.
from datetime import timedelta

from django.db import migrations


STUDY_SLUGS = frozenset({
    'daily_base',
    'week1_reflection', 'week2_reflection', 'week3_reflection', 'week4_reflection',
    'pre_study',
    'mid_study_w', 'mid_study_q',
    'post_study_w', 'post_study_q',
    'mid_study', 'post_study',  # legacy slugs from before 0011 split
    'anytime_reflection',
    'study_endpoint',
})

ONE_DAY = timedelta(days=1)


def shift_forward(apps, schema_editor):
    """No-op. May 4 calendar is now the source of truth in 0004 + 0011."""


def shift_backward(apps, schema_editor):
    """Subtract 1 day from every study-schedule row.

    Provided so a full migrate-backwards through 0012 returns the schedule
    to the pre-shift May 3-based dates. Combined with 0004 + 0011's
    forward seeds (which now produce May 4-based dates), this means the
    chain `migrate forward → migrate backward → migrate forward` works
    correctly: the second forward apply ends up at May 4 dates because
    0004's constants drive it.
    """
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
