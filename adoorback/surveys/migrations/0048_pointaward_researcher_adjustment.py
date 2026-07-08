# Generated manually for researcher-audited reimbursement adjustments.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0047_backfill_legacy_point_awards'),
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
                    ('researcher_adjustment', 'Researcher adjustment'),
                ],
                max_length=32,
            ),
        ),
    ]
