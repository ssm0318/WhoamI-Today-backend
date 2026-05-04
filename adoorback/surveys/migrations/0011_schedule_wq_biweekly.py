# Replace the legacy biweekly schedule (single mid_study / post_study slugs)
# with the version-suffixed pair (mid_study_w/q + post_study_w/q). Each
# variant is scheduled on its phase boundary day; the routing layer
# (`surveys.scheduling.routes_to_user`) maps each user to their group's
# variant at request time.
#
# Idempotent: re-running calls update_or_create on (cadence, sequence_index).
# Short-circuits when the new W/Q surveys aren't loaded yet — the YAML must
# be loaded first via load_surveys (or setup_survey_state, which orders the
# steps correctly).
from datetime import date

from django.db import migrations


# Phase boundary calendar — same as 0004_seed_study_schedule's STUDY_START.
# Kept here as literals (rather than imported) so the migration is self-
# contained and won't drift if 0004 is later parameterized.
PRE_STUDY = date(2026, 5, 2)
DAY_14 = date(2026, 5, 16)
DAY_28 = date(2026, 5, 30)


# (sequence_index, slug, window_start)
WQ_BIWEEKLY_SCHEDULE = [
    (1, 'pre_study',     PRE_STUDY),
    (2, 'mid_study_w',   DAY_14),
    (3, 'mid_study_q',   DAY_14),
    (4, 'post_study_w',  DAY_28),
    (5, 'post_study_q',  DAY_28),
]


def seed_wq_biweekly(apps, schema_editor):
    """Replace the biweekly schedule rows with W/Q variants.

    The original 0004 migration created biweekly seq 1=pre_study,
    2=mid_study, 3=post_study (singular slugs). This rewrite uses seq
    1=pre_study, 2=mid_study_w, 3=mid_study_q, 4=post_study_w,
    5=post_study_q. The `routes_to_user` predicate decides which variant
    each user sees on the phase boundary day.

    Pattern matches `0004_seed_study_schedule.seed_schedule`: short-circuits
    on a fresh DB (no Survey rows), so YAML must be loaded first.

    Re-runnable: existing rows update_or_create by (cadence, seq); orphaned
    rows from the legacy schedule are removed defensively at the start.
    """
    Survey = apps.get_model('surveys', 'Survey')
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    if not Survey.objects.exists():
        return

    # Drop any biweekly rows whose sequence_index is in [1, 5] but whose
    # current slug isn't in the target list — these are leftover legacy
    # rows (mid_study, post_study) that we're replacing.
    target_slugs = {slug for _, slug, _ in WQ_BIWEEKLY_SCHEDULE}
    legacy_rows = (
        ScheduledSurvey.objects
        .filter(cadence='biweekly', sequence_index__in=[s for s, *_ in WQ_BIWEEKLY_SCHEDULE])
        .exclude(survey__slug__in=target_slugs)
    )
    legacy_rows.delete()

    for seq, slug, day in WQ_BIWEEKLY_SCHEDULE:
        try:
            survey = Survey.objects.get(slug=slug)
        except Survey.DoesNotExist:
            # YAML for this variant isn't loaded yet. Skip — the next call
            # to setup_survey_state will retry once the YAML is loaded.
            continue
        ScheduledSurvey.objects.update_or_create(
            cadence='biweekly', sequence_index=seq,
            defaults={
                'survey': survey,
                'window_start': day,
                'window_end': day,
                'allow_late': True,
            },
        )


def unseed_wq_biweekly(apps, schema_editor):
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    ScheduledSurvey.objects.filter(
        cadence='biweekly',
        sequence_index__in=[s for s, *_ in WQ_BIWEEKLY_SCHEDULE],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0010_drop_unique_response_per_user_per_survey'),
    ]

    operations = [
        migrations.RunPython(seed_wq_biweekly, reverse_code=unseed_wq_biweekly),
    ]
