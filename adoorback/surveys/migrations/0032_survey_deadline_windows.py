from datetime import date

from django.db import migrations


PHASE1_DUE = date(2026, 5, 18)
PHASE2_DUE = date(2026, 5, 31)
FEATURE_W_FIRST_START = date(2026, 5, 8)
FEATURE_Q_FIRST_START = date(2026, 5, 22)
HABIT_PLATFORM_DAILY_SEQ = 915
OLD_HABIT_PLATFORM_BIWEEKLY_SEQ = 8


def apply_deadline_windows(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')

    ScheduledSurvey.objects.filter(
        cadence='biweekly',
        sequence_index=OLD_HABIT_PLATFORM_BIWEEKLY_SEQ,
        survey__slug='habit_platform',
    ).delete()

    habit = Survey.objects.filter(slug='habit_platform').first()
    if habit:
        ScheduledSurvey.objects.update_or_create(
            cadence='daily',
            sequence_index=HABIT_PLATFORM_DAILY_SEQ,
            defaults={
                'survey': habit,
                'window_start': PHASE1_DUE,
                'window_end': PHASE1_DUE,
                'allow_late': True,
                'target_user_group': '',
            },
        )

    feature = Survey.objects.filter(slug='feature_eval_w').first()
    if feature:
        for seq, window_start, window_end, target_group in [
            (2, FEATURE_W_FIRST_START, PHASE1_DUE, 'group_w_first'),
            (3, FEATURE_Q_FIRST_START, PHASE2_DUE, 'group_q_first'),
        ]:
            ScheduledSurvey.objects.update_or_create(
                cadence='endpoint',
                sequence_index=seq,
                defaults={
                    'survey': feature,
                    'window_start': window_start,
                    'window_end': window_end,
                    'allow_late': True,
                    'target_user_group': target_group,
                },
            )


def reverse_deadline_windows(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')

    ScheduledSurvey.objects.filter(
        cadence='daily',
        sequence_index=HABIT_PLATFORM_DAILY_SEQ,
        survey__slug='habit_platform',
    ).delete()

    habit = Survey.objects.filter(slug='habit_platform').first()
    if habit:
        ScheduledSurvey.objects.update_or_create(
            cadence='biweekly',
            sequence_index=OLD_HABIT_PLATFORM_BIWEEKLY_SEQ,
            defaults={
                'survey': habit,
                'window_start': PHASE1_DUE,
                'window_end': PHASE2_DUE,
                'allow_late': True,
                'target_user_group': '',
            },
        )

    feature = Survey.objects.filter(slug='feature_eval_w').first()
    if feature:
        for seq, window_start, target_group in [
            (2, FEATURE_W_FIRST_START, 'group_w_first'),
            (3, FEATURE_Q_FIRST_START, 'group_q_first'),
        ]:
            ScheduledSurvey.objects.update_or_create(
                cadence='endpoint',
                sequence_index=seq,
                defaults={
                    'survey': feature,
                    'window_start': window_start,
                    'window_end': None,
                    'allow_late': True,
                    'target_user_group': target_group,
                },
            )


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0031_phase1_reflection_parts_due_may18'),
    ]

    operations = [
        migrations.RunPython(
            apply_deadline_windows,
            reverse_code=reverse_deadline_windows,
        ),
    ]
