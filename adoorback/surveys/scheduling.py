"""Bucketing logic for the 4-week study schedule.

Pure query helpers — no view code. Consumed by `SurveyOfTheDayView` (today's
daily) and `SurveyIndexView` (the bucketed index).
"""
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Exists, OuterRef, Q, Subquery
from django.utils import timezone

from surveys.models import (
    CADENCE_DAILY, ScheduledSurvey, SurveyResponse, UserSurveyEmbeddedData,
)


# Saturdays = weekday 5, Sundays = weekday 6. Weekend skipping: standard
# SOTD surveys are not served on these days; daily_base diary continues.
_WEEKEND_DAYS = frozenset({5, 6})


def _today_la_7am():
    """Return the current 'logical date' using a 7 AM America/Los_Angeles boundary.
    Before 7 AM LA, this returns yesterday's date."""
    la_tz = ZoneInfo('America/Los_Angeles')
    return (timezone.now().astimezone(la_tz) - timedelta(hours=7)).date()


def _annotate_user_response(qs, user):
    """Annotate ScheduledSurvey queryset with `user_answered` (bool) and
    `user_submitted_at` (datetime or NULL)."""
    user_response_qs = SurveyResponse.objects.filter(
        user=user, survey=OuterRef('survey'),
    )
    return qs.annotate(
        user_answered=Exists(user_response_qs),
        user_submitted_at=Subquery(user_response_qs.values('submitted_at')[:1]),
    )


def _user_embedded_data(user) -> dict:
    """Snapshot of the user's embedded-data store as a plain dict.

    Used by `_skip_for_serving_condition` to evaluate the survey's skip rule
    without re-querying for every row in a multi-row check.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return {}
    return dict(
        UserSurveyEmbeddedData.objects.filter(user=user).values_list('key', 'value')
    )


def _skip_for_serving_condition(survey, user_data: dict) -> bool:
    """True when the survey's `serving_condition` matches the user's
    embedded data and the survey should NOT be served.

    Form: `{"skip_if_user_embedded_data": {<key>: <value>, ...}}`. Skip
    fires only when EVERY (key, value) pair matches. Any missing key, or
    any mismatch, means the survey is served as usual.
    """
    rule = (survey.serving_condition or {}).get('skip_if_user_embedded_data')
    if not isinstance(rule, dict) or not rule:
        return False
    for key, expected in rule.items():
        if user_data.get(key) != expected:
            return False
    return True


def routes_to_user(survey, user) -> bool:
    """True when the survey is currently routable to this user.

    Used by the dispatch layer to swap version-suffixed surveys based on the
    user's `user_group`. Slugs ending with `_w` go to W-first users; slugs
    ending with `_q` go to Q-first users; un-suffixed slugs route to all.

    Convention is `mid_study_w` / `mid_study_q` and `post_study_w` /
    `post_study_q`. Other slug suffixes are ignored.

    Public so view-layer routing (SurveyDetailView, SurveyResponseSubmitView)
    can apply the same predicate as the index/today-daily queries — keeps
    direct-URL access aligned with the natural flow.
    """
    slug = survey.slug
    user_group = getattr(user, 'user_group', '') or ''
    if slug.endswith('_w'):
        return user_group == 'group_w_first'
    if slug.endswith('_q'):
        return user_group == 'group_q_first'
    return True


def schedule_routes_to_user(scheduled, user) -> bool:
    """True when this scheduled row is visible to `user`.

    Two layers of routing — survey-level (slug-suffix `_w` / `_q`) AND
    schedule-level (`ScheduledSurvey.target_user_group`). The schedule-level
    field lets the SAME survey content be scheduled twice with different
    windows per group (e.g. feature_eval_w opens Day 5 for w_first /
    Day 19 for q_first), without needing two distinct slugs.
    """
    if not routes_to_user(scheduled.survey, user):
        return False
    target = getattr(scheduled, 'target_user_group', '') or ''
    if target:
        user_group = getattr(user, 'user_group', '') or ''
        if user_group != target:
            return False
    return True


# Backward-compat alias. Existing callers in this module still use the
# private name internally; outside callers should use `routes_to_user`.
_routes_to_user = routes_to_user


def _is_weekend_skipped(scheduled, today) -> bool:
    """True when this scheduled row is a SOTD-style daily that should be
    skipped on weekends.

    `daily_base` (the every-day diary) is exempt — research design is to keep
    the daily diary running through the weekend even when assessment SOTDs
    pause. Other daily rows are skipped on Sat/Sun.
    """
    if scheduled.cadence != CADENCE_DAILY:
        return False
    if scheduled.survey.slug == 'daily_base':
        return False
    return today.weekday() in _WEEKEND_DAYS


def get_today_daily(user):
    """Return today's daily ScheduledSurvey for `user`, or None.

    Filtering layers (after the basic cadence + date match):
      1. Version routing — surveys with `_w` / `_q` slug suffix only route
         to the user's matching `user_group`. Today's daily can be either
         a single un-suffixed survey (most common) or one of a w/q pair
         where the schedule has both rows on the same date.
      2. Weekend skip — non-`daily_base` daily SOTDs are not served on
         Sat/Sun.
      3. `serving_condition.skip_if_user_embedded_data` — surveys whose
         skip rule matches the user's embedded data are not returned.

    On weekdays of the study window, both daily_base (the diary) AND a
    SOTD instrument may be scheduled for the same date. The SOTD takes
    the Survey-of-the-Day card; daily_base still appears in the index
    and archive but isn't featured. Preference: any non-`daily_base`
    daily wins over `daily_base` on the same day.

    Returns the row regardless of whether the user has answered — the
    SurveyOfTheDay card on /share renders an answered-state UI ("Done /
    View results") once user_has_responded flips true.
    """
    today = _today_la_7am()
    candidates = list(
        _annotate_user_response(
            ScheduledSurvey.objects.filter(
                cadence=CADENCE_DAILY, window_start=today,
            ),
            user,
        ).select_related('survey')
    )
    user_data = _user_embedded_data(user)
    visible = []
    for sched in candidates:
        if not schedule_routes_to_user(sched, user):
            continue
        if _is_weekend_skipped(sched, today):
            continue
        if _skip_for_serving_condition(sched.survey, user_data):
            continue
        visible.append(sched)
    if not visible:
        return None
    # Prefer any non-`daily_base` row (i.e. an SOTD) on the same day; fall
    # back to daily_base when no SOTD is scheduled. Stable order so the
    # answered/unanswered display is consistent across requests.
    visible.sort(key=lambda s: (s.survey.slug == 'daily_base', s.sequence_index))
    return visible[0]


def get_survey_index(user):
    """Bucket every ScheduledSurvey row into available / late / completed for `user`.

    Returns dict[str, list[ScheduledSurvey]] with keys:
      - 'available_now':     window started, not closed, not answered
      - 'late_but_accepted': window closed, allow_late=True, not answered
      - 'completed':         user answered (any cadence, any date)

    Expired-and-hidden rows (window closed, allow_late=False, not answered —
    i.e. missed dailies) appear in NONE of the buckets and are never returned.

    Rows are also filtered to honor version routing (slugs ending `_w` /
    `_q` route to matching user_group only), weekend skip (non-daily_base
    dailies skipped on Sat/Sun), and `serving_condition` (skip rule).
    """
    today = _today_la_7am()
    qs = _annotate_user_response(
        ScheduledSurvey.objects.select_related('survey'), user,
    )

    available = list(
        qs.filter(window_start__lte=today)
          .filter(Q(window_end__isnull=True) | Q(window_end__gte=today))
          .filter(user_answered=False)
    )
    late = list(
        qs.filter(
            window_end__lt=today,
            allow_late=True,
            user_answered=False,
        )
    )
    completed = list(qs.filter(user_answered=True))

    user_data = _user_embedded_data(user)

    def _filter(rows):
        out = []
        for sched in rows:
            if not schedule_routes_to_user(sched, user):
                continue
            if _is_weekend_skipped(sched, today):
                continue
            if _skip_for_serving_condition(sched.survey, user_data):
                continue
            out.append(sched)
        return out

    # Within each bucket, surface the highest-priority surveys first so
    # users who don't have time for everything see the research-critical
    # surveys at the top of their list. Tie-break by window_start (earlier
    # first) then sequence_index for stable ordering.
    def _by_priority(rows):
        return sorted(
            rows,
            key=lambda s: (-s.survey.priority, s.window_start, s.sequence_index),
        )

    return {
        'available_now': _by_priority(_filter(available)),
        'late_but_accepted': _by_priority(_filter(late)),
        # Completed rows aren't filtered by serving_condition / weekend —
        # the user already answered, so they should still see the entry in
        # their archive. Version routing IS applied (a Q user shouldn't
        # see a W-only completion in their list, even if they somehow have one).
        'completed': _by_priority(
            [s for s in completed if schedule_routes_to_user(s, user)]
        ),
    }
