from django.db import migrations


OLD_SLUG = 'pre_study_catchup'
NEW_SLUG = 'habit_platform'


def rename_habit_platform_survey(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')

    old = Survey.objects.filter(slug=OLD_SLUG).first()
    new = Survey.objects.filter(slug=NEW_SLUG).first()

    if old and not new:
        old.slug = NEW_SLUG
        old.save(update_fields=['slug'])
        new = old
    elif old and new and old.pk != new.pk:
        ScheduledSurvey.objects.filter(survey=old).update(survey=new)

    if new:
        ScheduledSurvey.objects.filter(
            cadence='biweekly',
            sequence_index=8,
        ).update(survey=new)


def reverse_rename_habit_platform_survey(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    old = Survey.objects.filter(slug=NEW_SLUG).first()
    if old and not Survey.objects.filter(slug=OLD_SLUG).exists():
        old.slug = OLD_SLUG
        old.save(update_fields=['slug'])


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0026_free_text_min_length_zero'),
    ]

    operations = [
        migrations.RunPython(
            rename_habit_platform_survey,
            reverse_code=reverse_rename_habit_platform_survey,
        ),
    ]
