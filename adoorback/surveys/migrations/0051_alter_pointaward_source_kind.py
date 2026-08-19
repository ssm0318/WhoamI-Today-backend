from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0050_dropout_survey_draft'),
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
                    ('friend_invite', 'Friend invitations'),
                    ('researcher_adjustment', 'Researcher adjustment'),
                ],
                max_length=32,
            ),
        ),
    ]
