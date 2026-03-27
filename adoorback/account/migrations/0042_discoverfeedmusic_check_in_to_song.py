import django.db.models.deletion
from django.db import migrations, models


def clear_discover_feed_music(apps, schema_editor):
    DiscoverFeedMusic = apps.get_model('account', 'DiscoverFeedMusic')
    DiscoverFeedMusic.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0041_add_discover_feed_music'),
        ('check_in', '0010_create_song_remove_checkin_track_id'),
    ]

    operations = [
        migrations.RunPython(clear_discover_feed_music, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='discoverfeedmusic',
            name='check_in',
        ),
        migrations.AddField(
            model_name='discoverfeedmusic',
            name='song',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, related_name='discover_feed_music_items', to='check_in.song'),
            preserve_default=False,
        ),
    ]
