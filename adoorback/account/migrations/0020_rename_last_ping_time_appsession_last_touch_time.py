# Generated by Django 4.2.14 on 2025-03-01 05:31

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0019_appsession_last_ping_time'),
    ]

    operations = [
        migrations.RenameField(
            model_name='appsession',
            old_name='last_ping_time',
            new_name='last_touch_time',
        ),
    ]
