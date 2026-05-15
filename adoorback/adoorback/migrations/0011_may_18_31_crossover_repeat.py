"""Crossover study: May 18-31 repeats May 4-17 missions.

The 4-week study has a crossover design where week 1-2 (May 4-17, days 1-14)
content repeats in week 3-4 (May 18-31, days 15-28). This migration copies
the (prompt, type, cta_url, cta_label) of positions 4-17 onto positions
18-29 + 0 + 1 (wrap-around for May 30/31).

Position mapping:
  pos 18 <- pos 4   (May 18 mirrors May 4)
  pos 19 <- pos 5   (May 19 mirrors May 5 — wit_bot CTA preserved)
  pos 20 <- pos 6   (May 20 mirrors May 6 — type=question)
  pos 21 <- pos 7
  pos 22 <- pos 8   (May 22 mirrors May 8 — invite CTA preserved)
  pos 23 <- pos 9
  pos 24 <- pos 10  (May 24 mirrors May 10 — type=none + discover CTA)
  pos 25 <- pos 11
  pos 26 <- pos 12
  pos 27 <- pos 13
  pos 28 <- pos 14
  pos 29 <- pos 15
  pos 0  <- pos 16  (May 30 wraps; overwrites the original 'song that matches mood' seed)
  pos 1  <- pos 17  (May 31 wraps; overwrites the 0003 community-greeting hotfix)

Reverse restores each position to the value it held BEFORE this migration
applied (i.e., the cumulative result of 0002-0010).
"""
from django.db import migrations


# Final state at positions 4-17 after migrations 0003-0010. These are the
# values we COPY into positions 18-29 + 0 + 1.
SOURCE_BY_POS = {
    4: {
        'prompt': (
            "Today is the first day of the WIT study! Share your first post on "
            "the platform and leave your first emoji reaction. Welcome aboard, "
            "hello world."
        ),
        'type': 'text',
        'cta_url': '',
        'cta_label': '',
    },
    5: {
        'prompt': (
            "You're an official WIT user — congrats! Talk to wit_bot to finish "
            "onboarding."
        ),
        'type': 'text',
        'cta_url': '/users/7/chat',
        'cta_label': 'Chat with wit_bot',
    },
    6: {
        'prompt': (
            "Ask a question that you're curious to hear other WIT members' "
            "answers to."
        ),
        'type': 'question',
        'cta_url': '',
        'cta_label': '',
    },
    7: {
        'prompt': (
            "You've been using WIT for three days now. What's your favorite "
            "feature on the platform so far, and why? Show it off."
        ),
        'type': 'text',
        'cta_url': '',
        'cta_label': '',
    },
    8: {
        'prompt': (
            'Who in your life would "get" WIT? Invite someone you think would '
            'appreciate it most using your personal invite code, and share a '
            'bit about the person. (Heads-up: WIT is invite-only from current '
            'users for the foreseeable future to maintain community health.)'
        ),
        'type': 'text',
        'cta_url': '/friends/explore?tab=recommended',
        'cta_label': 'Find friends to invite',
    },
    9: {
        'prompt': (
            "What's one feature you wish WIT had? Share it with the community — "
            "we're listening."
        ),
        'type': 'text',
        'cta_url': '',
        'cta_label': '',
    },
    10: {
        'prompt': (
            "Leave a reaction on three different friends' posts today. Try out "
            "whatever feels right — a private comment, an emoji, a reaction to "
            "a check-in."
        ),
        'type': 'none',
        'cta_url': '/discover',
        'cta_label': 'Browse Daily Digest',
    },
    11: {
        'prompt': (
            "Hand-draw your own face. 60 seconds, whatever pen you grab, "
            "no retakes. Share the first attempt."
        ),
        'type': 'text',
        'cta_url': '',
        'cta_label': '',
    },
    12: {
        'prompt': (
            "Share the most random meme you saw today. Doesn't need to be "
            "funny. Doesn't need context."
        ),
        'type': 'text',
        'cta_url': '',
        'cta_label': '',
    },
    13: {
        'prompt': (
            "Open your camera roll and share the 5th photo. Tell us a bit "
            "about it — when, where, why you took it."
        ),
        'type': 'text',
        'cta_url': '',
        'cta_label': '',
    },
    14: {
        'prompt': (
            "Hand-write any single sentence — a thought, a lyric, something "
            "you'd put on a sticker. Take a photo and share."
        ),
        'type': 'text',
        'cta_url': '',
        'cta_label': '',
    },
    15: {
        'prompt': (
            "Take one photo of three random objects within arm's reach of "
            "you right now."
        ),
        'type': 'text',
        'cta_url': '',
        'cta_label': '',
    },
    16: {
        'prompt': "Take a photo of your shoes wherever they are right now.",
        'type': 'text',
        'cta_url': '',
        'cta_label': '',
    },
    17: {
        'prompt': (
            "Open your camera and take a photo of the ceiling above you right now."
        ),
        'type': 'text',
        'cta_url': '',
        'cta_label': '',
    },
}


# State at positions 18-29 + 0 + 1 BEFORE this migration runs (i.e., the
# cumulative result of 0002-0010). Used by the reverse function to restore.
PRIOR_STATE = {
    # 0010 overrides
    18: {'prompt': "Photo of your current setup — desk, couch, kitchen counter, wherever you happen to be right now.", 'type': 'text', 'cta_url': '', 'cta_label': ''},
    19: {'prompt': "Share a single song lyric (just the line, no context) you've had stuck in your head this week.", 'type': 'text', 'cta_url': '', 'cta_label': ''},
    20: {'prompt': "Doodle the first object you see when you look up from your phone. 30 seconds, single pen, no retakes.", 'type': 'text', 'cta_url': '', 'cta_label': ''},
    # Untouched seed
    21: {'prompt': "Share your current desktop or phone wallpaper", 'type': 'text', 'cta_url': '', 'cta_label': ''},
    # 0010 override
    22: {'prompt': "Find a sticker on something you own — laptop, water bottle, notebook, anywhere. Close-up photo.", 'type': 'text', 'cta_url': '', 'cta_label': ''},
    # Untouched seed (song type)
    23: {'prompt': "Share a song that gives you energy", 'type': 'song', 'cta_url': '', 'cta_label': ''},
    # 0010 overrides
    24: {'prompt': "Take a photo of the inside of your fridge or freezer. No curation.", 'type': 'text', 'cta_url': '', 'cta_label': ''},
    25: {'prompt': "Find the oldest photo on your phone and share it.", 'type': 'text', 'cta_url': '', 'cta_label': ''},
    26: {'prompt': "Take a screenshot of your phone's home screen. Show us how cluttered (or not) it is.", 'type': 'text', 'cta_url': '', 'cta_label': ''},
    27: {'prompt': "Take a photo of a piece of paper, sticky note, or notepad you're using right now.", 'type': 'text', 'cta_url': '', 'cta_label': ''},
    # Untouched seed (song type)
    28: {'prompt': "Share a song that calms you down", 'type': 'song', 'cta_url': '', 'cta_label': ''},
    # 0010 override
    29: {'prompt': "Take a photo of your hands — whatever they're doing or holding right now.", 'type': 'text', 'cta_url': '', 'cta_label': ''},
    # Untouched seed (song type)
    0: {'prompt': "Share a song that matches your mood right now", 'type': 'song', 'cta_url': '', 'cta_label': ''},
    # 0003 hotfix
    1: {'prompt': "Say hi to the WIT user community! Share a public post with something that represents you—a drawing, a favorite item, your pet, etc.", 'type': 'text', 'cta_url': '', 'cta_label': ''},
}


# (target_position, source_position)
COPY_MAP = [
    (18, 4),
    (19, 5),
    (20, 6),
    (21, 7),
    (22, 8),
    (23, 9),
    (24, 10),
    (25, 11),
    (26, 12),
    (27, 13),
    (28, 14),
    (29, 15),
    (0, 16),   # May 30 wraps
    (1, 17),   # May 31 wraps
]


_FIELDS = ['prompt', 'type', 'cta_url', 'cta_label']


def _mission_at(Mission, position):
    missions = list(Mission.objects.order_by('id'))
    if not missions:
        return None
    return missions[position % len(missions)]


def _apply(target, state):
    for field in _FIELDS:
        setattr(target, field, state[field])
    target.save(update_fields=_FIELDS)


def copy_days_4_17_to_18_31(apps, schema_editor):
    Mission = apps.get_model('adoorback', 'Mission')
    for target_pos, source_pos in COPY_MAP:
        target = _mission_at(Mission, target_pos)
        if target is None:
            continue
        _apply(target, SOURCE_BY_POS[source_pos])


def restore_prior_state(apps, schema_editor):
    Mission = apps.get_model('adoorback', 'Mission')
    for target_pos, _source_pos in COPY_MAP:
        target = _mission_at(Mission, target_pos)
        if target is None:
            continue
        _apply(target, PRIOR_STATE[target_pos])


class Migration(migrations.Migration):

    dependencies = [
        ('adoorback', '0010_may_16_to_29_qotd_overrides'),
    ]

    operations = [
        migrations.RunPython(copy_days_4_17_to_18_31, restore_prior_state),
    ]
