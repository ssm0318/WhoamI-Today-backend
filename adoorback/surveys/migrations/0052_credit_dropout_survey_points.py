from django.db import migrations, models


def credit_existing_responses(apps, schema_editor):
    DropoutSurveyResponse = apps.get_model('surveys', 'DropoutSurveyResponse')
    PointAward = apps.get_model('surveys', 'PointAward')

    user_ids = (
        DropoutSurveyResponse.objects
        .exclude(user_id=None)
        .values_list('user_id', flat=True)
        .distinct()
    )
    for user_id in user_ids:
        PointAward.objects.get_or_create(
            user_id=user_id,
            source_kind='dropout_survey',
            source_slug='dropout_survey',
            response_id=None,
            scheduled_survey_id=None,
            defaults={
                'awarded_points': 50,
                'note': 'Completed dropout survey.',
            },
        )


def remove_dropout_awards(apps, schema_editor):
    PointAward = apps.get_model('surveys', 'PointAward')
    PointAward.objects.filter(
        source_kind='dropout_survey',
        source_slug='dropout_survey',
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('surveys', '0051_alter_pointaward_source_kind'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pointaward',
            name='source_kind',
            field=models.CharField(
                choices=[
                    ('survey', 'Survey response'),
                    ('wit_bot_audit', 'Wit_bot audit pass'),
                    ('app_usage', 'App usage'),
                    ('interview_signup', 'Interview signup'),
                    ('dropout_survey', 'Dropout survey'),
                    ('friend_invite', 'Friend invitations'),
                    ('researcher_adjustment', 'Researcher adjustment'),
                ],
                max_length=32,
            ),
        ),
        migrations.RunPython(credit_existing_responses, remove_dropout_awards),
    ]
