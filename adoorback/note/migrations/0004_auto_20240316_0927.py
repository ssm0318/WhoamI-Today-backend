# Generated by Django 3.2.13 on 2024-03-16 16:27

from django.db import migrations, models
import django.db.models.deletion
import note.models


class Migration(migrations.Migration):

    dependencies = [
        ('note', '0003_alter_note_share_everyone'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='note',
            name='image',
        ),
        migrations.CreateModel(
            name='NoteImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('deleted', models.DateTimeField(db_index=True, editable=False, null=True)),
                ('deleted_by_cascade', models.BooleanField(default=False, editable=False)),
                ('image', models.ImageField(storage=note.models.OverwriteStorage(), upload_to=note.models.note_image_path)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('note', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='images', to='note.note')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
