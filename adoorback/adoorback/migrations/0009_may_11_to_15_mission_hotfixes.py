"""Hot-fix: May 11-15, 2026 prompts — week 2 creative-action missions.

Five low-stakes "do a small thing, capture it, share" missions for the
second week of the WIT study. All type=text, no cta, share_results=True
(default). Posts are expected to include a photo attachment.

Reverse restores the original 0002_seed_missions values at positions 11-15.
"""
from django.db import migrations


# (day_of_year, prompt, type, original_prompt, original_type)
HOTFIXES = [
    (
        131,  # May 11 — 131 % 30 == 11 — self-portrait doodle
        (
            "Hand-draw your own face. 60 seconds, whatever pen you grab, "
            "no retakes. Share the first attempt."
        ),
        'text',
        'Share your current favorite snack',
        'text',
    ),
    (
        132,  # May 12 — 132 % 30 == 12 — random meme
        (
            "Share the most random meme you saw today. Doesn't need to be "
            "funny. Doesn't need context."
        ),
        'text',
        'What hobby have you picked up lately?',
        'text',
    ),
    (
        133,  # May 13 — 133 % 30 == 13 — 5th photo in camera roll
        (
            "Open your camera roll and share the 5th photo. Tell us a bit "
            "about it — when, where, why you took it."
        ),
        'text',
        'Share a quote that resonates with you',
        'text',
    ),
    (
        134,  # May 14 — 134 % 30 == 14 — hand-written line
        (
            "Hand-write any single sentence — a thought, a lyric, something "
            "you'd put on a sticker. Take a photo and share."
        ),
        'text',
        'What made you smile today?',
        'text',
    ),
    (
        135,  # May 15 — 135 % 30 == 15 — three random objects
        (
            "Take one photo of three random objects within arm's reach of "
            "you right now."
        ),
        'text',
        'Share a song you have on repeat',
        'song',
    ),
]


def _target(Mission, day_of_year):
    missions = list(Mission.objects.order_by('id'))
    if not missions:
        return None
    return missions[day_of_year % len(missions)]


def set_may_11_to_15_missions(apps, schema_editor):
    Mission = apps.get_model('adoorback', 'Mission')
    for day_of_year, prompt, mtype, _orig_prompt, _orig_type in HOTFIXES:
        target = _target(Mission, day_of_year)
        if target is None:
            continue
        target.prompt = prompt
        target.type = mtype
        target.save(update_fields=['prompt', 'type'])


def restore_may_11_to_15_missions(apps, schema_editor):
    Mission = apps.get_model('adoorback', 'Mission')
    for day_of_year, _prompt, _mtype, orig_prompt, orig_type in HOTFIXES:
        target = _target(Mission, day_of_year)
        if target is None:
            continue
        target.prompt = orig_prompt
        target.type = orig_type
        target.save(update_fields=['prompt', 'type'])


class Migration(migrations.Migration):

    dependencies = [
        ('adoorback', '0008_may_8_to_10_mission_hotfixes'),
    ]

    operations = [
        migrations.RunPython(set_may_11_to_15_missions, restore_may_11_to_15_missions),
    ]
