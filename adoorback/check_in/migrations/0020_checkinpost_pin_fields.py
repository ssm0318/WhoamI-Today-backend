from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('check_in', '0019_rename_check_in_ch_created_idx_check_in_ch_created_e47cad_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='checkinpost',
            name='is_pinned',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='checkinpost',
            name='pin_visibility',
            field=models.CharField(
                blank=True,
                choices=[('friends', 'Friends'), ('close_friends', 'Close Friends')],
                max_length=20,
                null=True,
            ),
        ),
    ]
