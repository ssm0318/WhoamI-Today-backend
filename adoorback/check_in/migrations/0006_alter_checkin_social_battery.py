# Generated by Django 4.2.14 on 2025-03-24 04:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('check_in', '0005_remove_checkin_availability_checkin_social_battery'),
    ]

    operations = [
        migrations.AlterField(
            model_name='checkin',
            name='social_battery',
            field=models.CharField(blank=True, choices=[('completely_drained', 'Completely Drained'), ('low', 'Low Social Battery'), ('needs_recharge', 'Needs Recharge'), ('moderately_social', 'Moderately Social'), ('fully_charged', 'Fully Charged'), ('super_social', 'Super Social Mode (HMU!)')], max_length=30, null=True),
        ),
    ]
