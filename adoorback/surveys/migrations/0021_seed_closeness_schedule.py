# Schedule the end-of-phase per-friend closeness re-rating surveys.
#
# phase1_friend_closeness opens on Day 15 (May 18), phase2_friend_closeness
# opens on Day 28 (May 31). Both have `allow_late=True` so the slot stays
# completable through end-of-study — important because the surveys were
# specced on Day 15 and should remain answerable after the due date.
#
# Sequence indices 4 and 5 are taken by post_study_w / post_study_q from
# 0011 (the spec was authored before that migration's expansion). We pick
# 6 and 7 to stay clear of the existing biweekly rows (1=pre_study,
# 2=mid_study_w, 3=mid_study_q, 4=post_study_w, 5=post_study_q).
#
# Idempotent: update_or_create on (cadence, sequence_index). Short-circuits
# if the surveys aren't loaded yet (matching the 0011 pattern), so a fresh
# DB will get scheduled rows after load_surveys runs.
from datetime import date

from django.db import migrations


PHASE1_DUE = date(2026, 5, 18)
DAY_28 = date(2026, 5, 31)


CLOSENESS_SCHEDULE = [
    (6, 'phase1_friend_closeness', PHASE1_DUE),
    (7, 'phase2_friend_closeness', DAY_28),
]


def seed_closeness(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    if not Survey.objects.exists():
        return
    for seq, slug, day in CLOSENESS_SCHEDULE:
        try:
            survey = Survey.objects.get(slug=slug)
        except Survey.DoesNotExist:
            # YAML not loaded yet - next setup_survey_state run will retry.
            continue
        ScheduledSurvey.objects.update_or_create(
            cadence='biweekly', sequence_index=seq,
            defaults={
                'survey': survey,
                'window_start': day,
                'window_end': day,
                'allow_late': True,
            },
        )


def unseed_closeness(apps, schema_editor):
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    ScheduledSurvey.objects.filter(
        cadence='biweekly',
        sequence_index__in=[s for s, *_ in CLOSENESS_SCHEDULE],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0020_per_friend_question_types'),
    ]

    operations = [
        migrations.RunPython(seed_closeness, reverse_code=unseed_closeness),
    ]
