# Generated by Django 4.2.11 on 2024-07-13 02:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0005_rename_new_actors_notification_actors'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='notification',
            options={'ordering': ['-notification_updated_at']},
        ),
        migrations.RemoveIndex(
            model_name='notification',
            name='notificatio_created_87dbca_idx',
        ),
        migrations.AddField(
            model_name='notification',
            name='notification_updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['-notification_updated_at'], name='notificatio_notific_bb8886_idx'),
        ),
    ]
