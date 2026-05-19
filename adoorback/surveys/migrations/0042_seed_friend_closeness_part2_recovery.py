from datetime import date

from django.db import migrations


PHASE1_FRIEND_CLOSENESS_PART2_START = date(2026, 5, 19)
PHASE1_FRIEND_CLOSENESS_PART2_DUE = date(2026, 5, 24)


def seed_friend_closeness_part2_recovery(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    survey = Survey.objects.filter(slug='phase1_friend_closeness_part2').first()
    if survey is None:
        return
    ScheduledSurvey.objects.update_or_create(
        cadence='endpoint',
        sequence_index=26,
        defaults={
            'survey': survey,
            'window_start': PHASE1_FRIEND_CLOSENESS_PART2_START,
            'window_end': PHASE1_FRIEND_CLOSENESS_PART2_DUE,
            'allow_late': True,
            'target_user_group': '',
            'sidebar_order': None,
        },
    )


def unseed_friend_closeness_part2_recovery(apps, schema_editor):
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    ScheduledSurvey.objects.filter(cadence='endpoint', sequence_index=26).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('surveys', '0041_feature_eval_w_copy_cleanup'),
    ]

    operations = [
        migrations.RunPython(
            seed_friend_closeness_part2_recovery,
            reverse_code=unseed_friend_closeness_part2_recovery,
        ),
    ]
