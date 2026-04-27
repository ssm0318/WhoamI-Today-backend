import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0053_is_public_not_null'),
    ]

    operations = [
        migrations.CreateModel(
            name='FriendEvaluation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted', models.DateTimeField(editable=False, null=True)),
                ('deleted_by_cascade', models.BooleanField(default=False, editable=False)),
                ('context', models.CharField(choices=[('request', 'Friend Request Sent'), ('accept', 'Friend Request Accepted')], max_length=10)),
                ('closeness', models.IntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)])),
                ('relationship_type', models.CharField(blank=True, choices=[('school_friend', 'School Friend'), ('coworker', 'Coworker'), ('family', 'Family'), ('online_friend', 'Online Friend'), ('club_community', 'Club/Community'), ('other', 'Other')], max_length=20, null=True)),
                ('relationship_type_detail', models.CharField(blank=True, max_length=50, null=True)),
                ('skipped', models.BooleanField(default=False)),
                ('evaluator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='friend_evaluations_given', to=settings.AUTH_USER_MODEL)),
                ('evaluated_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='friend_evaluations_received', to=settings.AUTH_USER_MODEL)),
                ('friend_request', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='evaluations', to='account.friendrequest')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddConstraint(
            model_name='friendevaluation',
            constraint=models.UniqueConstraint(
                condition=models.Q(('deleted__isnull', True)),
                fields=('evaluator', 'evaluated_user', 'friend_request'),
                name='unique_friend_evaluation',
            ),
        ),
        migrations.AddIndex(
            model_name='friendevaluation',
            index=models.Index(fields=['evaluator', 'skipped'], name='account_fri_evaluat_idx'),
        ),
    ]
