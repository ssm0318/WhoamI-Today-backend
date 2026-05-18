from datetime import date

from django.db import migrations


PHASE1_DUE = date(2026, 5, 18)
OLD_PHASE1_DUE = date(2026, 5, 17)


def forward(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    try:
        survey = Survey.objects.get(slug='phase1_friend_closeness')
    except Survey.DoesNotExist:
        return
    ScheduledSurvey.objects.update_or_create(
        cadence='biweekly',
        sequence_index=6,
        defaults={
            'survey': survey,
            'window_start': PHASE1_DUE,
            'window_end': PHASE1_DUE,
            'allow_late': True,
        },
    )


def reverse(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    try:
        survey = Survey.objects.get(slug='phase1_friend_closeness')
    except Survey.DoesNotExist:
        return
    ScheduledSurvey.objects.update_or_create(
        cadence='biweekly',
        sequence_index=6,
        defaults={
            'survey': survey,
            'window_start': OLD_PHASE1_DUE,
            'window_end': OLD_PHASE1_DUE,
            'allow_late': True,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0029_clean_participant_facing_copy'),
    ]

    operations = [
        migrations.RunPython(forward, reverse_code=reverse),
    ]
