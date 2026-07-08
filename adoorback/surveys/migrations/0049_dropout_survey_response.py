# Generated manually for the public WhoAmI dropout survey.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('surveys', '0048_pointaward_researcher_adjustment'),
    ]

    operations = [
        migrations.CreateModel(
            name='DropoutSurveyResponse',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('identifier_hash', models.CharField(blank=True, default='', max_length=64)),
                ('matched_identifier_type', models.CharField(choices=[('username', 'Username'), ('email', 'Email'), ('unmatched', 'Unmatched')], default='unmatched', max_length=20)),
                ('user_group', models.CharField(blank=True, default='', max_length=20)),
                ('phase1_version', models.CharField(blank=True, default='', max_length=20)),
                ('phase2_version', models.CharField(blank=True, default='', max_length=20)),
                ('answers', models.JSONField(blank=True, default=dict)),
                ('lookup_metadata', models.JSONField(blank=True, default=dict)),
                ('submitted_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dropout_survey_responses', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-submitted_at', '-id'],
                'indexes': [
                    models.Index(fields=['user', 'submitted_at'], name='surveys_drop_user_sub_idx'),
                    models.Index(fields=['identifier_hash'], name='surveys_drop_ident_idx'),
                ],
            },
        ),
    ]
