# Generated by Django 4.2.11 on 2024-03-09 07:01

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("notification", "0003_copy_actors"),
    ]

    operations = [
        migrations.RemoveField(model_name="notification", name="actors",),
    ]