from django.db import migrations, models
import qna.models


class Migration(migrations.Migration):

    dependencies = [
        ('qna', '0011_alter_response_visibility'),
    ]

    operations = [
        migrations.AddField(
            model_name='response',
            name='video',
            field=models.FileField(
                blank=True, null=True,
                storage=qna.models.OverwriteStorage(),
                upload_to=qna.models.response_video_path,
            ),
        ),
        migrations.AddField(
            model_name='response',
            name='video_thumbnail',
            field=models.ImageField(
                blank=True, null=True,
                storage=qna.models.OverwriteStorage(),
                upload_to=qna.models.response_video_thumbnail_path,
            ),
        ),
        migrations.AddField(
            model_name='response',
            name='video_duration_seconds',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
