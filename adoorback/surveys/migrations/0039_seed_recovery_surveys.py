from datetime import date

from django.db import migrations


PHASE1_RECOVERY_START = date(2026, 5, 19)
PHASE1_RECOVERY_DUE = date(2026, 5, 24)
ENDPOINT_RECOVERY_START = date(2026, 5, 31)
PHASE2_RECOVERY_START = date(2026, 6, 1)
PHASE2_RECOVERY_DUE = date(2026, 6, 7)


# (sequence_index, survey_slug, window_start, window_end, allow_late, target_user_group)
RECOVERY_SCHEDULE = [
    (20, 'phase1_reflection_part3_w', PHASE1_RECOVERY_START, PHASE1_RECOVERY_DUE, True, 'group_w_first'),
    (21, 'phase1_reflection_part3_q', PHASE1_RECOVERY_START, PHASE1_RECOVERY_DUE, True, 'group_q_first'),
    (22, 'feature_eval_w_part2', PHASE1_RECOVERY_START, PHASE1_RECOVERY_DUE, True, ''),
    (23, 'study_endpoint_part2', ENDPOINT_RECOVERY_START, None, True, ''),
    (24, 'phase2_reflection_part3_w', PHASE2_RECOVERY_START, PHASE2_RECOVERY_DUE, True, 'group_w_first'),
    (25, 'phase2_reflection_part3_q', PHASE2_RECOVERY_START, PHASE2_RECOVERY_DUE, True, 'group_q_first'),
]


def seed_recovery_surveys(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    if not Survey.objects.exists():
        return

    for seq, slug, start, end, allow_late, target_group in RECOVERY_SCHEDULE:
        survey = Survey.objects.filter(slug=slug).first()
        if survey is None:
            continue
        ScheduledSurvey.objects.update_or_create(
            cadence='endpoint',
            sequence_index=seq,
            defaults={
                'survey': survey,
                'window_start': start,
                'window_end': end,
                'allow_late': allow_late,
                'target_user_group': target_group,
                'sidebar_order': None,
            },
        )


def unseed_recovery_surveys(apps, schema_editor):
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    ScheduledSurvey.objects.filter(
        cadence='endpoint',
        sequence_index__in=[row[0] for row in RECOVERY_SCHEDULE],
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('surveys', '0038_feature_eval_w_followups_no_na'),
    ]

    operations = [
        migrations.RunPython(seed_recovery_surveys, reverse_code=unseed_recovery_surveys),
    ]
