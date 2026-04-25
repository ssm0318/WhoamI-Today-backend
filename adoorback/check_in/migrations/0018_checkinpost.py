from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import check_in.models


class Migration(migrations.Migration):

    dependencies = [
        ('check_in', '0017_backfill_component_entries'),
    ]

    operations = [
        migrations.CreateModel(
            name='CheckInPost',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('deleted', models.DateTimeField(db_index=True, editable=False, null=True)),
                ('deleted_by_cascade', models.BooleanField(default=False, editable=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('image', models.ImageField(
                    upload_to=check_in.models.check_in_post_image_path,
                    storage=check_in.models.CheckInPostStorage(),
                )),
                ('caption', models.TextField(blank=True, default='')),
                ('visibility', models.CharField(
                    choices=[('friends', 'Friends'), ('close_friends', 'Close Friends')],
                    default='friends',
                    max_length=20,
                )),
                ('author', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='check_in_post_set',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('readers', models.ManyToManyField(
                    blank=True,
                    related_name='read_check_in_posts',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='checkinpost',
            index=models.Index(fields=['-created_at'], name='check_in_ch_created_idx'),
        ),
        migrations.AddIndex(
            model_name='checkinpost',
            index=models.Index(fields=['author', '-created_at'], name='check_in_ch_author_created_idx'),
        ),
    ]
