00# Generated by Django 3.2.13 on 2024-02-21 01:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('check_in', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='checkin',
            name='share_everyone',
            field=models.BooleanField(blank=True, default=False),
        ),
    ]
