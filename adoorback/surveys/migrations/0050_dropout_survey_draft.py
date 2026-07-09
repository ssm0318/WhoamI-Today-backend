# Generated manually for the public WhoAmI dropout survey drafts.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0049_dropout_survey_response'),
    ]

    operations = [
        migrations.CreateModel(
            name='DropoutSurveyDraft',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('identifier_hash', models.CharField(max_length=64, unique=True)),
                ('data', models.JSONField(blank=True, default=dict)),
            ],
            options={
                'ordering': ['-updated_at', '-id'],
            },
        ),
    ]
