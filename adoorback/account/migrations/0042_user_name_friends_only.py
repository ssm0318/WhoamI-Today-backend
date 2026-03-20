from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0041_add_discover_feed_music'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='name_friends_only',
            field=models.BooleanField(default=False),
        ),
    ]
