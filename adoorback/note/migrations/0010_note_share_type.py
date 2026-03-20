from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('note', '0009_alter_note_visibility'),
    ]

    operations = [
        migrations.AddField(
            model_name='note',
            name='share_type',
            field=models.CharField(
                choices=[
                    ('regular', 'Regular'),
                    ('tmi_of_the_day', 'TMI of the Day'),
                    ('photo_of_the_day', 'Photo of the Day'),
                ],
                default='regular',
                max_length=20,
            ),
        ),
    ]
