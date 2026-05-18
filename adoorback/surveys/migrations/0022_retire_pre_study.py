from django.db import migrations
from django.db.models.deletion import ProtectedError


RETIRED_PRE_STUDY_SLUG = 'pre_study'


def retire_pre_study(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')

    ScheduledSurvey.objects.filter(survey__slug=RETIRED_PRE_STUDY_SLUG).delete()

    survey = Survey.objects.filter(slug=RETIRED_PRE_STUDY_SLUG).first()
    if survey is None:
        return
    if survey.responses.exists():
        survey.closed = True
        survey.save(update_fields=['closed'])
        return
    try:
        survey.delete()
    except ProtectedError:
        survey.closed = True
        survey.save(update_fields=['closed'])


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0021_seed_closeness_schedule'),
    ]

    operations = [
        migrations.RunPython(retire_pre_study, reverse_code=migrations.RunPython.noop),
    ]
