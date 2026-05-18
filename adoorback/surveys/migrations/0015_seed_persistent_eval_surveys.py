# Schedule the 3 new persistent / editable surveys:
#
#   - feature_eval_w   (open-ended, no close) → opens Day 5 for w_first,
#                                                 Day 19 for q_first
#   - goal_comparison_p1 (open-ended, no close) → opens Day 15, all groups
#   - goal_comparison_p2 (open-ended, no close) → opens Day 29 (June 1),
#                                                 all groups
#
# All 3 use cadence='endpoint' since "open from day X, no upper bound,
# editable until manually closed" matches that cadence's
# semantics. allow_late=True is true-but-redundant when window_end is null.
#
# feature_eval_w gets TWO ScheduledSurvey rows for the same Survey row,
# differentiated by `target_user_group` (introduced in 0014). This lets
# the same content be scheduled once per group with different open dates.
from datetime import date

from django.db import migrations


# Phase boundary calendar — matches 0004's STUDY_START = May 4.
DAY_5 = date(2026, 5, 8)    # Day 5, w_first opens feature_eval_w
DAY_15 = date(2026, 5, 18)  # Day 15, all users open goal_comparison_p1
DAY_19 = date(2026, 5, 22)  # Day 19, q_first opens feature_eval_w
DAY_29 = date(2026, 6, 1)   # Day 29, all users open goal_comparison_p2


# (sequence_index, slug, window_start, target_user_group)
PERSISTENT_SCHEDULE = [
    (2, 'feature_eval_w',     DAY_5,  'group_w_first'),
    (3, 'feature_eval_w',     DAY_19, 'group_q_first'),
    (4, 'goal_comparison_p1', DAY_15, ''),
    (5, 'goal_comparison_p2', DAY_29, ''),
]


def seed_persistent(apps, schema_editor):
    """Schedule the editable / persistent surveys.

    Endpoint cadence + window_end=NULL = "opens day X, never closes
    automatically". Combined with Survey.editable=True (set in the YAML)
    and Survey.closed, users can submit and edit while the survey remains open.

    Idempotent — `update_or_create` keyed on (cadence, sequence_index).
    """
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    if not Survey.objects.exists():
        return

    for seq, slug, day, target_group in PERSISTENT_SCHEDULE:
        try:
            survey = Survey.objects.get(slug=slug)
        except Survey.DoesNotExist:
            # YAML for this slug isn't loaded yet — setup_survey_state will
            # retry once the YAML is loaded.
            continue
        ScheduledSurvey.objects.update_or_create(
            cadence='endpoint',
            sequence_index=seq,
            defaults={
                'survey': survey,
                'window_start': day,
                'window_end': None,  # never closes automatically
                'allow_late': True,
                'target_user_group': target_group,
            },
        )


def unseed_persistent(apps, schema_editor):
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    ScheduledSurvey.objects.filter(
        cadence='endpoint',
        sequence_index__in=[s for s, *_ in PERSISTENT_SCHEDULE],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0014_add_editable_closed_priority_target_group'),
    ]

    operations = [
        migrations.RunPython(seed_persistent, reverse_code=unseed_persistent),
    ]
