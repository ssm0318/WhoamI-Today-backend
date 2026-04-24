from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0045_update_version_and_group_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='music_entertainment_friends_only',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='hobbies_activities_friends_only',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='on_my_mind_friends_only',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='as_a_friend_friends_only',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='online_persona_friends_only',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='favorite_platform_friends_only',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='least_favorite_platform_friends_only',
            field=models.BooleanField(default=False),
        ),
    ]
