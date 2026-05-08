"""Hot-fix: May 8-10, 2026 prompts + backfill cta_label for May 5.

May 8-10 are study-week launch missions:
- May 8 (pos 8, type=text): invite-someone prompt with /friends/explore?tab=recommended cta
- May 9 (pos 9, type=text): community-feedback prompt, no cta_url
- May 10 (pos 10, type=none): action-only react-to-friends prompt with /discover cta

Also backfills May 5's cta_label='Chat with wit_bot' (set in 0005/0006 migrations
but the cta_label column did not exist yet).

Reverse restores the original 0002_seed_missions values at positions 8-10
and clears May 5's cta_label.
"""
from django.db import migrations


CHAT_WITH_WIT_BOT_LABEL = 'Chat with wit_bot'

MAY_5_2026_DAY_OF_YEAR = 125

# (day_of_year, prompt, type, cta_url, cta_label, original_prompt, original_type)
HOTFIXES = [
    (
        128,  # May 8 — 128 % 30 == 8
        (
            'Who in your life would "get" WIT? Invite someone you think would '
            'appreciate it most using your personal invite code, and share a bit '
            'about the person. (Heads-up: WIT is invite-only from current users '
            'for the foreseeable future to maintain community health.)'
        ),
        'text',
        '/friends/explore?tab=recommended',
        'Find friends to invite',
        'Recommend a podcast or video',
        'text',
    ),
    (
        129,  # May 9 — 129 % 30 == 9
        (
            "What's one feature you wish WIT had? Share it with the community — "
            "we're listening."
        ),
        'text',
        '',
        '',
        'Share a photo from your camera roll',
        'text',
    ),
    (
        130,  # May 10 — 130 % 30 == 10
        (
            "Leave a reaction on three different friends' posts today. Try out "
            "whatever feels right — a private comment, an emoji, a reaction to "
            "a check-in."
        ),
        'none',
        '/discover',
        'Browse Daily Digest',
        'What is on your mind today?',
        'question',
    ),
]


def _target(Mission, day_of_year):
    missions = list(Mission.objects.order_by('id'))
    if not missions:
        return None
    return missions[day_of_year % len(missions)]


def set_may_8_to_10_missions(apps, schema_editor):
    Mission = apps.get_model('adoorback', 'Mission')
    for day_of_year, prompt, mtype, cta_url, cta_label, _orig_prompt, _orig_type in HOTFIXES:
        target = _target(Mission, day_of_year)
        if target is None:
            continue
        target.prompt = prompt
        target.type = mtype
        target.cta_url = cta_url
        target.cta_label = cta_label
        target.save(update_fields=['prompt', 'type', 'cta_url', 'cta_label'])

    # Backfill May 5's cta_label (cta_url already set by 0006).
    may_5 = _target(Mission, MAY_5_2026_DAY_OF_YEAR)
    if may_5 is not None:
        may_5.cta_label = CHAT_WITH_WIT_BOT_LABEL
        may_5.save(update_fields=['cta_label'])


def restore_may_8_to_10_missions(apps, schema_editor):
    Mission = apps.get_model('adoorback', 'Mission')
    for day_of_year, _prompt, _mtype, _cta_url, _cta_label, orig_prompt, orig_type in HOTFIXES:
        target = _target(Mission, day_of_year)
        if target is None:
            continue
        target.prompt = orig_prompt
        target.type = orig_type
        target.cta_url = ''
        target.cta_label = ''
        target.save(update_fields=['prompt', 'type', 'cta_url', 'cta_label'])

    may_5 = _target(Mission, MAY_5_2026_DAY_OF_YEAR)
    if may_5 is not None:
        may_5.cta_label = ''
        may_5.save(update_fields=['cta_label'])


class Migration(migrations.Migration):

    dependencies = [
        ('adoorback', '0007_add_cta_label_and_none_type'),
    ]

    operations = [
        migrations.RunPython(set_may_8_to_10_missions, restore_may_8_to_10_missions),
    ]
