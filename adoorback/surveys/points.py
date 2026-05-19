from __future__ import annotations

from dataclasses import dataclass

from surveys.models import PointAward, ScheduledSurvey, Survey, SurveyResponse
from surveys.reimbursement_config import (
    INTERVIEW_SIGNUP_MAX_POINTS, POINTS_PER_DOLLAR, WIT_BOT_AUDIT_MAX_POINTS,
)
from surveys.retired import is_retired_survey_slug
from surveys.scheduling import (
    _is_weekend_skipped, _skip_for_serving_condition, _today_la_7am,
    _user_embedded_data, schedule_routes_to_user,
)


@dataclass(frozen=True)
class SubmitScheduleResolution:
    scheduled_survey: ScheduledSurvey | None
    rejection: str | None = None


def _is_currently_open(scheduled: ScheduledSurvey, today) -> bool:
    if scheduled.window_start > today:
        return False
    if scheduled.window_end is None:
        return True
    return scheduled.window_end >= today


def _is_late_accepted(scheduled: ScheduledSurvey, today) -> bool:
    return (
        scheduled.window_end is not None
        and scheduled.window_end < today
        and scheduled.allow_late
    )


def _answerable_sort_key(scheduled: ScheduledSurvey, today):
    is_late = _is_late_accepted(scheduled, today)
    return (
        1 if is_late else 0,
        -scheduled.window_start.toordinal(),
        scheduled.sequence_index,
    )


def resolve_submit_scheduled_survey(user, survey: Survey) -> SubmitScheduleResolution:
    """Find the scheduled opportunity a submit should credit, if any.

    Unscheduled surveys remain answerable and return ``scheduled_survey=None``.
    Scheduled surveys must route to the viewer and be currently open or
    late-accepted.
    """
    rows = list(ScheduledSurvey.objects.filter(survey=survey).select_related('survey'))
    if not rows:
        return SubmitScheduleResolution(scheduled_survey=None)

    today = _today_la_7am()
    routed = [row for row in rows if schedule_routes_to_user(row, user)]
    if not routed:
        return SubmitScheduleResolution(scheduled_survey=None, rejection='not_routed')

    user_data = _user_embedded_data(user)
    visible = [
        row for row in routed
        if not _is_weekend_skipped(row, today)
        and not _skip_for_serving_condition(row.survey, user_data)
    ]
    if not visible:
        return SubmitScheduleResolution(scheduled_survey=None, rejection='not_routed')

    answerable = [
        row for row in visible
        if _is_currently_open(row, today) or _is_late_accepted(row, today)
    ]
    if answerable:
        answerable.sort(key=lambda row: _answerable_sort_key(row, today))
        return SubmitScheduleResolution(scheduled_survey=answerable[0])

    if any(row.window_start > today for row in visible):
        return SubmitScheduleResolution(scheduled_survey=None, rejection='future')
    return SubmitScheduleResolution(scheduled_survey=None, rejection='expired')


def point_prereq_lock_for_user(survey: Survey, user) -> dict | None:
    prereq_slug = survey.point_prereq_slug or ''
    if not prereq_slug:
        return None
    if SurveyResponse.objects.filter(user=user, survey__slug=prereq_slug).exists():
        return None
    prereq = Survey.objects.filter(slug=prereq_slug).first()
    return {
        'slug': prereq_slug,
        'title_en': prereq.title_en if prereq else '',
        'title_ko': prereq.title_ko if prereq else '',
    }


def serialize_point_award(award: PointAward | None) -> dict | None:
    if award is None:
        return None
    return {
        'awarded_points': award.awarded_points,
        'adjusted_points': award.adjusted_points,
        'effective_points': award.effective_points,
        'note': award.note,
    }


def serialize_reimbursement_award(award: PointAward) -> dict:
    scheduled = award.scheduled_survey
    response = award.response
    survey = None
    if scheduled is not None:
        survey = scheduled.survey
    elif response is not None:
        survey = response.survey

    title_en = award.source_slug
    title_ko = award.source_slug
    if survey is not None:
        from surveys.tokens import build_token_map, substitute
        tokens = build_token_map(survey, viewer=award.user)
        title_en = substitute(survey.title_en, tokens)
        title_ko = substitute(survey.title_ko, tokens)
    elif award.source_kind == PointAward.SOURCE_WIT_BOT_AUDIT:
        title_en = 'Wit_bot audit pass'
        title_ko = 'Wit_bot audit pass'
    elif award.source_kind == PointAward.SOURCE_INTERVIEW_SIGNUP:
        title_en = 'Interview signup'
        title_ko = 'Interview signup'

    submitted_at = response.submitted_at if response is not None else award.created_at
    return {
        'source_kind': award.source_kind,
        'source_slug': award.source_slug,
        'scheduled_survey_id': scheduled.id if scheduled is not None else None,
        'title_en': title_en,
        'title_ko': title_ko,
        'cadence': scheduled.cadence if scheduled is not None else None,
        'window_start': scheduled.window_start if scheduled is not None else None,
        'window_end': scheduled.window_end if scheduled is not None else None,
        'awarded_points': award.awarded_points,
        'adjusted_points': award.adjusted_points,
        'effective_points': award.effective_points,
        'note': award.note,
        'submitted_at': submitted_at,
    }


def get_point_award_for_scheduled(user, scheduled: ScheduledSurvey) -> PointAward | None:
    return (
        PointAward.objects
        .filter(
            user=user,
            source_kind=PointAward.SOURCE_SURVEY,
            scheduled_survey=scheduled,
        )
        .select_related('scheduled_survey__survey', 'response__survey')
        .first()
    )


def get_point_award_for_survey(user, survey: Survey, *, scheduled_survey=None) -> PointAward | None:
    if scheduled_survey is not None:
        return get_point_award_for_scheduled(user, scheduled_survey)
    return (
        PointAward.objects
        .filter(
            user=user,
            source_kind=PointAward.SOURCE_SURVEY,
            source_slug=survey.slug,
        )
        .select_related('scheduled_survey__survey', 'response__survey')
        .order_by('-created_at', '-id')
        .first()
    )


def create_survey_point_award(
    *,
    user,
    survey: Survey,
    response: SurveyResponse,
    scheduled_survey: ScheduledSurvey | None,
) -> PointAward | None:
    if survey.point_value <= 0:
        return None

    lock = point_prereq_lock_for_user(survey, user)
    if lock is None:
        awarded_points = survey.point_value
        note = ''
    else:
        awarded_points = 0
        note = f"Prereq {lock['slug']} not completed at submit time."

    defaults = {
        'source_slug': survey.slug,
        'response': response,
        'awarded_points': awarded_points,
        'note': note,
    }
    if scheduled_survey is not None:
        award, _created = PointAward.objects.get_or_create(
            user=user,
            source_kind=PointAward.SOURCE_SURVEY,
            scheduled_survey=scheduled_survey,
            defaults=defaults,
        )
        return award

    award, _created = PointAward.objects.get_or_create(
        user=user,
        source_kind=PointAward.SOURCE_SURVEY,
        response=response,
        defaults=defaults,
    )
    return award


def _visible_scheduled_surveys_for_points(user):
    today = _today_la_7am()
    user_data = _user_embedded_data(user)
    rows = ScheduledSurvey.objects.select_related('survey').order_by(
        'window_start', 'cadence', 'sequence_index',
    )
    visible = []
    for scheduled in rows:
        survey = scheduled.survey
        if is_retired_survey_slug(survey.slug):
            continue
        if not schedule_routes_to_user(scheduled, user):
            continue
        if _is_weekend_skipped(scheduled, scheduled.window_start):
            continue
        if _skip_for_serving_condition(survey, user_data):
            continue
        visible.append(scheduled)
    return visible


def available_max_for_user(user) -> int:
    total = WIT_BOT_AUDIT_MAX_POINTS + INTERVIEW_SIGNUP_MAX_POINTS
    for scheduled in _visible_scheduled_surveys_for_points(user):
        total += scheduled.survey.point_value
    return total


def pending_prereqs_for_user(user) -> list[dict]:
    pending = []
    for scheduled in _visible_scheduled_surveys_for_points(user):
        survey = scheduled.survey
        if survey.point_value <= 0:
            continue
        lock = point_prereq_lock_for_user(survey, user)
        if lock is None:
            continue
        pending.append({
            'survey_slug': survey.slug,
            'scheduled_survey_id': scheduled.id,
            'title_en': survey.title_en,
            'title_ko': survey.title_ko,
            'potential_points': survey.point_value,
            'prereq_slug': lock['slug'],
            'prereq_title_en': lock['title_en'],
            'prereq_title_ko': lock['title_ko'],
        })
    return pending


def reimbursement_state_for_user(user) -> dict:
    awards = list(
        PointAward.objects
        .filter(user=user)
        .select_related('scheduled_survey__survey', 'response__survey')
        .order_by('-created_at', '-id')
    )
    provisional_total = sum(award.awarded_points for award in awards)
    adjusted_total = sum(award.effective_points for award in awards)
    return {
        'provisional_total': provisional_total,
        'adjusted_total': adjusted_total,
        'available_max': available_max_for_user(user),
        'dollar_estimate_cents': round(adjusted_total * 100 / POINTS_PER_DOLLAR),
        'points_per_dollar': POINTS_PER_DOLLAR,
        'awards': [serialize_reimbursement_award(award) for award in awards],
        'pending_prereqs': pending_prereqs_for_user(user),
    }


def credit_manual_award(*, user, source_kind: str, source_slug: str, points: int, note: str = ''):
    award, _created = PointAward.objects.get_or_create(
        user=user,
        source_kind=source_kind,
        source_slug=source_slug,
        response=None,
        scheduled_survey=None,
        defaults={
            'awarded_points': points,
            'note': note,
        },
    )
    return award
