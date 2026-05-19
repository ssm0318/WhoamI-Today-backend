from datetime import date

from django.db import migrations


PHASE1_DUE = date(2026, 5, 18)
PHASE1_PART2_DUE = date(2026, 5, 19)
PHASE2_DUE = date(2026, 5, 31)
FEATURE_W_FIRST_START = date(2026, 5, 8)
FEATURE_Q_FIRST_START = date(2026, 5, 22)
FEATURE_DUE_WEEKEND = date(2026, 5, 24)
ANYTIME_START = date(2026, 5, 4)

REFLECTION_TITLES = {
    'mid_study_w': 'Phase 1 reflection: Part 2',
    'mid_study_q': 'Phase 1 reflection: Part 2',
    'goal_comparison_p1': 'Phase 1 reflection: Part 1',
    'post_study_w': 'Phase 2 reflection: Part 2',
    'post_study_q': 'Phase 2 reflection: Part 2',
    'goal_comparison_p2': 'Phase 2 reflection: Part 1',
}

OLD_REFLECTION_TITLES = {
    'mid_study_w': 'Phase 1 reflection: Part 1',
    'mid_study_q': 'Phase 1 reflection: Part 1',
    'goal_comparison_p1': 'Phase 1 reflection: Part 2',
    'post_study_w': 'Phase 2 reflection: Part 1',
    'post_study_q': 'Phase 2 reflection: Part 1',
    'goal_comparison_p2': 'Phase 2 reflection: Part 2',
}

SIDEBAR_ORDER = {
    ('biweekly', 6): 1,
    ('endpoint', 4): 2,
    ('biweekly', 2): 3,
    ('biweekly', 3): 3,
    ('endpoint', 2): 4,
    ('endpoint', 3): 4,
}


def _set_title(survey, title):
    survey.title = title
    survey.title_en = title
    survey.title_ko = title
    survey.priority = 100
    survey.save(update_fields=['title', 'title_en', 'title_ko', 'priority'])


def apply_priority_order_and_windows(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')

    for slug, title in REFLECTION_TITLES.items():
        survey = Survey.objects.filter(slug=slug).first()
        if survey:
            _set_title(survey, title)

    Survey.objects.filter(slug='phase1_friend_closeness').update(priority=100)

    phase1_closeness = Survey.objects.filter(slug='phase1_friend_closeness').first()
    if phase1_closeness:
        ScheduledSurvey.objects.update_or_create(
            cadence='biweekly',
            sequence_index=6,
            defaults={
                'survey': phase1_closeness,
                'window_start': PHASE1_DUE,
                'window_end': PHASE1_DUE,
                'allow_late': True,
                'target_user_group': '',
                'sidebar_order': SIDEBAR_ORDER[('biweekly', 6)],
            },
        )

    feature = Survey.objects.filter(slug='feature_eval_w').first()
    if feature:
        for seq, start, target_group in [
            (2, FEATURE_W_FIRST_START, 'group_w_first'),
            (3, FEATURE_Q_FIRST_START, 'group_q_first'),
        ]:
            ScheduledSurvey.objects.update_or_create(
                cadence='endpoint',
                sequence_index=seq,
                defaults={
                    'survey': feature,
                    'window_start': start,
                    'window_end': FEATURE_DUE_WEEKEND,
                    'allow_late': True,
                    'target_user_group': target_group,
                    'sidebar_order': SIDEBAR_ORDER[('endpoint', seq)],
                },
            )

    anytime = Survey.objects.filter(slug='anytime_reflection').first()
    if anytime:
        ScheduledSurvey.objects.update_or_create(
            cadence='anytime',
            sequence_index=1,
            defaults={
                'survey': anytime,
                'window_start': ANYTIME_START,
                'window_end': None,
                'allow_late': True,
                'target_user_group': '',
                'sidebar_order': None,
            },
        )

    ScheduledSurvey.objects.filter(cadence='endpoint', sequence_index=4).update(
        sidebar_order=SIDEBAR_ORDER[('endpoint', 4)],
    )

    for seq in (2, 3):
        ScheduledSurvey.objects.filter(cadence='biweekly', sequence_index=seq).update(
            window_start=PHASE1_DUE,
            window_end=PHASE1_PART2_DUE,
            allow_late=True,
            sidebar_order=SIDEBAR_ORDER[('biweekly', seq)],
        )

def reverse_priority_order_and_windows(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')

    for slug, title in OLD_REFLECTION_TITLES.items():
        Survey.objects.filter(slug=slug).update(
            title=title,
            title_en=title,
            title_ko=title,
            priority=100,
        )

    Survey.objects.filter(slug='phase1_friend_closeness').update(priority=50)

    ScheduledSurvey.objects.filter(
        cadence='endpoint',
        sequence_index=2,
        survey__slug='feature_eval_w',
    ).update(window_start=FEATURE_W_FIRST_START, window_end=PHASE1_DUE)
    ScheduledSurvey.objects.filter(
        cadence='endpoint',
        sequence_index=3,
        survey__slug='feature_eval_w',
    ).update(window_start=FEATURE_Q_FIRST_START, window_end=PHASE2_DUE)
    ScheduledSurvey.objects.filter(
        cadence='anytime',
        sequence_index=1,
        survey__slug='anytime_reflection',
    ).update(window_start=ANYTIME_START, window_end=PHASE2_DUE)
    ScheduledSurvey.objects.filter(cadence='biweekly', sequence_index__in=[2, 3]).update(
        window_start=PHASE1_DUE,
        window_end=PHASE1_DUE,
        allow_late=True,
    )
    for cadence, seq in SIDEBAR_ORDER:
        ScheduledSurvey.objects.filter(cadence=cadence, sequence_index=seq).update(
            sidebar_order=None,
        )


class Migration(migrations.Migration):
    dependencies = [
        ('surveys', '0034_surveydraft_surveydraft_unique_survey_draft_per_user'),
    ]

    operations = [
        migrations.RunPython(
            apply_priority_order_and_windows,
            reverse_code=reverse_priority_order_and_windows,
        ),
    ]
