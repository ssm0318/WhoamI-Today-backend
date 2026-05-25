"""May 26 mission -> "update your interest chips" action mission.

Replaces position 26 (the May 26 'random meme' photo prompt seeded by
0011's crossover repeat) with a `type='none'` action mission that
deep-links to the interests editor. Drives the ~half of participants who
still have zero interest chips to fill them in.

`type='none'` suppresses the post-creation "Do it" flow; the Share-tab
mission card and the Discover digest instead surface a CTA button that
navigates straight to `cta_url`. `share_results=False` because an action
mission produces no posts, so there's nothing for the digest's
yesterday-mission card to show.

Forward sets position 26 to the interests action mission.
Reverse restores position 26 to its prior state (the result of 0011 —
day-12's 'random meme' text prompt). Verified against prod (whoamitoday_
merged): 30 missions, so 26 % 30 = 26 = mission id 27, type=text,
share_results=true, empty cta — matching PRIOR_STATE below.
"""
from django.db import migrations


POSITION = 26

NEW_STATE = {
    'prompt': "Update your profile to share your interests with your friends.",
    'type': 'none',
    'share_results': False,
    'cta_url': '/settings/edit-profile?tab=interests',
    'cta_label': 'Add your interests',
}

PRIOR_STATE = {
    'prompt': (
        "Share the most random meme you saw today. Doesn't need to be "
        "funny. Doesn't need context."
    ),
    'type': 'text',
    'share_results': True,
    'cta_url': '',
    'cta_label': '',
}

_FIELDS = ['prompt', 'type', 'share_results', 'cta_url', 'cta_label']


def _mission_at(Mission, position):
    missions = list(Mission.objects.order_by('id'))
    if not missions:
        return None
    return missions[position % len(missions)]


def _apply(target, state):
    for field in _FIELDS:
        setattr(target, field, state[field])
    target.save(update_fields=_FIELDS)


def set_interest_mission(apps, schema_editor):
    Mission = apps.get_model('adoorback', 'Mission')
    target = _mission_at(Mission, POSITION)
    if target is None:
        return
    _apply(target, NEW_STATE)


def restore_prior_state(apps, schema_editor):
    Mission = apps.get_model('adoorback', 'Mission')
    target = _mission_at(Mission, POSITION)
    if target is None:
        return
    _apply(target, PRIOR_STATE)


class Migration(migrations.Migration):

    dependencies = [
        ('adoorback', '0011_may_18_31_crossover_repeat'),
    ]

    operations = [
        migrations.RunPython(set_interest_mission, restore_prior_state),
    ]
