"""Bucketing logic for the 4-week study schedule.

Pure query helpers — no view code. Consumed by `SurveyOfTheDayView` (today's
daily) and `SurveyIndexView` (the bucketed index).
"""
from datetime import date

from django.db.models import Exists, OuterRef, Q, Subquery

from surveys.models import CADENCE_DAILY, ScheduledSurvey, SurveyResponse


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


def get_today_daily(user):
    """Return today's daily ScheduledSurvey for `user`, or None.

    Returns the row regardless of whether the user has answered — the
    SurveyOfTheDay card on /share renders an answered-state UI ("Done /
    View results") once user_has_responded flips true. Hiding the card
    after answering led to confusion ("did I do it? was it submitted?")
    and a stale-cache window where users could navigate back into the
    answer form and hit a 409.
    """
    today = date.today()
    return (
        _annotate_user_response(
            ScheduledSurvey.objects.filter(
                cadence=CADENCE_DAILY, window_start=today,
            ),
            user,
        )
        .select_related('survey')
        .first()
    )


def get_survey_index(user):
    """Bucket every ScheduledSurvey row into available / late / completed for `user`.

    Returns dict[str, list[ScheduledSurvey]] with keys:
      - 'available_now':     window started, not closed, not answered
      - 'late_but_accepted': window closed, allow_late=True, not answered
      - 'completed':         user answered (any cadence, any date)

    Expired-and-hidden rows (window closed, allow_late=False, not answered —
    i.e. missed dailies) appear in NONE of the buckets and are never returned.
    """
    today = date.today()
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

    return {
        'available_now': available,
        'late_but_accepted': late,
        'completed': completed,
    }
