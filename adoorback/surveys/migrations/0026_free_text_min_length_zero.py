from django.db import migrations


def set_free_text_min_length_zero(apps, schema_editor):
    SurveyQuestion = apps.get_model('surveys', 'SurveyQuestion')
    SurveyQuestion.objects.filter(type='free_text').exclude(min_length=0).update(
        min_length=0,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0025_scheduledsurvey_sidebar_order'),
    ]

    operations = [
        migrations.RunPython(set_free_text_min_length_zero, migrations.RunPython.noop),
    ]
