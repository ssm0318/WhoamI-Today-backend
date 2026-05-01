"""Hot-fix: set May 1, 2026 Mission of the Day to a community-greeting prompt.

The frontend selects today's mission via `missions[getDayOfYear() % missions.length]`
(see `WhoamI-Today-frontend/src/components/share/MissionOfTheDay.tsx:13` and
`src/routes/discover/Discover.tsx:114`). For May 1, 2026 the day-of-year is 121,
so we update the row at index `121 % count` (ordered by id) — currently the row
seeded as 'Ask the community a question'.

Reverse restores the original seed values, so `migrate adoorback 0002`
cleanly rolls back this hotfix.
"""
from django.db import migrations


MAY_1_2026_DAY_OF_YEAR = 121

NEW_PROMPT = (
    'Say hi to the WIT user community! Share a public post with something '
    'that represents you—a drawing, a favorite item, your pet, etc.'
)
NEW_TYPE = 'text'

ORIGINAL_PROMPT = 'Ask the community a question'
ORIGINAL_TYPE = 'question'


def _target(Mission):
    missions = list(Mission.objects.order_by('id'))
    if not missions:
        return None
    return missions[MAY_1_2026_DAY_OF_YEAR % len(missions)]


def set_may_1_mission(apps, schema_editor):
    Mission = apps.get_model('adoorback', 'Mission')
    target = _target(Mission)
    if target is None:
        return
    target.prompt = NEW_PROMPT
    target.type = NEW_TYPE
    target.save(update_fields=['prompt', 'type'])


def restore_may_1_mission(apps, schema_editor):
    Mission = apps.get_model('adoorback', 'Mission')
    target = _target(Mission)
    if target is None:
        return
    target.prompt = ORIGINAL_PROMPT
    target.type = ORIGINAL_TYPE
    target.save(update_fields=['prompt', 'type'])


class Migration(migrations.Migration):

    dependencies = [
        ('adoorback', '0002_seed_missions'),
    ]

    operations = [
        migrations.RunPython(set_may_1_mission, restore_may_1_mission),
    ]
