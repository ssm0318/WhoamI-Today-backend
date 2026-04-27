from django.db import migrations, models
import qna.models


class Migration(migrations.Migration):

    dependencies = [
        ('qna', '0012_response_video_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='response',
            name='image',
            field=models.ImageField(
                blank=True,
                null=True,
                storage=qna.models.OverwriteStorage(),
                upload_to=qna.models.response_image_path,
            ),
        ),
    ]
