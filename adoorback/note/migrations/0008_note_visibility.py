# Generated by Django 4.2.14 on 2025-01-29 17:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('note', '0007_note_is_edited'),
    ]

    operations = [
        migrations.AddField(
            model_name='note',
            name='visibility',
            field=models.CharField(choices=[('friends', 'Friends'), ('close_friends', 'Close Friends')], default='friends', max_length=20),
        ),
    ]
