"""Hot-fix: replace QotD-style mission prompts in the back half of the study.

The 0002 seed has several "What is X?" / "Describe X?" / "What are you X?"
prompts at positions 16-29 that overlap with the Question-of-the-Day feature.
This migration replaces 11 of those with action-based "do a small thing,
capture it, share" prompts to keep the mission flow distinct from QotD.

Days NOT overridden (already action-y or song-type):
- May 21 (pos 21): "Share your current desktop or phone wallpaper"
- May 23 (pos 23): "Share a song that gives you energy" (song)
- May 28 (pos 28): "Share a song that calms you down" (song)
- May 30 (pos 0): "Share a song that matches your mood right now" (song)

May 25 (pos 25) also changes type from 'question' to 'text' to drop the
literal /questions routing overlap.

Reverse restores the original 0002_seed_missions values at all 11 positions.
"""
from django.db import migrations


# (day_of_year, prompt, type, original_prompt, original_type)
HOTFIXES = [
    (
        136,  # May 16 — 136 % 30 == 16
        "Take a photo of your shoes wherever they are right now.",
        'text',
        'What is the best thing that happened this week?',
        'text',
    ),
    (
        137,  # May 17 — pos 17
        "Open your camera and take a photo of the ceiling above you right now.",
        'text',
        'Describe your ideal weekend',
        'text',
    ),
    (
        138,  # May 18 — pos 18
        (
            "Photo of your current setup — desk, couch, kitchen counter, "
            "wherever you happen to be right now."
        ),
        'text',
        'What are you grateful for today?',
        'text',
    ),
    (
        139,  # May 19 — pos 19
        (
            "Share a single song lyric (just the line, no context) you've "
            "had stuck in your head this week."
        ),
        'text',
        'Share a movie or show recommendation',
        'text',
    ),
    (
        140,  # May 20 — pos 20
        (
            "Doodle the first object you see when you look up from your "
            "phone. 30 seconds, single pen, no retakes."
        ),
        'text',
        'What is something you want to try?',
        'text',
    ),
    (
        142,  # May 22 — pos 22
        (
            "Find a sticker on something you own — laptop, water bottle, "
            "notebook, anywhere. Close-up photo."
        ),
        'text',
        'What are you reading right now?',
        'text',
    ),
    (
        144,  # May 24 — pos 24
        "Take a photo of the inside of your fridge or freezer. No curation.",
        'text',
        'What is your go-to comfort food?',
        'text',
    ),
    (
        145,  # May 25 — pos 25  (also drops type=question -> text)
        "Find the oldest photo on your phone and share it.",
        'text',
        'Ask your friends for a recommendation',
        'question',
    ),
    (
        146,  # May 26 — pos 26
        (
            "Take a screenshot of your phone's home screen. Show us how "
            "cluttered (or not) it is."
        ),
        'text',
        'Share a fun fact about yourself',
        'text',
    ),
    (
        147,  # May 27 — pos 27
        (
            "Take a photo of a piece of paper, sticky note, or notepad "
            "you're using right now."
        ),
        'text',
        'What skill do you want to learn?',
        'text',
    ),
    (
        149,  # May 29 — pos 29
        "Take a photo of your hands — whatever they're doing or holding right now.",
        'text',
        'What is your unpopular opinion?',
        'text',
    ),
]


def _target(Mission, day_of_year):
    missions = list(Mission.objects.order_by('id'))
    if not missions:
        return None
    return missions[day_of_year % len(missions)]


def set_qotd_overrides(apps, schema_editor):
    Mission = apps.get_model('adoorback', 'Mission')
    for day_of_year, prompt, mtype, _orig_prompt, _orig_type in HOTFIXES:
        target = _target(Mission, day_of_year)
        if target is None:
            continue
        target.prompt = prompt
        target.type = mtype
        target.save(update_fields=['prompt', 'type'])


def restore_qotd_seeds(apps, schema_editor):
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
        ('adoorback', '0009_may_11_to_15_mission_hotfixes'),
    ]

    operations = [
        migrations.RunPython(set_qotd_overrides, restore_qotd_seeds),
    ]
