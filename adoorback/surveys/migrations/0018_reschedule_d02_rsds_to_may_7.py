# Reschedule sotd_d02_rsds from May 5 to May 7.
#
# May 5 was already double-booked with sotd_d01_honeymoon (rescheduled
# from missed May 4 in 0016). Rather than make participants slog through
# 14 likert items in a single day, slip RSDS forward by 2 days to land
# alongside sotd_d04_iscs_bridge on May 7 — same co-schedule pattern as
# the May 5 d01+d02 arrangement, and auto-chaining (frontend) handles
# the UX.
#
# Sequence index stays at 102 (lower than d04's 104), so RSDS wins the
# featured Survey-of-the-Day card on May 7 and ISCS-bridge lands one
# row down in available_now.
from datetime import date

from django.db import migrations


RSDS_SLUG = 'sotd_d02_rsds'
RSDS_SEQ = 102  # 100 + day_number per 0013's convention
NEW_WINDOW = date(2026, 5, 7)
ORIGINAL_WINDOW = date(2026, 5, 5)


def reschedule_rsds(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')

    if not Survey.objects.filter(slug=RSDS_SLUG).exists():
        return

    ScheduledSurvey.objects.filter(
        cadence='daily', sequence_index=RSDS_SEQ,
    ).update(
        window_start=NEW_WINDOW,
        window_end=NEW_WINDOW,
    )


def revert_rsds(apps, schema_editor):
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    ScheduledSurvey.objects.filter(
        cadence='daily', sequence_index=RSDS_SEQ,
    ).update(
        window_start=ORIGINAL_WINDOW,
        window_end=ORIGINAL_WINDOW,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0017_shift_weekly_reflections_to_end_of_week'),
    ]

    operations = [
        migrations.RunPython(reschedule_rsds, reverse_code=revert_rsds),
    ]
