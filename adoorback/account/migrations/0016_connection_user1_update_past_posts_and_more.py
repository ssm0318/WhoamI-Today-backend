# Generated by Django 4.2.14 on 2025-02-02 23:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0015_remove_user_friends_alter_connection_user1_choice_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='connection',
            name='user1_update_past_posts',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='connection',
            name='user1_upgrade_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='connection',
            name='user2_update_past_posts',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='connection',
            name='user2_upgrade_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
