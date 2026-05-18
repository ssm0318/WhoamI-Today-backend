from django.db import migrations


HABIT_PLATFORM_SLUG = 'habit_platform'
TITLE_EN = 'Habitual platform'
TITLE_KO = '습관적으로 여는 플랫폼'
INTRO_EN = (
    'Pick the platform that feels the most automatic for you to open — '
    'the one you tap without really deciding to.'
)
INTRO_KO = '별 생각 없이 자동으로 열게 되는 플랫폼을 골라 주세요.'


def update_habit_platform_copy(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    SurveyQuestion = apps.get_model('surveys', 'SurveyQuestion')

    survey = Survey.objects.filter(slug=HABIT_PLATFORM_SLUG).first()
    if not survey:
        return

    survey.title = TITLE_EN
    survey.title_en = TITLE_EN
    survey.title_ko = TITLE_KO
    survey.description = ''
    survey.description_en = ''
    survey.description_ko = ''
    survey.save(update_fields=[
        'title',
        'title_en',
        'title_ko',
        'description',
        'description_en',
        'description_ko',
    ])

    intro = (
        SurveyQuestion.objects.filter(survey=survey, slug='habit_platform_intro').first()
        or SurveyQuestion.objects.filter(survey=survey, slug='pre_study_catchup_intro').first()
    )
    if not intro:
        return

    intro.slug = 'habit_platform_intro'
    intro.content = INTRO_EN
    intro.content_en = INTRO_EN
    intro.content_ko = INTRO_KO
    intro.save(update_fields=['slug', 'content', 'content_en', 'content_ko'])


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0027_rename_habit_platform_survey'),
    ]

    operations = [
        migrations.RunPython(update_habit_platform_copy, migrations.RunPython.noop),
    ]
