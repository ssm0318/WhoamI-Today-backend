from datetime import date

from django.db import migrations
from django.db.models.deletion import ProtectedError


WEEKLY_SURVEY_SLUGS = [
    'week1_reflection',
    'week2_reflection',
    'week3_reflection',
    'week4_reflection',
]

KEEP_WEEKLY_QUESTION_SLUGS = [
    'weekly_ritual_highlight',
    'weekly_issue_flag',
    'weekly_issue_text',
]

RETIRED_WEEKLY_QUESTION_SLUGS = {
    'weekly_intro',
    'weekly_overall_feel',
    'weekly_ritual_highlight_other',
    'weekly_moment',
    'weekly_tomorrow_question',
}

RETIRED_CONDITIONAL_DISPLAY = {
    'depends_on': 'weekly_issue_flag',
    'show_when_value': '__retired_weekly_question__',
}


# (sequence_index, slug, window_start, window_end)
WEEKEND_WEEKLY_SCHEDULE = [
    (1, 'week1_reflection', date(2026, 5, 9), date(2026, 5, 10)),
    (2, 'week2_reflection', date(2026, 5, 16), date(2026, 5, 17)),
    (3, 'week3_reflection', date(2026, 5, 23), date(2026, 5, 24)),
    (4, 'week4_reflection', date(2026, 5, 30), date(2026, 5, 31)),
]

PREVIOUS_WEEKLY_SCHEDULE = [
    (1, 'week1_reflection', date(2026, 5, 10), date(2026, 5, 16)),
    (2, 'week2_reflection', date(2026, 5, 17), date(2026, 5, 23)),
    (3, 'week3_reflection', date(2026, 5, 24), date(2026, 5, 30)),
    (4, 'week4_reflection', date(2026, 5, 31), date(2026, 6, 6)),
]


def apply_weekend_weekly_reflections(apps, schema_editor):
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    Survey = apps.get_model('surveys', 'Survey')
    SurveyOption = apps.get_model('surveys', 'SurveyOption')

    for seq, _slug, window_start, window_end in WEEKEND_WEEKLY_SCHEDULE:
        ScheduledSurvey.objects.filter(
            cadence='weekly',
            sequence_index=seq,
        ).update(
            window_start=window_start,
            window_end=window_end,
            allow_late=False,
        )

    for survey_slug in WEEKLY_SURVEY_SLUGS:
        survey = Survey.objects.filter(slug=survey_slug).first()
        if survey is None:
            continue

        questions = list(survey.questions.all())
        original_orders = {question.id: question.order for question in questions}

        # Move everything out of the 1..N range first so the final kept
        # questions can be compacted to orders 1, 2, 3 without unique-order
        # collisions.
        for index, question in enumerate(questions, start=1):
            question.order = 1000 + index
            question.save(update_fields=['order'])

        for question in questions:
            if question.slug in KEEP_WEEKLY_QUESTION_SLUGS:
                continue
            if question.slug not in RETIRED_WEEKLY_QUESTION_SLUGS:
                continue
            try:
                if question.answers.exists():
                    raise ProtectedError('Question has existing answers.', [question])
                question.delete()
            except ProtectedError:
                question.order = 100 + original_orders[question.id]
                question.required = False
                question.result_hidden = True
                question.conditional_display = RETIRED_CONDITIONAL_DISPLAY
                question.save(
                    update_fields=[
                        'order',
                        'required',
                        'result_hidden',
                        'conditional_display',
                    ]
                )

        for order, slug in enumerate(KEEP_WEEKLY_QUESTION_SLUGS, start=1):
            question = survey.questions.filter(slug=slug).first()
            if question is None:
                continue
            question.order = order
            if slug == 'weekly_issue_text':
                question.required = False
                question.conditional_display = {
                    'depends_on': 'weekly_issue_flag',
                    'show_when_value_in': [2, 3, 4, 5],
                }
                question.save(update_fields=['order', 'required', 'conditional_display'])
            else:
                question.required = True
                question.conditional_display = {}
                question.save(update_fields=['order', 'required', 'conditional_display'])

        highlight = survey.questions.filter(slug='weekly_ritual_highlight').first()
        if highlight is not None:
            SurveyOption.objects.filter(question=highlight, value='other').update(
                label='Something else',
                label_en='Something else',
            )


def restore_previous_weekly_windows(apps, schema_editor):
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    for seq, _slug, window_start, window_end in PREVIOUS_WEEKLY_SCHEDULE:
        ScheduledSurvey.objects.filter(
            cadence='weekly',
            sequence_index=seq,
        ).update(
            window_start=window_start,
            window_end=window_end,
            allow_late=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0022_retire_pre_study'),
    ]

    operations = [
        migrations.RunPython(
            apply_weekend_weekly_reflections,
            reverse_code=restore_previous_weekly_windows,
        ),
    ]
