import django.db.models.deletion
from django.db import migrations, models


def clear_playlist_feed(apps, schema_editor):
    PlaylistFeed = apps.get_model('playlist', 'PlaylistFeed')
    PlaylistFeed.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('playlist', '0003_playlistfeed_feed_id'),
        ('check_in', '0010_create_song_remove_checkin_track_id'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Song',
        ),
        migrations.RunPython(clear_playlist_feed, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='playlistfeed',
            name='check_in',
        ),
        migrations.AddField(
            model_name='playlistfeed',
            name='song',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='check_in.song'),
            preserve_default=False,
        ),
    ]
