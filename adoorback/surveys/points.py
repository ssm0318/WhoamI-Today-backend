from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from zoneinfo import ZoneInfo

from surveys.models import (
    DropoutSurveyResponse, PointAward, ScheduledSurvey, Survey, SurveyResponse,
)
from surveys.reimbursement_config import (
    APP_USAGE_PHASES, DROPOUT_SURVEY_URL, FRIEND_INVITE_MAX_POINTS,
    INTERVIEW_SIGNUP_DEADLINE, INTERVIEW_SIGNUP_MAX_POINTS, INTERVIEW_SIGNUP_URL,
    POINTS_PER_DOLLAR, WIT_BOT_AUDIT_PHASES,
)
from surveys.retired import is_retired_survey_slug
from surveys.scheduling import (
    _skip_for_serving_condition, _today_la_7am, _user_embedded_data,
    schedule_routes_to_user,
)


@dataclass(frozen=True)
class SubmitScheduleResolution:
    scheduled_survey: ScheduledSurvey | None
    rejection: str | None = None


@dataclass(frozen=True)
class SurveyPointAwardBackfillResult:
    scanned: int
    created: int
    skipped_existing: int


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
        if not _skip_for_serving_condition(row.survey, user_data)
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


def wit_bot_audit_version_for_group(user_group: str, phase: int) -> str:
    if phase == 1:
        return 'version_q' if user_group == 'group_q_first' else 'version_w'
    if phase == 2:
        return 'version_w' if user_group == 'group_q_first' else 'version_q'
    raise ValueError(f'Unsupported Wit_bot audit phase: {phase}')


def wit_bot_audit_source_for_phase(phase: int) -> dict:
    try:
        return WIT_BOT_AUDIT_PHASES[phase]
    except KeyError as exc:
        raise ValueError(f'Unsupported Wit_bot audit phase: {phase}') from exc


def wit_bot_audit_phase_for_source_slug(source_slug: str) -> int | None:
    for phase, source in WIT_BOT_AUDIT_PHASES.items():
        if source['source_slug'] == source_slug:
            return phase
    return None


def app_usage_source_for_phase(phase: int) -> dict:
    try:
        return APP_USAGE_PHASES[phase]
    except KeyError as exc:
        raise ValueError(f'Unsupported app usage phase: {phase}') from exc


def app_usage_phase_for_source_slug(source_slug: str) -> int | None:
    for phase, source in APP_USAGE_PHASES.items():
        if source['source_slug'] == source_slug:
            return phase
    return None


def _version_label(version: str) -> str:
    if version == 'version_q':
        return 'Ver.Q'
    if version == 'version_w':
        return 'Ver.W'
    return version


def _wit_bot_audit_title(award: PointAward, language: str) -> str:
    phase = wit_bot_audit_phase_for_source_slug(award.source_slug)
    if phase is None:
        return 'Wit_bot audit pass'
    source = wit_bot_audit_source_for_phase(phase)
    title = source[f'title_{language}']
    version = wit_bot_audit_version_for_group(award.user.user_group, phase)
    return f'{title} ({_version_label(version)})'


def _computed_wit_bot_audit_awards_for_user(user, existing_awards: list[PointAward]) -> list[dict]:
    from chat.models import WitBotConversationState

    existing_source_slugs = {
        award.source_slug
        for award in existing_awards
        if award.source_kind == PointAward.SOURCE_WIT_BOT_AUDIT
    }
    state = WitBotConversationState.objects.filter(user=user).first()
    if state is None:
        return []

    context = state.context or {}
    awards = []
    for phase, source in WIT_BOT_AUDIT_PHASES.items():
        source_slug = source['source_slug']
        if source_slug in existing_source_slugs:
            continue

        version = wit_bot_audit_version_for_group(user.user_group, phase)
        version_context = context.get(version) or {}
        audit = version_context.get('audit') or {}
        if audit.get('last_missing_count') != 0:
            continue

        points = source['max_points']
        awards.append({
            'source_kind': PointAward.SOURCE_WIT_BOT_AUDIT,
            'source_slug': source_slug,
            'scheduled_survey_id': None,
            'title_en': f"{source['title_en']} ({_version_label(version)})",
            'title_ko': f"{source['title_ko']} ({_version_label(version)})",
            'cadence': None,
            'window_start': None,
            'window_end': None,
            'awarded_points': points,
            'adjusted_points': None,
            'effective_points': points,
            'note': '',
            'submitted_at': state.updated_at,
        })
    return awards


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
        title_en, title_ko = _survey_titles_for_user(survey, award.user)
    elif award.source_kind == PointAward.SOURCE_WIT_BOT_AUDIT:
        title_en = _wit_bot_audit_title(award, 'en')
        title_ko = _wit_bot_audit_title(award, 'ko')
    elif award.source_kind == PointAward.SOURCE_APP_USAGE:
        phase = app_usage_phase_for_source_slug(award.source_slug)
        if phase is not None:
            source = app_usage_source_for_phase(phase)
            title_en = source['title_en']
            title_ko = source['title_ko']
    elif award.source_kind == PointAward.SOURCE_INTERVIEW_SIGNUP:
        title_en = 'Interview'
        title_ko = 'Interview'
    elif award.source_kind == PointAward.SOURCE_FRIEND_INVITE:
        title_en = 'Friend invitations'
        title_ko = '친구 초대'
    elif award.source_kind == PointAward.SOURCE_RESEARCHER_ADJUSTMENT:
        title_en = _source_slug_title(award.source_slug)
        title_ko = title_en

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


def _survey_titles_for_user(survey: Survey, user) -> tuple[str, str]:
    from surveys.tokens import build_token_map, substitute

    tokens = build_token_map(survey, viewer=user)
    return (
        substitute(survey.title_en, tokens),
        substitute(survey.title_ko, tokens),
    )


def _source_slug_title(source_slug: str) -> str:
    return ' '.join(
        part.capitalize()
        for part in str(source_slug or '').replace('-', '_').split('_')
        if part
    )


def _logical_response_date(response: SurveyResponse):
    la_tz = ZoneInfo('America/Los_Angeles')
    return (response.submitted_at.astimezone(la_tz) - timedelta(hours=7)).date()


def _scheduled_survey_for_existing_response(response: SurveyResponse) -> ScheduledSurvey | None:
    rows = [
        row
        for row in (
            ScheduledSurvey.objects
            .filter(survey=response.survey)
            .select_related('survey')
        )
        if schedule_routes_to_user(row, response.user)
    ]
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]

    logical_date = _logical_response_date(response)
    matching_window = [
        row for row in rows
        if row.window_start <= logical_date and (
            row.window_end is None or row.window_end >= logical_date
        )
    ]
    if matching_window:
        return sorted(matching_window, key=lambda row: (row.window_start, row.sequence_index))[0]

    return None


def _point_prereq_lock_for_response(response: SurveyResponse) -> dict | None:
    prereq_slug = response.survey.point_prereq_slug or ''
    if not prereq_slug:
        return None
    if SurveyResponse.objects.filter(
        user=response.user,
        survey__slug=prereq_slug,
        submitted_at__lte=response.submitted_at,
    ).exists():
        return None
    prereq = Survey.objects.filter(slug=prereq_slug).first()
    return {
        'slug': prereq_slug,
        'title_en': prereq.title_en if prereq else '',
        'title_ko': prereq.title_ko if prereq else '',
    }


def _survey_award_values_for_response(response: SurveyResponse) -> tuple[int, str]:
    lock = _point_prereq_lock_for_response(response)
    if lock is None:
        return response.survey.point_value, ''
    return 0, f"Prereq {lock['slug']} not completed at submit time."


def _computed_missing_survey_awards_for_user(
    user,
    existing_awards: list[PointAward],
) -> list[dict]:
    awarded_response_ids = {
        award.response_id
        for award in existing_awards
        if award.source_kind == PointAward.SOURCE_SURVEY and award.response_id
    }
    awarded_scheduled_ids = {
        award.scheduled_survey_id
        for award in existing_awards
        if award.source_kind == PointAward.SOURCE_SURVEY and award.scheduled_survey_id
    }
    computed = []
    responses = (
        SurveyResponse.objects
        .filter(user=user, survey__point_value__gt=0)
        .exclude(id__in=awarded_response_ids)
        .select_related('survey', 'user')
        .order_by('submitted_at', 'id')
    )
    for response in responses:
        scheduled = _scheduled_survey_for_existing_response(response)
        if scheduled is not None and scheduled.id in awarded_scheduled_ids:
            continue

        awarded_points, note = _survey_award_values_for_response(response)
        title_en, title_ko = _survey_titles_for_user(response.survey, user)
        computed.append({
            'source_kind': PointAward.SOURCE_SURVEY,
            'source_slug': response.survey.slug,
            'scheduled_survey_id': scheduled.id if scheduled is not None else None,
            'title_en': title_en,
            'title_ko': title_ko,
            'cadence': scheduled.cadence if scheduled is not None else None,
            'window_start': scheduled.window_start if scheduled is not None else None,
            'window_end': scheduled.window_end if scheduled is not None else None,
            'awarded_points': awarded_points,
            'adjusted_points': None,
            'effective_points': awarded_points,
            'note': note,
            'submitted_at': response.submitted_at,
        })
        if scheduled is not None:
            awarded_scheduled_ids.add(scheduled.id)
    return computed


def backfill_missing_survey_point_awards(*, user=None) -> SurveyPointAwardBackfillResult:
    """Materialize PointAward rows for responses submitted before the ledger existed."""
    awarded_response_ids = set(
        PointAward.objects
        .filter(source_kind=PointAward.SOURCE_SURVEY, response__isnull=False)
        .values_list('response_id', flat=True)
    )
    awarded_scheduled_ids_by_user: dict[int, set[int]] = {}
    scheduled_awards = (
        PointAward.objects
        .filter(source_kind=PointAward.SOURCE_SURVEY, scheduled_survey__isnull=False)
        .values_list('user_id', 'scheduled_survey_id')
    )
    for user_id, scheduled_id in scheduled_awards:
        awarded_scheduled_ids_by_user.setdefault(user_id, set()).add(scheduled_id)

    responses = (
        SurveyResponse.objects
        .filter(survey__point_value__gt=0)
        .exclude(id__in=awarded_response_ids)
        .select_related('survey', 'user')
        .order_by('user_id', 'submitted_at', 'id')
    )
    if user is not None:
        responses = responses.filter(user=user)

    scanned = 0
    created = 0
    skipped_existing = 0
    for response in responses:
        scanned += 1
        scheduled = _scheduled_survey_for_existing_response(response)
        user_scheduled_ids = awarded_scheduled_ids_by_user.setdefault(response.user_id, set())
        if scheduled is not None and scheduled.id in user_scheduled_ids:
            skipped_existing += 1
            continue

        awarded_points, note = _survey_award_values_for_response(response)
        defaults = {
            'source_slug': response.survey.slug,
            'response': response,
            'awarded_points': awarded_points,
            'note': note,
        }
        if scheduled is not None:
            _award, was_created = PointAward.objects.get_or_create(
                user=response.user,
                source_kind=PointAward.SOURCE_SURVEY,
                scheduled_survey=scheduled,
                defaults=defaults,
            )
            if was_created:
                user_scheduled_ids.add(scheduled.id)
                created += 1
            else:
                skipped_existing += 1
            continue

        _award, was_created = PointAward.objects.get_or_create(
            user=response.user,
            source_kind=PointAward.SOURCE_SURVEY,
            response=response,
            defaults=defaults,
        )
        if was_created:
            created += 1
        else:
            skipped_existing += 1

    return SurveyPointAwardBackfillResult(
        scanned=scanned,
        created=created,
        skipped_existing=skipped_existing,
    )


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
        if _skip_for_serving_condition(survey, user_data):
            continue
        visible.append(scheduled)
    return visible


def available_max_for_user(user) -> int:
    total = sum(source['max_points'] for source in WIT_BOT_AUDIT_PHASES.values())
    total += sum(source['max_points'] for source in APP_USAGE_PHASES.values())
    total += INTERVIEW_SIGNUP_MAX_POINTS
    total += FRIEND_INVITE_MAX_POINTS
    for scheduled in _visible_scheduled_surveys_for_points(user):
        total += scheduled.survey.point_value
    return total


def pending_prereqs_for_user(user) -> list[dict]:
    from surveys.tokens import build_token_map, substitute

    pending = []
    for scheduled in _visible_scheduled_surveys_for_points(user):
        survey = scheduled.survey
        if survey.point_value <= 0:
            continue
        lock = point_prereq_lock_for_user(survey, user)
        if lock is None:
            continue
        tokens = build_token_map(survey, viewer=user)
        pending.append({
            'survey_slug': survey.slug,
            'scheduled_survey_id': scheduled.id,
            'title_en': substitute(survey.title_en, tokens),
            'title_ko': substitute(survey.title_ko, tokens),
            'potential_points': survey.point_value,
            'prereq_slug': lock['slug'],
            'prereq_title_en': lock['title_en'],
            'prereq_title_ko': lock['title_ko'],
        })
    return pending


def round_reimbursement_cents(points: int) -> int:
    """Convert points to dollars and round any positive amount up to $5."""
    if points <= 0:
        return 0
    raw_cents = (points * 100 + POINTS_PER_DOLLAR - 1) // POINTS_PER_DOLLAR
    return ((raw_cents + 499) // 500) * 500


def reimbursement_state_for_user(user) -> dict:
    awards = list(
        PointAward.objects
        .filter(user=user)
        .select_related('scheduled_survey__survey', 'response__survey')
        .order_by('-created_at', '-id')
    )
    serialized_awards = [serialize_reimbursement_award(award) for award in awards]
    adjusted_total = sum(award['effective_points'] for award in serialized_awards)
    interview_completed = any(
        award.source_kind == PointAward.SOURCE_INTERVIEW_SIGNUP
        and award.effective_points > 0
        for award in awards
    )
    dropout_completed = DropoutSurveyResponse.objects.filter(user=user).exists()
    return {
        'is_final': True,
        'provisional_total': adjusted_total,
        'adjusted_total': adjusted_total,
        'available_max': available_max_for_user(user),
        'dollar_estimate_cents': round_reimbursement_cents(adjusted_total),
        'points_per_dollar': POINTS_PER_DOLLAR,
        'rounding_notice_en': (
            'Reimbursement amounts are rounded up to the next $5 increment.'
        ),
        'awards': serialized_awards,
        'pending_prereqs': [],
        'interview_opportunity': {
            'completed': interview_completed,
            'potential_points': INTERVIEW_SIGNUP_MAX_POINTS,
            'signup_url': None if interview_completed else INTERVIEW_SIGNUP_URL,
            'signup_deadline': INTERVIEW_SIGNUP_DEADLINE,
        },
        'dropout_survey': {
            'completed': dropout_completed,
            'url': None if dropout_completed else DROPOUT_SURVEY_URL,
        },
        'policy_notice_en': (
            'Surveys determined not to have been answered in good faith were not '
            'credited, even when the survey was completed.'
        ),
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
