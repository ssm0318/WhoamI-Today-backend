"""Bucketing logic for the 4-week study schedule.

Pure query helpers — no view code. Consumed by `SurveyOfTheDayView` (today's
daily) and `SurveyIndexView` (the bucketed index).
"""
import re
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Exists, OuterRef, Q, Subquery
from django.utils import timezone

from surveys.models import (
    CADENCE_DAILY, ScheduledSurvey, Survey, SurveyQuestion, SurveyResponse,
    UserSurveyEmbeddedData,
)
from surveys.retired import is_retired_survey_slug


# Same pattern as `surveys.tokens._TOKEN_RE` — duplicated locally so this
# module stays decoupled from the substitution layer. If the syntax ever
# changes, update both.
_TOKEN_RE = re.compile(r'\{\{\s*(\w+)\s*\}\}')

# Survey-level text fields that may contain `{{token}}` references. Used by
# `_required_tokens_for_survey` to enumerate which keys a survey depends on.
_SURVEY_TEXT_FIELDS = (
    'title_en', 'title_ko',
    'description_en', 'description_ko',
    'interpretation_en', 'interpretation_ko',
)

# Question-level text fields with the same role. Kept aligned with the
# substitution helper in `surveys.tokens.apply_to_question_dict`.
_QUESTION_TEXT_FIELDS = (
    'prompt_en', 'prompt_ko',
    'description_en', 'description_ko',
    'placeholder_en', 'placeholder_ko',
    'content_en', 'content_ko',
)


def _required_tokens_for_survey(survey: 'Survey') -> set:
    """Set of token keys this survey will need at render time.

    Tokens listed in the survey's own `tokens` block are subtracted — those
    resolve from the survey row itself and never depend on the user.
    """
    needed: set = set()
    for f in _SURVEY_TEXT_FIELDS:
        text = getattr(survey, f, '') or ''
        if text:
            needed.update(_TOKEN_RE.findall(text))
    for q in survey.questions.all():
        for f in _QUESTION_TEXT_FIELDS:
            text = getattr(q, f, '') or ''
            if text:
                needed.update(_TOKEN_RE.findall(text))
    survey_provided = set((survey.tokens or {}).keys())
    return needed - survey_provided


def _find_source_survey_for_token(token: str) -> 'Survey | None':
    """Survey whose `embedded_data=True` question populates this token.

    Convention:
      - A question with slug `X` and `embedded_data=True` populates token `X`.
      - For specific keys (currently only `habit_platform`), an additional
        resolver writes `X_label` as a side-effect — so `X_label` is also
        sourced from the same question.

    Returns None when no source exists in the DB. Callers then have to
    decide between hiding the downstream survey or surfacing the literal
    token. `get_today_daily` chooses to hide.
    """
    candidates = [token]
    if token.endswith('_label'):
        candidates.append(token[: -len('_label')])
    for slug in candidates:
        q = (
            SurveyQuestion.objects
            .filter(slug=slug, embedded_data=True)
            .select_related('survey')
            .first()
        )
        if q:
            return q.survey
    return None


def _resolve_missing_token_to_source(scheduled_survey: 'Survey', user) -> 'Survey | None':
    """If `scheduled_survey` has any required tokens this user hasn't
    populated, return the upstream Survey that would populate the first such
    token. Returns `None` either when nothing is missing (run as scheduled)
    OR when none of the missing tokens have a resolvable source (caller
    should skip the survey entirely).
    """
    user_data = _user_embedded_data(user)
    missing = sorted(_required_tokens_for_survey(scheduled_survey) - set(user_data.keys()))
    if not missing:
        return None
    for tok in missing:
        source = _find_source_survey_for_token(tok)
        if source is None:
            continue
        # Don't loop: if the user already responded to the source survey
        # (so the answer just hasn't propagated to embedded data — shouldn't
        # happen, but defensive), prefer skipping over redirecting.
        if SurveyResponse.objects.filter(survey=source, user=user).exists():
            continue
        return source
    return None


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

    Routing priority — schedule-level (`ScheduledSurvey.target_user_group`)
    OVERRIDES survey-level (slug-suffix `_w` / `_q`) when explicitly set.
    Without that override, a slug like `feature_eval_w` would never reach
    a `group_q_first` user even though the q-first row is intentionally
    scheduled for them in Phase 2 (Day 19) so they can evaluate Ver.W
    after the biweekly crossover.

    When `target_user_group` is empty, fall back to slug-suffix routing
    (the original behavior — used by mid_study_w / mid_study_q etc.).
    """
    target = getattr(scheduled, 'target_user_group', '') or ''
    if target:
        user_group = getattr(user, 'user_group', '') or ''
        return user_group == target
    return routes_to_user(scheduled.survey, user)


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


# Sentinel return shape from `get_today_daily_with_prereq`. The view turns
# this into the API response without having to know about ScheduledSurvey
# vs Survey directly. `date` is None when the survey is a token-prereq
# redirect (not on the user's actual schedule for today).
class _SurveyForToday:
    __slots__ = ('survey', 'date', 'is_prereq_redirect')

    def __init__(self, survey, date=None, is_prereq_redirect=False):
        self.survey = survey
        self.date = date
        self.is_prereq_redirect = is_prereq_redirect


def get_today_daily_with_prereq(user):
    """Wrap `get_today_daily` with token-prerequisite resolution.

    Three outcomes:

    1. No daily scheduled today (or all filtered out) → returns `None`.

    2. Today's scheduled survey has all its `{{token}}` references either
       provided by the survey's own `tokens` map or already populated in
       the user's `UserSurveyEmbeddedData` → returns `_SurveyForToday`
       wrapping that ScheduledSurvey row (with `date = window_start`).

    3. Today's scheduled survey has at least one token the user hasn't
       populated, AND there exists an upstream Survey whose
       `embedded_data=True` question would populate it → returns
       `_SurveyForToday` wrapping the upstream Survey (with `date = None`
       since the redirected survey isn't tied to today's window) and
       `is_prereq_redirect = True`. The SOTD card on Share / digest will
       render this in place of today's scheduled survey, so the user
       answers the prerequisite first and the literal `{{token}}` never
       leaks to the UI.

    4. Today's scheduled survey has missing tokens and NO source is
       findable for them → returns `None` (caller treats as "no SOTD
       today"). Prevents serving a survey whose text would contain raw
       `{{token}}` literals — the user-visible behavior of the bug that
       this whole machinery exists to close.
    """
    scheduled = get_today_daily(user)
    if scheduled is None:
        return None
    source = _resolve_missing_token_to_source(scheduled.survey, user)
    if source is None:
        # Either nothing missing, or nothing findable. If something is
        # missing AND nothing is findable, return None — we never want to
        # surface literal tokens.
        missing = _required_tokens_for_survey(scheduled.survey) - set(
            _user_embedded_data(user).keys()
        )
        if missing:
            return None
        return _SurveyForToday(survey=scheduled.survey, date=scheduled.window_start)
    return _SurveyForToday(survey=source, date=None, is_prereq_redirect=True)


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

    # Persistent surveys that stay in available_now even after the user
    # submits, until the researcher closes them:
    #   - editable: one row per user, re-openable for editing.
    #   - repeatable: multiple rows allowed (each visit is a fresh entry,
    #     e.g. anytime_reflection drop-ins).
    # Both carry `user_answered=True` after first submit, so the frontend
    # can decide between "Edit" / "Add another" affordances. Once
    # `survey.closed` flips to True, the row drops from available_now.
    persistent_open = Q(
        Q(survey__editable=True) | Q(survey__repeatable=True),
        survey__closed=False,
    )

    available = list(
        qs.filter(window_start__lte=today)
          .filter(Q(window_end__isnull=True) | Q(window_end__gte=today))
          .filter(Q(user_answered=False) | persistent_open)
    )
    late = list(
        qs.filter(
            window_end__lt=today,
            allow_late=True,
            user_answered=False,
        )
    )
    # Completed: answered AND (not editable AND not repeatable) OR closed.
    # Persistent surveys live exclusively in available_now (single source
    # of truth) while they're still accepting submissions.
    completed = list(
        qs.filter(user_answered=True).filter(
            Q(survey__closed=True) |
            Q(survey__editable=False, survey__repeatable=False)
        )
    )

    user_data = _user_embedded_data(user)
    user_data_keys = set(user_data.keys())

    def _has_unresolved_tokens(survey) -> bool:
        """True when a survey would render with literal `{{token}}` text
        for this user (no value in their embedded data and no upstream
        source survey exists in the DB to populate it). Drops the row from
        the bucket so the user never taps into a half-broken answer flow.
        Surveys whose missing tokens DO have a findable source could stay
        in the index (the user can answer the source survey first, then
        the row resolves), but for now we keep things simple and drop them
        as well — the SOTD card is the primary surface and already handles
        the prereq redirect.
        """
        missing = _required_tokens_for_survey(survey) - user_data_keys
        return bool(missing)

    def _filter(rows):
        out = []
        for sched in rows:
            if is_retired_survey_slug(sched.survey.slug):
                continue
            if not schedule_routes_to_user(sched, user):
                continue
            if _is_weekend_skipped(sched, today):
                continue
            if _skip_for_serving_condition(sched.survey, user_data):
                continue
            if _has_unresolved_tokens(sched.survey):
                # Hide the row from `available_now` / `late_but_accepted`
                # — opening it would reveal literal `{{token}}` text. The
                # row reappears in the next index fetch once the source
                # survey is answered (token populates -> missing set
                # shrinks -> filter passes).
                continue
            out.append(sched)
        return out

    # Within each bucket, an explicit ScheduledSurvey.sidebar_order wins.
    # Rows without one keep the legacy fallback: highest-priority survey,
    # earlier window_start, then sequence_index for stable ordering.
    def _by_sidebar_order(rows):
        return sorted(
            rows,
            key=lambda s: (
                s.sidebar_order is None,
                s.sidebar_order if s.sidebar_order is not None else 0,
                -s.survey.priority,
                s.window_start,
                s.sequence_index,
            ),
        )

    return {
        'available_now': _by_sidebar_order(_filter(available)),
        'late_but_accepted': _by_sidebar_order(_filter(late)),
        # Completed rows aren't filtered by serving_condition / weekend —
        # the user already answered, so they should still see the entry in
        # their archive. Version routing IS applied (a Q user shouldn't
        # see a W-only completion in their list, even if they somehow have one).
        'completed': _by_sidebar_order(
            [s for s in completed if schedule_routes_to_user(s, user)]
        ),
    }
