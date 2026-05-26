from django.db import migrations


NEW_SIDEBAR_ORDER = {
    ('endpoint', 2): 1,
    ('endpoint', 3): 1,
    ('endpoint', 22): 1,
    ('biweekly', 6): 2,
    ('endpoint', 4): 3,
    ('biweekly', 2): 4,
    ('biweekly', 3): 4,
}

OLD_SIDEBAR_ORDER = {
    ('biweekly', 6): 1,
    ('endpoint', 4): 2,
    ('biweekly', 2): 3,
    ('biweekly', 3): 3,
    ('endpoint', 2): 4,
    ('endpoint', 3): 4,
    ('endpoint', 22): None,
}


def apply_ver_w_priority(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')

    Survey.objects.filter(slug__in=['feature_eval_w', 'feature_eval_w_part2']).update(
        priority=200,
    )
    for (cadence, sequence_index), sidebar_order in NEW_SIDEBAR_ORDER.items():
        ScheduledSurvey.objects.filter(
            cadence=cadence,
            sequence_index=sequence_index,
        ).update(sidebar_order=sidebar_order)


def reverse_ver_w_priority(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')

    Survey.objects.filter(slug__in=['feature_eval_w', 'feature_eval_w_part2']).update(
        priority=100,
    )
    for (cadence, sequence_index), sidebar_order in OLD_SIDEBAR_ORDER.items():
        ScheduledSurvey.objects.filter(
            cadence=cadence,
            sequence_index=sequence_index,
        ).update(sidebar_order=sidebar_order)


class Migration(migrations.Migration):
    dependencies = [
        ('surveys', '0044_alter_pointaward_source_kind'),
    ]

    operations = [
        migrations.RunPython(apply_ver_w_priority, reverse_code=reverse_ver_w_priority),
    ]
