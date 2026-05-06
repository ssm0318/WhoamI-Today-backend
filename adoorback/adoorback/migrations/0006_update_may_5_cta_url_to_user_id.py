"""Update May 5 mission's cta_url from /users/wit_bot/chat to /users/7/chat.

The chat route resolves either way (it accepts both username strings and
numeric IDs), but the test-group prod environment routes by user ID, so
we use the numeric ID directly. wit_bot's user id is 7 in this env.

Reverse restores /users/wit_bot/chat (the value set by 0005).
"""
from django.db import migrations


MAY_5_2026_DAY_OF_YEAR = 125
NEW_CTA_URL = '/users/7/chat'
OLD_CTA_URL = '/users/wit_bot/chat'


def _target(Mission):
    missions = list(Mission.objects.order_by('id'))
    if not missions:
        return None
    return missions[MAY_5_2026_DAY_OF_YEAR % len(missions)]


def update_to_user_id(apps, schema_editor):
    Mission = apps.get_model('adoorback', 'Mission')
    target = _target(Mission)
    if target is None:
        return
    target.cta_url = NEW_CTA_URL
    target.save(update_fields=['cta_url'])


def restore_username(apps, schema_editor):
    Mission = apps.get_model('adoorback', 'Mission')
    target = _target(Mission)
    if target is None:
        return
    target.cta_url = OLD_CTA_URL
    target.save(update_fields=['cta_url'])


class Migration(migrations.Migration):

    dependencies = [
        ('adoorback', '0005_mission_share_results_and_cta_url'),
    ]

    operations = [
        migrations.RunPython(update_to_user_id, restore_username),
    ]
