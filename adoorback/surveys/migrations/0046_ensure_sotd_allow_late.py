from django.db import migrations


def ensure_sotd_allow_late(apps, schema_editor):
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    ScheduledSurvey.objects.filter(
        cadence='daily',
        survey__slug__startswith='sotd_d',
    ).update(allow_late=True)


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0045_prioritize_ver_w_surveys'),
    ]

    operations = [
        migrations.RunPython(ensure_sotd_allow_late, reverse_code=migrations.RunPython.noop),
    ]
