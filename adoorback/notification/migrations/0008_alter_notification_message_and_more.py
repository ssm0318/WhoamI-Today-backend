# Generated by Django 4.2.14 on 2025-03-09 07:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0007_alter_notification_notification_updated_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='message',
            field=models.CharField(max_length=300),
        ),
        migrations.AlterField(
            model_name='notification',
            name='message_en',
            field=models.CharField(max_length=300, null=True),
        ),
        migrations.AlterField(
            model_name='notification',
            name='message_ko',
            field=models.CharField(max_length=300, null=True),
        ),
    ]
