from django.db import migrations, models
import django.db.models.deletion
import note.models


class Migration(migrations.Migration):

    dependencies = [
        ('note', '0010_note_share_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='NoteVideo',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('deleted', models.DateTimeField(editable=False, null=True)),
                ('video', models.FileField(storage=note.models.OverwriteStorage(), upload_to=note.models.note_video_path)),
                ('thumbnail', models.ImageField(blank=True, null=True, storage=note.models.OverwriteStorage(), upload_to=note.models.note_video_thumbnail_path)),
                ('duration_seconds', models.FloatField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('note', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='videos', to='note.note')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
