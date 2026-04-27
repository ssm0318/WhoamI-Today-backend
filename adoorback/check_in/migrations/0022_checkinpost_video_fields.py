from django.db import migrations, models
import check_in.models


class Migration(migrations.Migration):

    dependencies = [
        ('check_in', '0021_checkinpost_pin_index'),
    ]

    operations = [
        migrations.AlterField(
            model_name='checkinpost',
            name='image',
            field=models.ImageField(
                blank=True, null=True,
                storage=check_in.models.CheckInPostStorage(),
                upload_to=check_in.models.check_in_post_image_path,
            ),
        ),
        migrations.AddField(
            model_name='checkinpost',
            name='video',
            field=models.FileField(
                blank=True, null=True,
                storage=check_in.models.CheckInPostStorage(),
                upload_to=check_in.models.check_in_post_video_path,
            ),
        ),
        migrations.AddField(
            model_name='checkinpost',
            name='video_thumbnail',
            field=models.ImageField(
                blank=True, null=True,
                storage=check_in.models.CheckInPostStorage(),
                upload_to=check_in.models.check_in_post_video_thumbnail_path,
            ),
        ),
        migrations.AddField(
            model_name='checkinpost',
            name='video_duration_seconds',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
