from datetime import date

from django.db import migrations


PHASE1_DUE = date(2026, 5, 18)
OLD_MID_STUDY_DUE = date(2026, 5, 17)

REFLECTION_TITLES = {
    'mid_study_w': 'Phase 1 reflection: Part 1',
    'mid_study_q': 'Phase 1 reflection: Part 1',
    'goal_comparison_p1': 'Phase 1 reflection: Part 2',
    'post_study_w': 'Phase 2 reflection: Part 1',
    'post_study_q': 'Phase 2 reflection: Part 1',
    'goal_comparison_p2': 'Phase 2 reflection: Part 2',
}
OLD_REFLECTION_TITLES = {
    'mid_study_w': ('Looking back: Phase 1', 0),
    'mid_study_q': ('Looking back: Phase 1', 0),
    'goal_comparison_p1': ('How did Phase 1 go?', 100),
    'post_study_w': ('Looking back: Phase 2', 0),
    'post_study_q': ('Looking back: Phase 2', 0),
    'goal_comparison_p2': ('How did Phase 2 go?', 100),
}


def apply_phase_reflection_parts(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')

    for slug, title in REFLECTION_TITLES.items():
        Survey.objects.filter(slug=slug).update(
            title=title,
            title_en=title,
            title_ko=title,
            priority=100,
        )

    for seq, slug in [(2, 'mid_study_w'), (3, 'mid_study_q')]:
        survey = Survey.objects.filter(slug=slug).first()
        if not survey:
            continue
        ScheduledSurvey.objects.update_or_create(
            cadence='biweekly',
            sequence_index=seq,
            defaults={
                'survey': survey,
                'window_start': PHASE1_DUE,
                'window_end': PHASE1_DUE,
                'allow_late': True,
            },
        )

    survey = Survey.objects.filter(slug='goal_comparison_p1').first()
    if survey:
        ScheduledSurvey.objects.update_or_create(
            cadence='endpoint',
            sequence_index=4,
            defaults={
                'survey': survey,
                'window_start': PHASE1_DUE,
                'window_end': PHASE1_DUE,
                'allow_late': True,
                'target_user_group': '',
            },
        )


def reverse_phase_reflection_parts(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')

    for slug, (title, priority) in OLD_REFLECTION_TITLES.items():
        Survey.objects.filter(slug=slug).update(
            title=title,
            title_en=title,
            title_ko='',
            priority=priority,
        )

    for seq, slug in [(2, 'mid_study_w'), (3, 'mid_study_q')]:
        survey = Survey.objects.filter(slug=slug).first()
        if not survey:
            continue
        ScheduledSurvey.objects.update_or_create(
            cadence='biweekly',
            sequence_index=seq,
            defaults={
                'survey': survey,
                'window_start': OLD_MID_STUDY_DUE,
                'window_end': OLD_MID_STUDY_DUE,
                'allow_late': True,
            },
        )

    survey = Survey.objects.filter(slug='goal_comparison_p1').first()
    if survey:
        ScheduledSurvey.objects.update_or_create(
            cadence='endpoint',
            sequence_index=4,
            defaults={
                'survey': survey,
                'window_start': PHASE1_DUE,
                'window_end': None,
                'allow_late': True,
                'target_user_group': '',
            },
        )


def apply_phase1_reflection_parts(apps, schema_editor):
    apply_phase_reflection_parts(apps, schema_editor)


def reverse_phase1_reflection_parts(apps, schema_editor):
    reverse_phase_reflection_parts(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0030_phase1_closeness_due_may18'),
    ]

    operations = [
        migrations.RunPython(
            apply_phase_reflection_parts,
            reverse_code=reverse_phase_reflection_parts,
        ),
    ]
