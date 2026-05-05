# Reschedule sotd_d01_honeymoon from May 4 to May 5.
#
# The Day 1 honeymoon SOTD missed its original May 4 administration
# (deploy slipped). With `allow_late=False`, the row would have stayed
# expired-and-hidden through the rest of the study — never collected.
#
# We co-schedule it with the existing May 5 SOTD (sotd_d02_rsds) rather
# than picking the shortest day's slot: the honeymoon scale is a baseline
# measure of early-study state, and any further delay (e.g. moving it to
# Day 11 or Day 26) would invalidate the construct entirely. One day late
# preserves temporal validity at the cost of ~4 extra Likert items.
#
# Sequence index stays at 101 — lower than sotd_d02_rsds at 102 — so
# `get_today_daily` still picks the honeymoon as the featured Survey of
# the Day on May 5. RSDS lands one row down in the available_now bucket
# (still answerable that day, since both have window_end=May 5 and the
# user can hit /surveys/sotd_d02_rsds/answer directly from the index).
from datetime import date

from django.db import migrations


# (cadence, sequence_index) is the upsert key that 0013 used; reuse it.
HONEYMOON_SLUG = 'sotd_d01_honeymoon'
HONEYMOON_SEQ = 101  # 100 + day_number from 0013's convention
NEW_WINDOW = date(2026, 5, 5)
ORIGINAL_WINDOW = date(2026, 5, 4)


def reschedule_honeymoon(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')

    # Survey row must exist. If sotd.yaml hasn't been loaded yet
    # (fresh DB before setup_survey_state), short-circuit silently —
    # the next run picks it up just like 0013.
    if not Survey.objects.filter(slug=HONEYMOON_SLUG).exists():
        return

    ScheduledSurvey.objects.filter(
        cadence='daily', sequence_index=HONEYMOON_SEQ,
    ).update(
        window_start=NEW_WINDOW,
        window_end=NEW_WINDOW,
    )


def revert_honeymoon(apps, schema_editor):
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    ScheduledSurvey.objects.filter(
        cadence='daily', sequence_index=HONEYMOON_SEQ,
    ).update(
        window_start=ORIGINAL_WINDOW,
        window_end=ORIGINAL_WINDOW,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0015_seed_persistent_eval_surveys'),
    ]

    operations = [
        migrations.RunPython(reschedule_honeymoon, reverse_code=revert_honeymoon),
    ]
