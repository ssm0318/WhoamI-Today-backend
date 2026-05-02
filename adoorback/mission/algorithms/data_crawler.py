import datetime

from mission.models import Mission

NUM_DAILY_MISSIONS = 1


def select_daily_missions(set_date=None):
    """Pick random Mission(s) for set_date (default tomorrow). Skip if already scheduled.

    The skip-if-scheduled branch lets the curated study schedule
    (mission/migrations/0002_seed_study_schedule.py) pre-claim 43 specific
    dates without the cron stomping on them.
    """
    if not set_date:
        set_date = datetime.date.today() + datetime.timedelta(days=1)

    if Mission.objects.filter(selected_dates__contains=[set_date]).exists():
        return

    missions = Mission.objects.filter(selected=False).order_by('?')[:NUM_DAILY_MISSIONS]

    if missions.count() < NUM_DAILY_MISSIONS:
        # Pool exhausted: reset selected=False on missions whose selected_dates is empty.
        # Curated missions keep selected=True so they don't get re-picked randomly.
        # NOTE: the filter selected_dates=[] is a partial protection — randomly-picked
        # missions (which have a non-empty selected_dates) won't reset either, so over
        # the long term the cron may run out of pickable missions. Revisit with an
        # explicit is_curated flag once the curated window is live.
        Mission.objects.filter(selected_dates=[]).update(selected=False)
        missions = list(missions) + list(
            Mission.objects.filter(selected=False).order_by('?')[
                : (NUM_DAILY_MISSIONS - missions.count())
            ]
        )

    for mission in missions:
        mission.selected_dates.append(set_date)
        mission.selected = True
        mission.save(update_fields=['selected_dates', 'selected'])
