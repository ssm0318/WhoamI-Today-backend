from django.db import migrations


FIELD_MAP = {
    'pronouns_friends_only': 'pronouns_visibility',
    'bio_friends_only': 'bio_visibility',
    'music_entertainment_friends_only': 'music_entertainment_visibility',
    'hobbies_activities_friends_only': 'hobbies_activities_visibility',
    'on_my_mind_friends_only': 'on_my_mind_visibility',
    'as_a_friend_friends_only': 'as_a_friend_visibility',
    'online_persona_friends_only': 'online_persona_visibility',
    'favorite_platform_friends_only': 'favorite_platform_visibility',
    'least_favorite_platform_friends_only': 'least_favorite_platform_visibility',
}


def boolean_to_enum(apps, schema_editor):
    User = apps.get_model('account', 'user')
    update_fields = list(FIELD_MAP.values())
    for user in User.objects.all():
        for old, new in FIELD_MAP.items():
            if getattr(user, old, False):
                setattr(user, new, 'friends')
        user.save(update_fields=update_fields)


def enum_to_boolean(apps, schema_editor):
    User = apps.get_model('account', 'user')
    update_fields = list(FIELD_MAP.keys())
    for user in User.objects.all():
        for old, new in FIELD_MAP.items():
            setattr(user, old, getattr(user, new, 'public') != 'public')
        user.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0060_user_as_a_friend_visibility_user_bio_visibility_and_more'),
    ]

    operations = [
        migrations.RunPython(boolean_to_enum, enum_to_boolean),
    ]
