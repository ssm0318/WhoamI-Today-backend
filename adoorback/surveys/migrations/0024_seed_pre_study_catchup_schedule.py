# Schedule the habit_platform survey so it surfaces in the surveys
# index as available_now. The window opens today (the day this ships)
# and stays open through end-of-study via allow_late=True; the priority
# field (set in the YAML at 110) bumps it ahead of the SOTD card so the
# habit_platform prereq lands first.
#
# Sequence indices 1-7 on biweekly cadence are taken by pre_study,
# mid_study_w/q, post_study_w/q, and the phase1/phase2 closeness re-rating
# surveys. seq=8 is the next available slot.
#
# Idempotent — update_or_create on (cadence, sequence_index).
from datetime import date

from django.db import migrations


SHIP_DATE = date(2026, 5, 18)
# Window stays open through the end of the study window.
STUDY_END = date(2026, 5, 31)
HABIT_PLATFORM_SLUG = 'habit_platform'


def seed_catchup(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    if not Survey.objects.exists():
        return
    try:
        survey = Survey.objects.get(slug=HABIT_PLATFORM_SLUG)
    except Survey.DoesNotExist:
        # YAML not loaded yet; setup_survey_state retries this on next run.
        return
    ScheduledSurvey.objects.update_or_create(
        cadence='biweekly', sequence_index=8,
        defaults={
            'survey': survey,
            'window_start': SHIP_DATE,
            'window_end': STUDY_END,
            'allow_late': True,
        },
    )


def unseed_catchup(apps, schema_editor):
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    ScheduledSurvey.objects.filter(
        cadence='biweekly', sequence_index=8,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0023_weekly_reflections_weekend_only'),
    ]

    operations = [
        migrations.RunPython(seed_catchup, reverse_code=unseed_catchup),
    ]
