# Generated by Django 3.2.13 on 2023-06-24 05:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('feed', '0007_auto_20230603_1638'),
    ]

    operations = [
        migrations.AddField(
            model_name='response',
            name='date',
            field=models.CharField(blank=True, max_length=10),
        ),
    ]