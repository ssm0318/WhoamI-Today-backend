# Generated by Django 3.2.13 on 2023-10-22 07:36

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0011_auto_20230908_2232'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='noti_on',
        ),
    ]