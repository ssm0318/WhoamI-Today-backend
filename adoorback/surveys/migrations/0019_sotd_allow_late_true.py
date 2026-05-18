# Flip `allow_late=True` on every SOTD daily-cadence row.
#
# SOTDs (Survey of the Day) are validated research instruments measuring
# stable traits — HEXACO personality facets, Need to Belong, Self-Report
# Habit Index, etc. Unlike `daily_base` (the diary that asks "how did you
# feel TODAY"), trait-level instruments don't lose meaning when answered
# post-hoc, so users who miss a day should be able to catch up via the
# `late_but_accepted` bucket on /surveys.
#
# Original schedule (0013_seed_sotd_schedule.py:87) set `allow_late=False`,
# treating SOTDs the same as the state-level daily diary. This migration
# corrects that for trait-level rows only.
#
# `daily_base` stays `allow_late=False` (it IS state-level — "how did you
# feel today" doesn't aggregate retrospectively).
#
# Idempotent: re-running has no effect (it just re-applies the same flag).

from django.db import migrations


SOTD_SLUGS = [
    'sotd_d01_honeymoon',
    'sotd_d02_rsds',
    'sotd_d03_iscs_bond',
    'sotd_d04_iscs_bridge',
    'sotd_d05_rsq',
    'sotd_d08_singelis_ind',
    'sotd_d09_singelis_int',
    'sotd_d10_woodAS',
    'sotd_d11_ucla8',
    'sotd_d12_ntb',
    'sotd_d15_shi',
    'sotd_d16_hexaco_hh',
    'sotd_d17_hexaco_em',
    'sotd_d18_hexaco_ex',
    'sotd_d19_hexaco_ag',
    'sotd_d22_hexaco_co',
    'sotd_d23_hexaco_op',
    'sotd_d24_ceii',
    'sotd_d25_iuipc',
    'sotd_d26_transition',
]


def forward(apps, _):
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    ScheduledSurvey.objects.filter(
        cadence='daily',
        survey__slug__in=SOTD_SLUGS,
    ).update(allow_late=True)


def reverse(apps, _):
    ScheduledSurvey = apps.get_model('surveys', 'ScheduledSurvey')
    ScheduledSurvey.objects.filter(
        cadence='daily',
        survey__slug__in=SOTD_SLUGS,
    ).update(allow_late=False)


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0018_reschedule_d02_rsds_to_may_7'),
    ]

    operations = [
        migrations.RunPython(forward, reverse_code=reverse),
    ]
