"""Hot-fix: set May 4–7, 2026 Mission of the Day prompts for the WIT study launch.

Mirrors the pattern in 0003_may_1_mission_hotfix.py. The frontend selects today's
mission via `missions[getDayOfYear() % missions.length]`, ordered by id. For
May 4–7 the day-of-year values are 124–127, which mod 30 give positions 4–7.

Reverse restores the original seed values from 0002_seed_missions.py at those
positions, so `migrate adoorback 0003` cleanly rolls back this hotfix.
"""
from django.db import migrations


# (day_of_year, new_prompt, new_type, original_prompt, original_type)
HOTFIXES = [
    (
        124,  # May 4 — 124 % 30 == 4
        (
            "Today is the first day of the WIT study! Share your first post on "
            "the platform and leave your first emoji reaction. Welcome aboard, "
            "hello world."
        ),
        'text',
        'Share something you learned recently',
        'text',
    ),
    (
        125,  # May 5 — 125 % 30 == 5
        "You're an official WIT user — congrats! Talk to wit_bot to finish onboarding.",
        'text',
        'What are you looking forward to?',
        'text',
    ),
    (
        126,  # May 6 — 126 % 30 == 6
        "Ask a question that you're curious to hear other WIT members' answers to.",
        'question',
        'Share a song that reminds you of a friend',
        'song',
    ),
    (
        127,  # May 7 — 127 % 30 == 7
        (
            "You've been using WIT for three days now. What's your favorite "
            "feature on the platform so far, and why? Show it off."
        ),
        'text',
        'What is your comfort show right now?',
        'text',
    ),
]


def _target(Mission, day_of_year):
    missions = list(Mission.objects.order_by('id'))
    if not missions:
        return None
    return missions[day_of_year % len(missions)]


def set_may_4_7_missions(apps, schema_editor):
    Mission = apps.get_model('adoorback', 'Mission')
    for day_of_year, new_prompt, new_type, _orig_prompt, _orig_type in HOTFIXES:
        target = _target(Mission, day_of_year)
        if target is None:
            continue
        target.prompt = new_prompt
        target.type = new_type
        target.save(update_fields=['prompt', 'type'])


def restore_may_4_7_missions(apps, schema_editor):
    Mission = apps.get_model('adoorback', 'Mission')
    for day_of_year, _new_prompt, _new_type, orig_prompt, orig_type in HOTFIXES:
        target = _target(Mission, day_of_year)
        if target is None:
            continue
        target.prompt = orig_prompt
        target.type = orig_type
        target.save(update_fields=['prompt', 'type'])


class Migration(migrations.Migration):

    dependencies = [
        ('adoorback', '0003_may_1_mission_hotfix'),
    ]

    operations = [
        migrations.RunPython(set_may_4_7_missions, restore_may_4_7_missions),
    ]
