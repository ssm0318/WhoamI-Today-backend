from django.db import migrations

INTEREST_CATEGORIES = [
    'music_entertainment',
    'hobbies_activities',
    'on_my_mind',
    'as_a_friend',
    'favorite_platform',
    'least_favorite_platform',
]


def backfill(apps, schema_editor):
    User = apps.get_model('account', 'User')
    # Non-persona categories inherit from legacy interests_friends_only
    update_kwargs = {f"{cat}_friends_only": True for cat in INTEREST_CATEGORIES}
    User.objects.filter(interests_friends_only=True).update(**update_kwargs)
    # online_persona inherits from legacy persona_friends_only
    User.objects.filter(persona_friends_only=True).update(online_persona_friends_only=True)


def reverse(apps, schema_editor):
    User = apps.get_model('account', 'User')
    reset_kwargs = {f"{cat}_friends_only": False for cat in INTEREST_CATEGORIES}
    reset_kwargs['online_persona_friends_only'] = False
    User.objects.all().update(**reset_kwargs)


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0046_add_per_category_friends_only'),
    ]

    operations = [
        migrations.RunPython(backfill, reverse),
    ]
