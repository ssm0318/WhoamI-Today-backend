from django.db import migrations


CLOSENESS_SURVEY_SLUGS = [
    'phase1_friend_closeness',
    'phase2_friend_closeness',
]


def forward(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    Survey.objects.filter(slug__in=CLOSENESS_SURVEY_SLUGS).update(
        editable=False,
        repeatable=False,
    )


def reverse(apps, schema_editor):
    # No reverse: prior DB state varied depending on when setup_survey_state
    # last loaded the fixture. Keeping these one-shot is the intended state.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('surveys', '0036_points_system'),
    ]

    operations = [
        migrations.RunPython(forward, reverse_code=reverse),
    ]
