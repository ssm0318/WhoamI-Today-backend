from __future__ import annotations

import importlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone as dt_timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from django.utils import timezone

from surveys.management.commands.load_surveys import (
    _expand_includes,
    _load_yaml_with_anchor_lookup,
    _preprocess_yaml_text,
)
from surveys.retired import RETIRED_SURVEY_SLUGS, is_retired_survey_slug
from surveys.sidebar_order import SIDEBAR_ORDER, schedule_order_key


CARE_FIXTURE_FILENAMES = (
    'endpoint.yaml',
    'weekly_anytime.yaml',
    'sotd.yaml',
    'daily.yaml',
    'pre.yaml',
)

RUNTIME_FIXTURE_FILENAMES = (
    'daily.yaml',
    'pre.yaml',
    'endpoint.yaml',
    'weekly_anytime.yaml',
    'sotd.yaml',
    'closeness_reeval.yaml',
    'habit_platform.yaml',
)

FIXTURES_DIR = Path(__file__).resolve().parent / 'fixtures'
TOKEN_RE = re.compile(r'\{\{\s*(\w+)\s*\}\}')
W_FIRST = 'group_w_first'
Q_FIRST = 'group_q_first'
ALL_PARTICIPANTS = 'all_participants'
SURVEYS_PAUSED_UNTIL_UTC = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)
SURVEYS_PAUSED_MESSAGE_EN = ''

AUDIENCE_LABELS = {
    ALL_PARTICIPANTS: 'All participants',
    W_FIRST: 'Ver.W-first users',
    Q_FIRST: 'Ver.Q-first users',
}

BUCKET_LABELS = {
    'available_now': 'Available now',
    'late_but_accepted': 'Late but accepted',
    'completed': 'Completed',
}

CADENCE_LABELS = {
    'daily': 'daily',
    'weekly': 'weekly',
    'biweekly': 'biweekly',
    'anytime': 'anytime',
    'endpoint': 'endpoint',
}

MONTH_ABBR = (
    '',
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
)


def build_survey_audit(
    *,
    fixtures_dir: Path | None = None,
    fixture_files: tuple[str, ...] = CARE_FIXTURE_FILENAMES,
    logical_today: date | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Build a source-of-truth audit from survey fixtures and schedule code.

    The survey content comes directly from the selected YAML files, expanded
    with the same helper functions used by `load_surveys`. The schedule comes
    from the migration constants plus the follow-up reschedule migrations that
    `setup_survey_state` reapplies.
    """
    base_dir = fixtures_dir or FIXTURES_DIR
    now_utc = _as_utc(now_utc or timezone.now())
    logical_today = logical_today or _logical_today_from_now(now_utc)

    surveys, fixture_errors = _load_surveys_from_files(base_dir, fixture_files)
    runtime_surveys, _runtime_errors = _load_surveys_from_files(base_dir, RUNTIME_FIXTURE_FILENAMES)
    _drop_retired_surveys(runtime_surveys)
    _apply_static_survey_tokens(runtime_surveys)

    schedule_rows = _build_schedule_rows()
    _annotate_schedule_rows(schedule_rows, surveys)
    sidebar_simulations = _build_sidebar_simulations(
        runtime_surveys,
        schedule_rows,
        logical_today=logical_today,
        now_utc=now_utc,
    )

    warnings = list(fixture_errors)
    warnings.extend(_build_warnings(surveys, schedule_rows))

    scheduled_slugs = {row['survey_slug'] for row in schedule_rows if row['source_found']}
    unscheduled = sorted(
        slug for slug, survey in surveys.items()
        if slug not in scheduled_slugs and not survey['slug'].startswith('_')
    )

    question_count = sum(survey['question_count'] for survey in surveys.values())
    return {
        'generated_at': now_utc.isoformat(),
        'fixture_files': list(fixture_files),
        'runtime_fixture_files': list(RUNTIME_FIXTURE_FILENAMES),
        'summary': {
            'survey_count': len(surveys),
            'question_count': question_count,
            'schedule_row_count': len(schedule_rows),
            'warning_count': len(warnings),
            'unscheduled_survey_count': len(unscheduled),
        },
        'surveys': surveys,
        'schedule_rows': schedule_rows,
        'sidebar_simulations': sidebar_simulations,
        'unscheduled_surveys': unscheduled,
        'warnings': warnings,
    }


def build_survey_user_audit(
    *,
    fixtures_dir: Path | None = None,
    logical_today: date | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Build the click-through audit for a user with no survey responses.

    Unlike the source audit, this loads the runtime fixture order so scheduled
    rows such as `pre_study` can be opened and inspected even when their source
    YAML is outside the five focused authoring files.
    """
    base_dir = fixtures_dir or FIXTURES_DIR
    now_utc = _as_utc(now_utc or timezone.now())
    logical_today = logical_today or _logical_today_from_now(now_utc)

    surveys, fixture_errors = _load_surveys_from_files(base_dir, RUNTIME_FIXTURE_FILENAMES)
    _drop_retired_surveys(surveys)
    _apply_static_survey_tokens(surveys)
    schedule_rows = _build_schedule_rows()
    _annotate_schedule_rows(schedule_rows, surveys)
    sidebar_simulations = _build_sidebar_simulations(
        surveys,
        schedule_rows,
        logical_today=logical_today,
        now_utc=now_utc,
    )

    question_type_counts: Counter[str] = Counter()
    for survey in surveys.values():
        for question in survey['questions']:
            question_type_counts[question['type']] += 1

    warnings = list(fixture_errors)
    warnings.extend(_build_warnings(surveys, schedule_rows))
    question_count = sum(survey['question_count'] for survey in surveys.values())

    return {
        'generated_at': now_utc.isoformat(),
        'logical_today': logical_today.isoformat(),
        'fixture_files': list(RUNTIME_FIXTURE_FILENAMES),
        'summary': {
            'survey_count': len(surveys),
            'question_count': question_count,
            'schedule_row_count': len(schedule_rows),
            'warning_count': len(warnings),
        },
        'question_type_counts': dict(sorted(question_type_counts.items())),
        'surveys': surveys,
        'schedule_rows': schedule_rows,
        'sidebar_simulations': sidebar_simulations,
        'warnings': warnings,
    }


def _drop_retired_surveys(surveys: dict[str, dict[str, Any]]) -> None:
    for slug in RETIRED_SURVEY_SLUGS:
        surveys.pop(slug, None)


def _load_surveys_from_files(
    base_dir: Path,
    filenames: tuple[str, ...],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    surveys: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for filename in filenames:
        path = base_dir / filename
        if not path.exists():
            errors.append(f'Missing fixture: {filename}')
            continue
        for survey in _load_survey_entries(path):
            surveys[survey['slug']] = survey

    return surveys, errors


def _apply_static_survey_tokens(surveys: dict[str, dict[str, Any]]) -> None:
    """Apply the same survey-level token substitution the API serializer uses.

    This intentionally only resolves tokens provided by each survey's own
    `tokens` block. Per-user embedded-data tokens stay unresolved here because
    the no-response audit user has none; rows depending on those tokens are
    filtered out of the visible sidebar just like the real app.
    """
    from surveys.tokens import substitute

    survey_fields = ('title', 'description', 'interpretation')
    question_fields = ('prompt', 'description', 'placeholder', 'content')

    for survey in surveys.values():
        tokens = survey.get('tokens') or {}
        if not tokens:
            continue
        for field in survey_fields:
            survey[field] = substitute(survey.get(field, ''), tokens)
        for question in survey['questions']:
            for field in question_fields:
                question[field] = substitute(question.get(field, ''), tokens)


def _load_survey_entries(path: Path) -> list[dict[str, Any]]:
    text = _preprocess_yaml_text(path.read_text(encoding='utf-8'))
    loaded = _load_yaml_with_anchor_lookup(text)
    data = loaded['data'] or []
    anchors = loaded['anchors']

    entries: list[dict[str, Any]] = []
    for entry in data:
        slug = entry.get('slug', '')
        if not slug or slug.startswith('_'):
            continue

        default_type = entry.get('type', 'likert_5')
        raw_questions = list(entry.get('questions', []))
        expanded_questions = _expand_includes(
            raw_questions,
            anchors,
            context=f'audit survey {slug!r}',
        )
        questions = [
            _normalize_question(question, order, default_type)
            for order, question in enumerate(expanded_questions, start=1)
        ]
        survey_texts = [
            _localized(entry.get('title')),
            _localized(entry.get('description')),
            _localized(entry.get('interpretation')),
        ]
        question_texts = [
            value
            for question in questions
            for value in (
                question['prompt'],
                question['content'],
                question['description'],
                question['placeholder'],
            )
            if value
        ]
        provided_tokens = set((entry.get('tokens') or {}).keys())
        required_tokens = sorted(_tokens_in_texts(survey_texts + question_texts) - provided_tokens)

        entries.append({
            'slug': slug,
            'source_file': path.name,
            'type': default_type,
            'title': _localized(entry.get('title')),
            'description': _localized(entry.get('description')),
            'interpretation': _localized(entry.get('interpretation')),
            'friend_visible': entry.get('friend_visible', True),
            'results_hidden': entry.get('results_hidden', False),
            'result_kind': entry.get('result_kind', ''),
            'score_formula': entry.get('score_formula', ''),
            'score_components': entry.get('score_components', []) or [],
            'tokens': entry.get('tokens', {}) or {},
            'required_tokens': required_tokens,
            'repeatable': entry.get('repeatable', False),
            'serving_condition': entry.get('serving_condition', {}) or {},
            'editable': entry.get('editable', False),
            'closed': entry.get('closed', False),
            'priority': entry.get('priority', 0),
            'question_count': len(questions),
            'questions': questions,
        })
    return entries


def _normalize_question(question: dict[str, Any], order: int, default_type: str) -> dict[str, Any]:
    options = [
        {
            'order': option.get('order'),
            'value': option.get('value'),
            'label': _localized(option.get('label')),
        }
        for option in question.get('options', [])
    ]
    return {
        'order': order,
        'slug': question.get('slug', ''),
        'type': question.get('type', default_type),
        'prompt': _localized(question.get('prompt')),
        'content': _localized(question.get('content')),
        'description': _localized(question.get('description')),
        'placeholder': _localized(question.get('placeholder')),
        'low_label': _localized(question.get('low_label')),
        'high_label': _localized(question.get('high_label')),
        'na_option': _localized(question.get('na_option')),
        'required': question.get('required', True),
        'reverse_scored': question.get('reverse_scored', False),
        'result_kind': question.get('result_kind', ''),
        'result_group': question.get('result_group', ''),
        'result_hidden': question.get('result_hidden', False),
        'embedded_data': question.get('embedded_data', False),
        'conditional_display': question.get('conditional_display', {}) or {},
        'min_length': question.get('min_length'),
        'slider_min_value': question.get('slider_min_value'),
        'slider_max_value': question.get('slider_max_value'),
        'options': options,
    }


def _localized(value: Any, lang: str = 'en') -> str:
    if not value:
        return ''
    if isinstance(value, dict):
        return str(value.get(lang) or value.get('en') or '')
    return str(value)


def _tokens_in_texts(texts: list[str]) -> set[str]:
    tokens: set[str] = set()
    for text in texts:
        tokens.update(TOKEN_RE.findall(text or ''))
    return tokens


def _build_schedule_rows() -> list[dict[str, Any]]:
    rows: dict[tuple[str, int], dict[str, Any]] = {}

    seed = importlib.import_module('surveys.migrations.0004_seed_study_schedule')
    for cadence, seq, slug, window_start, window_end, allow_late in seed.SCHEDULE:
        _upsert_schedule(rows, cadence, seq, slug, window_start, window_end, allow_late)

    wq = importlib.import_module('surveys.migrations.0011_schedule_wq_biweekly')
    wq_sequences = {seq for seq, _, _ in wq.WQ_BIWEEKLY_SCHEDULE}
    wq_slugs = {slug for _, slug, _ in wq.WQ_BIWEEKLY_SCHEDULE}
    for key, row in list(rows.items()):
        cadence, seq = key
        if cadence == 'biweekly' and seq in wq_sequences and row['survey_slug'] not in wq_slugs:
            del rows[key]
    for seq, slug, day in wq.WQ_BIWEEKLY_SCHEDULE:
        _upsert_schedule(rows, 'biweekly', seq, slug, day, day, True)

    sotd = importlib.import_module('surveys.migrations.0013_seed_sotd_schedule')
    for day_n, slug in sotd.SOTD_SCHEDULE:
        _upsert_schedule(
            rows,
            'daily',
            100 + day_n,
            slug,
            sotd._day(day_n),
            sotd._day(day_n),
            False,
        )

    persistent = importlib.import_module('surveys.migrations.0015_seed_persistent_eval_surveys')
    for seq, slug, day, target_group in persistent.PERSISTENT_SCHEDULE:
        _upsert_schedule(
            rows,
            'endpoint',
            seq,
            slug,
            day,
            None,
            True,
            target_user_group=target_group,
        )

    deadline_windows = importlib.import_module(
        'surveys.migrations.0032_survey_deadline_windows'
    )
    _update_schedule_date(
        rows,
        'endpoint',
        2,
        deadline_windows.FEATURE_W_FIRST_START,
        deadline_windows.PHASE1_DUE,
    )
    _update_schedule_date(
        rows,
        'endpoint',
        3,
        deadline_windows.FEATURE_Q_FIRST_START,
        deadline_windows.PHASE2_DUE,
    )

    phase1_reflection = importlib.import_module(
        'surveys.migrations.0031_phase1_reflection_parts_due_may18'
    )
    for seq in (2, 3):
        _update_schedule_date(
            rows,
            'biweekly',
            seq,
            phase1_reflection.PHASE1_DUE,
            phase1_reflection.PHASE1_DUE,
        )
        rows[('biweekly', seq)]['allow_late'] = True
        rows[('biweekly', seq)]['late_behavior'] = 'Late accepted'
    _update_schedule_date(
        rows,
        'endpoint',
        4,
        phase1_reflection.PHASE1_DUE,
        phase1_reflection.PHASE1_DUE,
    )
    rows[('endpoint', 4)]['allow_late'] = True
    rows[('endpoint', 4)]['late_behavior'] = 'Late accepted'

    honeymoon = importlib.import_module('surveys.migrations.0016_reschedule_d01_honeymoon_to_may_5')
    _update_schedule_date(rows, 'daily', honeymoon.HONEYMOON_SEQ, honeymoon.NEW_WINDOW, honeymoon.NEW_WINDOW)

    weekly = importlib.import_module('surveys.migrations.0017_shift_weekly_reflections_to_end_of_week')
    for seq, _slug, window_start, window_end in weekly.NEW_WEEKLY_SCHEDULE:
        _update_schedule_date(rows, 'weekly', seq, window_start, window_end)

    weekend_weekly = importlib.import_module(
        'surveys.migrations.0023_weekly_reflections_weekend_only'
    )
    for seq, _slug, window_start, window_end in weekend_weekly.WEEKEND_WEEKLY_SCHEDULE:
        _update_schedule_date(rows, 'weekly', seq, window_start, window_end)
        rows[('weekly', seq)]['allow_late'] = False
        rows[('weekly', seq)]['late_behavior'] = 'Expires when window closes'

    rsds = importlib.import_module('surveys.migrations.0018_reschedule_d02_rsds_to_may_7')
    _update_schedule_date(rows, 'daily', rsds.RSDS_SEQ, rsds.NEW_WINDOW, rsds.NEW_WINDOW)

    sotd_late = importlib.import_module('surveys.migrations.0019_sotd_allow_late_true')
    sotd_slugs = set(sotd_late.SOTD_SLUGS)
    for row in rows.values():
        if row['cadence'] == 'daily' and row['survey_slug'] in sotd_slugs:
            row['allow_late'] = True
            row['late_behavior'] = 'Late accepted'

    catchup = importlib.import_module('surveys.migrations.0024_seed_pre_study_catchup_schedule')
    rows.pop(('biweekly', deadline_windows.OLD_HABIT_PLATFORM_BIWEEKLY_SEQ), None)
    _upsert_schedule(
        rows,
        'daily',
        deadline_windows.HABIT_PLATFORM_DAILY_SEQ,
        catchup.HABIT_PLATFORM_SLUG,
        deadline_windows.PHASE1_DUE,
        deadline_windows.PHASE1_DUE,
        True,
    )

    for key, row in list(rows.items()):
        if is_retired_survey_slug(row['survey_slug']):
            del rows[key]

    _apply_sidebar_order_map(rows)

    out = sorted(rows.values(), key=lambda row: (row['window_start'], row['cadence'], row['sequence_index']))
    _mark_daily_featured_surface(out)
    return out


def _upsert_schedule(
    rows: dict[tuple[str, int], dict[str, Any]],
    cadence: str,
    sequence_index: int,
    survey_slug: str,
    window_start: date,
    window_end: date | None,
    allow_late: bool,
    *,
    target_user_group: str = '',
) -> None:
    rows[(cadence, sequence_index)] = {
        'cadence': cadence,
        'sequence_index': sequence_index,
        'sidebar_order': SIDEBAR_ORDER.get(schedule_order_key(cadence, sequence_index)),
        'survey_slug': survey_slug,
        'window_start': window_start.isoformat(),
        'window_end': window_end.isoformat() if window_end else None,
        'allow_late': allow_late,
        'target_user_group': target_user_group,
        'audience': _audience_for(survey_slug, target_user_group),
        'audience_label': AUDIENCE_LABELS[_audience_for(survey_slug, target_user_group)],
        'source_found': False,
        'source_file': None,
        'question_count': 0,
        'title': '',
        'featured_surface': 'Survey index',
        'late_behavior': 'Late accepted' if allow_late else 'Expires when window closes',
    }


def _apply_sidebar_order_map(rows: dict[tuple[str, int], dict[str, Any]]) -> None:
    for (cadence, sequence_index), row in rows.items():
        row['sidebar_order'] = SIDEBAR_ORDER.get(schedule_order_key(cadence, sequence_index))


def _update_schedule_date(
    rows: dict[tuple[str, int], dict[str, Any]],
    cadence: str,
    sequence_index: int,
    window_start: date,
    window_end: date | None,
) -> None:
    row = rows.get((cadence, sequence_index))
    if not row:
        return
    row['window_start'] = window_start.isoformat()
    row['window_end'] = window_end.isoformat() if window_end else None


def _audience_for(survey_slug: str, target_user_group: str) -> str:
    if target_user_group:
        return target_user_group
    if survey_slug.endswith('_w'):
        return W_FIRST
    if survey_slug.endswith('_q'):
        return Q_FIRST
    return ALL_PARTICIPANTS


def _mark_daily_featured_surface(rows: list[dict[str, Any]]) -> None:
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row['cadence'] == 'daily':
            by_day[row['window_start']].append(row)

    for day_rows in by_day.values():
        visible_rows = sorted(
            day_rows,
            key=lambda row: (row['survey_slug'] == 'daily_base', row['sequence_index']),
        )
        if not visible_rows:
            continue
        featured = visible_rows[0]
        for row in day_rows:
            row['featured_surface'] = (
                'Survey of the Day card'
                if row is featured
                else 'Survey index'
            )


def _annotate_schedule_rows(rows: list[dict[str, Any]], surveys: dict[str, dict[str, Any]]) -> None:
    for row in rows:
        survey = surveys.get(row['survey_slug'])
        if not survey:
            continue
        row['source_found'] = True
        row['source_file'] = survey['source_file']
        row['question_count'] = survey['question_count']
        row['title'] = survey['title']


def _build_warnings(surveys: dict[str, dict[str, Any]], schedule_rows: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    missing = [
        row for row in schedule_rows
        if not row['source_found']
    ]
    for row in missing:
        warnings.append(
            f"Scheduled survey {row['survey_slug']} ({row['cadence']} #{row['sequence_index']}) "
            'is not present in the selected audit fixtures.'
        )
    for slug, survey in surveys.items():
        if survey['required_tokens']:
            warnings.append(
                f"Survey {slug} contains user-dependent tokens: "
                + ', '.join(survey['required_tokens'])
            )
    return warnings


def _build_sidebar_simulations(
    surveys: dict[str, dict[str, Any]],
    schedule_rows: list[dict[str, Any]],
    *,
    logical_today: date,
    now_utc: datetime,
) -> list[dict[str, Any]]:
    return [
        _build_sidebar_simulation(
            surveys,
            schedule_rows,
            audience=audience,
            logical_today=logical_today,
            now_utc=now_utc,
        )
        for audience in (W_FIRST, Q_FIRST)
    ]


def _build_sidebar_simulation(
    surveys: dict[str, dict[str, Any]],
    schedule_rows: list[dict[str, Any]],
    *,
    audience: str,
    logical_today: date,
    now_utc: datetime,
) -> dict[str, Any]:
    available: list[dict[str, Any]] = []
    late: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    user_data: dict[str, Any] = {}

    for row in schedule_rows:
        survey = surveys.get(row['survey_slug'])
        if not survey:
            skipped.append(_sidebar_skip(row, 'missing_runtime_source'))
            continue
        if not _sidebar_routes_to_audience(row, audience):
            continue
        if _sidebar_weekend_skipped(row, logical_today):
            skipped.append(_sidebar_skip(row, 'weekend_skip'))
            continue
        if _sidebar_skip_for_serving_condition(survey, user_data):
            skipped.append(_sidebar_skip(row, 'serving_condition'))
            continue
        if survey['required_tokens']:
            skipped.append(_sidebar_skip(row, 'unresolved_tokens', survey['required_tokens']))
            continue

        start = date.fromisoformat(row['window_start'])
        end = date.fromisoformat(row['window_end']) if row['window_end'] else None
        if start <= logical_today and (end is None or end >= logical_today):
            available.append(_sidebar_entry(row, survey, 'available_now'))
        elif end is not None and end < logical_today and row['allow_late']:
            late.append(_sidebar_entry(row, survey, 'late_but_accepted'))

    available = _sort_sidebar_entries(available)
    late = _sort_sidebar_entries(late)
    is_paused = now_utc < SURVEYS_PAUSED_UNTIL_UTC

    return {
        'audience': audience,
        'audience_label': AUDIENCE_LABELS[audience],
        'logical_today': logical_today.isoformat(),
        'now_utc': now_utc.isoformat(),
        'bucket_order': ['available_now', 'late_but_accepted', 'completed'],
        'bucket_labels': BUCKET_LABELS,
        'is_paused': is_paused,
        'pause_until_utc': SURVEYS_PAUSED_UNTIL_UTC.isoformat(),
        'pause_message_en': SURVEYS_PAUSED_MESSAGE_EN,
        'buckets': {
            'available_now': [] if is_paused else available,
            'late_but_accepted': late,
            'completed': [],
        },
        'hidden_available_now': available if is_paused else [],
        'completed_daily_count': 0,
        'skipped': skipped,
    }


def _sidebar_entry(row: dict[str, Any], survey: dict[str, Any], bucket: str) -> dict[str, Any]:
    entry = {
        'id': f"{row['cadence']}:{row['sequence_index']}",
        'bucket': bucket,
        'survey_slug': row['survey_slug'],
        'survey_title': survey['title'] or row['survey_slug'],
        'cadence': row['cadence'],
        'cadence_label': CADENCE_LABELS.get(row['cadence'], row['cadence']),
        'sequence_index': row['sequence_index'],
        'sidebar_order': row.get('sidebar_order'),
        'window_start': row['window_start'],
        'window_end': row['window_end'],
        'allow_late': row['allow_late'],
        'priority': survey['priority'],
        'redirect_url': f"/surveys/{row['survey_slug']}/answer",
        'runtime_source_file': survey['source_file'],
        'source_found_in_selected_fixtures': row['source_found'],
        'selected_source_file': row['source_file'],
    }
    if bucket == 'late_but_accepted' and row['window_end']:
        entry['subtitle_en'] = f"Was due {_format_sidebar_date(row['window_end'])}"
    else:
        entry['subtitle_en'] = ''
    return entry


def _sidebar_skip(
    row: dict[str, Any],
    reason: str,
    details: list[str] | None = None,
) -> dict[str, Any]:
    return {
        'survey_slug': row['survey_slug'],
        'cadence': row['cadence'],
        'sequence_index': row['sequence_index'],
        'sidebar_order': row.get('sidebar_order'),
        'window_start': row['window_start'],
        'window_end': row['window_end'],
        'reason': reason,
        'details': details or [],
    }


def _sort_sidebar_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        entries,
        key=lambda entry: (
            entry.get('sidebar_order') is None,
            entry.get('sidebar_order') if entry.get('sidebar_order') is not None else 0,
            -entry['priority'],
            date.fromisoformat(entry['window_start']),
            entry['sequence_index'],
        ),
    )


def _sidebar_routes_to_audience(row: dict[str, Any], audience: str) -> bool:
    target = row['target_user_group'] or ''
    if target:
        return target == audience
    slug = row['survey_slug']
    if slug.endswith('_w'):
        return audience == W_FIRST
    if slug.endswith('_q'):
        return audience == Q_FIRST
    return True


def _sidebar_weekend_skipped(row: dict[str, Any], logical_today: date) -> bool:
    if row['cadence'] != 'daily':
        return False
    if row['survey_slug'] == 'daily_base':
        return False
    return logical_today.weekday() in {5, 6}


def _sidebar_skip_for_serving_condition(survey: dict[str, Any], user_data: dict[str, Any]) -> bool:
    rule = (survey['serving_condition'] or {}).get('skip_if_user_embedded_data')
    if not isinstance(rule, dict) or not rule:
        return False
    for key, expected in rule.items():
        if user_data.get(key) != expected:
            return False
    return True


def _format_sidebar_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    return f'{MONTH_ABBR[parsed.month]} {parsed.day}, {parsed.year}'


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt_timezone.utc)
    return value.astimezone(dt_timezone.utc)


def _logical_today_from_now(now_utc: datetime) -> date:
    la_tz = ZoneInfo('America/Los_Angeles')
    return (now_utc.astimezone(la_tz) - timedelta(hours=7)).date()


def render_survey_user_audit_html(audit: dict[str, Any]) -> str:
    data = json.dumps(audit, ensure_ascii=False).replace('</', '<\\/')
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WhoamI Survey User Audit</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #182026;
      --muted: #64717c;
      --line: #d9dfdf;
      --paper: #f5f6f3;
      --panel: #ffffff;
      --soft: #eef4f1;
      --soft-2: #f4eee4;
      --accent: #126a5a;
      --danger: #9f1d1d;
      --mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      --body: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: var(--body);
      line-height: 1.42;
    }
    header {
      padding: 18px 22px;
      border-bottom: 1px solid var(--line);
      background: #fbfbf8;
      display: grid;
      gap: 8px;
    }
    h1 {
      margin: 0;
      font-size: clamp(25px, 4vw, 42px);
      line-height: 1;
      letter-spacing: 0;
    }
    .subtitle {
      margin: 0;
      color: var(--muted);
      max-width: 1120px;
      font-size: 14px;
    }
    .nav-links {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .nav-links a {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      color: var(--ink);
      padding: 7px 10px;
      text-decoration: none;
      font-size: 13px;
      font-weight: 650;
    }
    .nav-links a.active {
      border-color: var(--accent);
      background: var(--soft);
      color: #163d36;
    }
    .shell {
      min-height: calc(100vh - 104px);
      display: grid;
      grid-template-columns: minmax(300px, 380px) minmax(0, 1fr);
    }
    aside {
      border-right: 1px solid var(--line);
      background: #fbfbf8;
      padding: 14px;
      overflow: auto;
      max-height: calc(100vh - 104px);
      position: sticky;
      top: 0;
      display: grid;
      gap: 12px;
      align-content: start;
    }
    main {
      padding: 16px;
      overflow: auto;
      max-height: calc(100vh - 104px);
      display: grid;
      gap: 14px;
      align-content: start;
    }
    .toolbar, .panel, .survey-button, .question-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .toolbar {
      padding: 10px;
      display: grid;
      gap: 10px;
    }
    .segmented {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }
    button, input, select {
      font: inherit;
    }
    button {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 7px;
      min-height: 36px;
      cursor: pointer;
    }
    button.active {
      border-color: var(--accent);
      background: var(--soft);
      color: #163d36;
      font-weight: 700;
    }
    input, select {
      width: 100%;
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 7px 9px;
      background: #fff;
      color: var(--ink);
    }
    .bucket {
      display: grid;
      gap: 7px;
    }
    .bucket h2 {
      margin: 6px 0 0;
      font-size: 16px;
      letter-spacing: 0;
    }
    .bucket-note, .muted {
      color: var(--muted);
      font-size: 13px;
    }
    .pause-banner {
      border: 1px solid #8700ff;
      border-radius: 8px;
      background: #f3e8ff;
      color: #4b008f;
      padding: 10px 12px;
      font-size: 13px;
      font-weight: 650;
    }
    .survey-button {
      width: 100%;
      text-align: left;
      padding: 10px 11px;
      display: grid;
      gap: 5px;
      min-height: auto;
    }
    .survey-button.active {
      box-shadow: inset 3px 0 0 var(--accent);
    }
    .survey-row-top {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
    }
    .survey-row-title {
      font-weight: 750;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 7px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--soft);
      color: #24433d;
      white-space: nowrap;
      font-size: 12px;
      font-weight: 650;
    }
    .pill.gray {
      background: #f0f1f2;
      color: #4d5962;
    }
    .pill.orange {
      background: var(--soft-2);
      color: #653800;
    }
    .pill.red {
      background: #fff1f0;
      color: var(--danger);
      border-color: #edc8c3;
    }
    code, .mono {
      font-family: var(--mono);
      font-size: 12px;
    }
    .panel {
      padding: 14px;
      display: grid;
      gap: 12px;
    }
    .survey-header {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: start;
    }
    h2, h3 {
      margin: 0;
      letter-spacing: 0;
    }
    .survey-header h2 {
      font-size: clamp(22px, 3vw, 34px);
      line-height: 1.05;
    }
    .meta-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 8px;
    }
    .meta-item {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fcfcfb;
      padding: 8px;
      font-size: 13px;
    }
    .meta-item strong {
      display: block;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: .07em;
      margin-bottom: 3px;
    }
    .question-controls {
      display: grid;
      grid-template-columns: minmax(180px, 1fr) 180px;
      gap: 8px;
    }
    .question-list {
      display: grid;
      gap: 10px;
    }
    .question-card {
      padding: 12px;
      display: grid;
      gap: 9px;
    }
    .question-head {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: flex-start;
    }
    .question-badges {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      align-items: center;
    }
    .question-text {
      font-size: 15px;
      font-weight: 650;
    }
    .display-block {
      border-left: 4px solid var(--accent);
      padding: 10px 12px;
      background: #f8fbf8;
      border-radius: 6px;
      white-space: pre-wrap;
    }
    .choice-grid, .likert-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .choice-chip, .likert-chip {
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 8px;
      padding: 7px 9px;
      min-height: 34px;
      cursor: pointer;
      user-select: none;
      display: inline-flex;
      gap: 6px;
      align-items: center;
      max-width: 100%;
    }
    .choice-chip.selected, .likert-chip.selected {
      border-color: var(--accent);
      background: var(--soft);
      color: #173f37;
    }
    .option-value {
      color: var(--muted);
      font-family: var(--mono);
      font-size: 11px;
    }
    .anchor-row, .slider-labels {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      color: var(--muted);
      font-size: 12px;
    }
    .text-preview {
      min-height: 72px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      color: var(--muted);
      background: #fff;
    }
    .slider-preview {
      display: grid;
      gap: 8px;
    }
    .range-track {
      height: 4px;
      border-radius: 4px;
      background: linear-gradient(90deg, var(--accent) 0 50%, var(--line) 50% 100%);
    }
    .json {
      white-space: pre-wrap;
      word-break: break-word;
      background: #f6f7f7;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 8px;
      color: #364149;
    }
    .empty {
      border: 1px dashed var(--line);
      border-radius: 8px;
      padding: 14px;
      color: var(--muted);
      background: #fff;
    }
    @media (max-width: 900px) {
      .shell {
        grid-template-columns: 1fr;
      }
      aside, main {
        position: static;
        max-height: none;
      }
      .survey-header, .question-head, .question-controls {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <header>
    <h1>WhoamI Survey User Audit</h1>
    <p class="subtitle">Click through the surveys in the same bucket order a no-response user would get. The detail pane renders every question with its type, answer control, options, conditions, and result metadata for audit.</p>
    <nav class="nav-links" aria-label="Audit pages">
      <a href="survey_user_audit.html" class="active">Full click-through audit</a>
      <a href="survey_audit.html">Source timeline audit</a>
      <a href="survey_priority_audit.html">Sidebar order editor</a>
    </nav>
  </header>
  <div class="shell">
    <aside>
      <div class="toolbar">
        <div class="segmented" id="audienceButtons"></div>
        <input id="surveySearch" type="search" placeholder="Search surveys, slugs, dates">
      </div>
      <div id="sidebar"></div>
    </aside>
    <main>
      <section class="panel" id="overview"></section>
      <section class="panel">
        <div class="question-controls">
          <input id="questionSearch" type="search" placeholder="Search question text, slug, option labels">
          <label>
            <span class="muted">Question type</span>
            <select id="questionTypeFilter"></select>
          </label>
        </div>
      </section>
      <section id="detail"></section>
    </main>
  </div>
  <script>
    const AUDIT_DATA = __AUDIT_DATA__;
    const LIKERT_RANGES = {
      likert_3: [1, 3],
      likert_4: [1, 4],
      likert_5: [1, 5],
      likert_5_na: [1, 5],
      likert_6: [1, 6],
      likert_7: [1, 7],
    };
    const state = {
      audience: (AUDIT_DATA.sidebar_simulations[0] || {}).audience || '',
      surveySlug: '',
      surveySearch: '',
      questionSearch: '',
      questionType: '',
    };

    const $ = (id) => document.getElementById(id);
    const lower = (value) => String(value || '').toLowerCase();
    const escapeHtml = (value) => String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');

    function simulation() {
      return AUDIT_DATA.sidebar_simulations.find((item) => item.audience === state.audience)
        || AUDIT_DATA.sidebar_simulations[0];
    }

    function sidebarGroups(sim) {
      const groups = [];
      const available = sim.buckets.available_now || [];
      const late = sim.buckets.late_but_accepted || [];
      const completed = sim.buckets.completed || [];
      const hiddenAvailable = sim.hidden_available_now || [];
      const filtered = (sim.skipped || [])
        .filter((entry) => AUDIT_DATA.surveys[entry.survey_slug])
        .map((entry) => ({
          survey_slug: entry.survey_slug,
          survey_title: AUDIT_DATA.surveys[entry.survey_slug].title || entry.survey_slug,
          cadence_label: entry.cadence,
          subtitle_en: `Hidden: ${entry.reason}${entry.details && entry.details.length ? ` (${entry.details.join(', ')})` : ''}`,
          redirect_url: `/surveys/${entry.survey_slug}/answer`,
        }));
      if (available.length) groups.push(['Available now', available, '']);
      if (late.length) groups.push(['Late but accepted', late, '']);
      if (completed.length) groups.push(['Completed', completed, '']);
      if (hiddenAvailable.length) {
        groups.push([
          'Available now hidden while paused',
          hiddenAvailable,
          'The app hides this bucket during the maintenance pause, but these rows are next in the API order.',
        ]);
      }
      if (filtered.length) {
        groups.push([
          'Filtered out of this user sidebar',
          filtered,
          'Not visible to a no-response user now, usually because a token or condition is unresolved.',
        ]);
      }
      return groups;
    }

    function allSidebarEntries(sim) {
      return sidebarGroups(sim).flatMap(([, entries]) => entries);
    }

    function ensureSelectedSurvey() {
      const entries = allSidebarEntries(simulation());
      if (!entries.some((entry) => entry.survey_slug === state.surveySlug)) {
        state.surveySlug = entries[0] ? entries[0].survey_slug : Object.keys(AUDIT_DATA.surveys)[0];
      }
    }

    function renderAudienceButtons() {
      $('audienceButtons').innerHTML = AUDIT_DATA.sidebar_simulations.map((sim) => `
        <button type="button" class="${sim.audience === state.audience ? 'active' : ''}" data-audience="${escapeHtml(sim.audience)}">
          ${escapeHtml(sim.audience_label)}
        </button>
      `).join('');
    }

    function renderOverview() {
      const sim = simulation();
      const counts = AUDIT_DATA.question_type_counts || {};
      $('overview').innerHTML = `
        <div class="survey-header">
          <div>
            <h2>${escapeHtml(sim.audience_label)}</h2>
            <p class="muted">Logical date ${escapeHtml(sim.logical_today)}. Generated ${escapeHtml(AUDIT_DATA.generated_at)}.</p>
          </div>
          <span class="pill ${sim.is_paused ? 'orange' : ''}">${sim.is_paused ? 'survey pause active' : 'not paused'}</span>
        </div>
        <div class="meta-grid">
          <div class="meta-item"><strong>Runtime surveys</strong>${AUDIT_DATA.summary.survey_count}</div>
          <div class="meta-item"><strong>Questions</strong>${AUDIT_DATA.summary.question_count}</div>
          <div class="meta-item"><strong>Schedule rows</strong>${AUDIT_DATA.summary.schedule_row_count}</div>
          <div class="meta-item"><strong>Types</strong>${Object.entries(counts).map(([type, count]) => `${escapeHtml(type)}=${count}`).join(' | ')}</div>
        </div>
        ${sim.is_paused ? `<div class="pause-banner">${escapeHtml(sim.pause_message_en)}</div>` : ''}
      `;
    }

    function renderSidebar() {
      const sim = simulation();
      const q = lower(state.surveySearch);
      const groups = sidebarGroups(sim).map(([label, entries, note]) => [
        label,
        entries.filter((entry) => {
          if (!q) return true;
          return lower([
            entry.survey_slug,
            entry.survey_title,
            entry.cadence_label,
            entry.subtitle_en,
            entry.window_start,
            entry.window_end,
          ].join(' ')).includes(q);
        }),
        note,
      ]).filter(([, entries]) => entries.length);

      $('sidebar').innerHTML = groups.length
        ? groups.map(([label, entries, note]) => `
          <div class="bucket">
            <h2>${escapeHtml(label)}</h2>
            ${note ? `<div class="bucket-note">${escapeHtml(note)}</div>` : ''}
            ${entries.map(renderSurveyButton).join('')}
          </div>
        `).join('')
        : '<div class="empty">No survey rows match this search.</div>';
    }

    function renderSurveyButton(entry) {
      const active = entry.survey_slug === state.surveySlug;
      return `
        <button
          type="button"
          class="survey-button ${active ? 'active' : ''}"
          data-survey-slug="${escapeHtml(entry.survey_slug)}"
        >
          <div class="survey-row-top">
            <span class="survey-row-title">${escapeHtml(entry.survey_title || entry.survey_slug)}</span>
            <span class="pill gray">${escapeHtml(entry.cadence_label || entry.cadence || '')}</span>
          </div>
          ${entry.subtitle_en ? `<div class="muted">${escapeHtml(entry.subtitle_en)}</div>` : ''}
          <code>${escapeHtml(entry.survey_slug)}</code>
        </button>
      `;
    }

    function renderQuestionTypeOptions() {
      const select = $('questionTypeFilter');
      const types = Object.keys(AUDIT_DATA.question_type_counts || {}).sort();
      select.innerHTML = '<option value="">All question types</option>' + types.map((type) =>
        `<option value="${escapeHtml(type)}">${escapeHtml(type)}</option>`
      ).join('');
    }

    function renderDetail() {
      const survey = AUDIT_DATA.surveys[state.surveySlug];
      if (!survey) {
        $('detail').innerHTML = '<div class="empty">Select a survey.</div>';
        return;
      }
      const schedules = AUDIT_DATA.schedule_rows.filter((row) => row.survey_slug === survey.slug);
      const questions = survey.questions.filter(questionPasses);
      $('detail').innerHTML = `
        <section class="panel">
          <div class="survey-header">
            <div>
              <h2>${escapeHtml(survey.title || survey.slug)}</h2>
              <p class="muted">${escapeHtml(survey.description || '')}</p>
            </div>
            <span class="pill">${survey.question_count} questions</span>
          </div>
          <div class="meta-grid">
            <div class="meta-item"><strong>Slug</strong><code>${escapeHtml(survey.slug)}</code></div>
            <div class="meta-item"><strong>Fixture</strong><code>${escapeHtml(survey.source_file)}</code></div>
            <div class="meta-item"><strong>Default type</strong>${escapeHtml(survey.type)}</div>
            <div class="meta-item"><strong>Priority</strong>${survey.priority}</div>
            <div class="meta-item"><strong>Results</strong>${survey.results_hidden ? 'hidden' : 'visible'}</div>
            <div class="meta-item"><strong>Persistence</strong>${survey.editable ? 'editable' : 'one-shot'}${survey.repeatable ? ', repeatable' : ''}</div>
          </div>
          <div class="question-badges">
            ${schedules.length ? schedules.map((row) => `<span class="pill gray">${escapeHtml(row.cadence)} #${row.sequence_index}: ${escapeHtml(row.window_start)}${row.window_end ? ` to ${escapeHtml(row.window_end)}` : ' onward'} / ${escapeHtml(row.audience_label)}</span>`).join('') : '<span class="pill red">not scheduled</span>'}
          </div>
        </section>
        <section class="question-list">
          ${questions.length ? questions.map((q) => renderQuestion(q, survey)).join('') : '<div class="empty">No questions match these filters.</div>'}
        </section>
      `;
    }

    function questionPasses(question) {
      if (state.questionType && question.type !== state.questionType) return false;
      const q = lower(state.questionSearch);
      if (!q) return true;
      return lower([
        question.slug,
        question.type,
        question.prompt,
        question.content,
        question.description,
        question.placeholder,
        question.low_label,
        question.high_label,
        question.na_option,
        JSON.stringify(question.conditional_display || {}),
        ...(question.options || []).flatMap((option) => [option.value, option.label]),
      ].join(' ')).includes(q);
    }

    function renderQuestion(question, survey) {
      const text = question.type === 'display_only'
        ? question.content
        : question.prompt || question.content || '(no prompt/content)';
      return `
        <article class="question-card" id="q-${escapeHtml(survey.slug)}-${question.order}">
          <div class="question-head">
            <div>
              <div class="question-badges">
                <span class="pill gray">#${question.order}</span>
                <span class="pill">Question type: ${escapeHtml(question.type)}</span>
                ${question.required ? '<span class="pill gray">required</span>' : '<span class="pill orange">optional</span>'}
                ${question.conditional_display && Object.keys(question.conditional_display).length ? '<span class="pill orange">conditional</span>' : ''}
                ${question.result_hidden ? '<span class="pill orange">result hidden</span>' : ''}
                ${question.embedded_data ? '<span class="pill">embedded data</span>' : ''}
                ${question.reverse_scored ? '<span class="pill red">reverse scored</span>' : ''}
              </div>
            </div>
            <code>${escapeHtml(question.slug || 'no slug')}</code>
          </div>
          ${question.type === 'display_only'
            ? `<div class="display-block">${escapeHtml(text)}</div>`
            : `<div class="question-text">${escapeHtml(text)}</div>`}
          ${question.description ? `<div class="muted">${escapeHtml(question.description)}</div>` : ''}
          ${renderQuestionControl(question)}
          ${renderQuestionMetadata(question)}
        </article>
      `;
    }

    function renderQuestionControl(question) {
      if (LIKERT_RANGES[question.type]) return renderLikert(question);
      if (question.type === 'single_choice' || question.type === 'multi_choice') {
        return renderChoice(question);
      }
      if (question.type === 'free_text') {
        return `
          <div class="text-preview">
            ${escapeHtml(question.placeholder || 'Free-text answer field')}
            ${question.min_length !== null && question.min_length !== undefined ? `<br><span class="muted">Minimum length: ${question.min_length}</span>` : ''}
          </div>
        `;
      }
      if (question.type === 'slider') {
        return `
          <div class="slider-preview">
            <div class="range-track"></div>
            <div class="slider-labels">
              <span>${escapeHtml(question.low_label || String(question.slider_min_value ?? 'min'))}</span>
              <span>${escapeHtml(question.high_label || String(question.slider_max_value ?? 'max'))}</span>
            </div>
          </div>
        `;
      }
      if (question.type === 'display_only') return '';
      return '<div class="empty">No renderer for this question type.</div>';
    }

    function renderLikert(question) {
      const [min, max] = LIKERT_RANGES[question.type];
      const values = [];
      for (let value = min; value <= max; value += 1) values.push(value);
      const firstOption = (question.options || [])[0];
      const lastOption = (question.options || [])[question.options.length - 1];
      const low = question.low_label || (firstOption ? firstOption.label : '');
      const high = question.high_label || (lastOption ? lastOption.label : '');
      return `
        <div class="likert-row">
          ${values.map((value) => `<span class="likert-chip" data-toggle-chip>${value}</span>`).join('')}
          ${question.type === 'likert_5_na' ? `<span class="likert-chip" data-toggle-chip>${escapeHtml(question.na_option || 'N/A')}</span>` : ''}
        </div>
        ${(low || high) ? `<div class="anchor-row"><span>${escapeHtml(low)}</span><span>${escapeHtml(high)}</span></div>` : ''}
        ${question.options && question.options.length ? `<div class="muted">YAML options: ${question.options.map((option) => `${escapeHtml(JSON.stringify(option.value))}=${escapeHtml(option.label)}`).join(' | ')}</div>` : ''}
      `;
    }

    function renderChoice(question) {
      const multi = question.type === 'multi_choice';
      return `
        <div class="choice-grid">
          ${(question.options || []).map((option) => `
            <span class="choice-chip" data-toggle-chip>
              <span>${multi ? '[ ]' : '( )'}</span>
              <span>${escapeHtml(option.label)}</span>
              <span class="option-value">${escapeHtml(JSON.stringify(option.value))}</span>
            </span>
          `).join('')}
        </div>
      `;
    }

    function renderQuestionMetadata(question) {
      const details = [];
      if (question.result_kind) details.push(['result_kind', question.result_kind]);
      if (question.result_group) details.push(['result_group', question.result_group]);
      if (question.min_length !== null && question.min_length !== undefined) details.push(['min_length', question.min_length]);
      if (question.slider_min_value !== null && question.slider_min_value !== undefined) details.push(['slider_min', question.slider_min_value]);
      if (question.slider_max_value !== null && question.slider_max_value !== undefined) details.push(['slider_max', question.slider_max_value]);
      if (question.conditional_display && Object.keys(question.conditional_display).length) {
        details.push(['conditional_display', JSON.stringify(question.conditional_display, null, 2)]);
      }
      if (!details.length) return '';
      return `
        <div class="meta-grid">
          ${details.map(([label, value]) => `
            <div class="meta-item">
              <strong>${escapeHtml(label)}</strong>
              ${String(value).includes('\\n') ? `<div class="json">${escapeHtml(value)}</div>` : escapeHtml(value)}
            </div>
          `).join('')}
        </div>
      `;
    }

    function renderAll() {
      ensureSelectedSurvey();
      renderAudienceButtons();
      renderOverview();
      renderSidebar();
      renderDetail();
    }

    function init() {
      renderQuestionTypeOptions();
      $('audienceButtons').addEventListener('click', (event) => {
        const button = event.target.closest('[data-audience]');
        if (!button) return;
        state.audience = button.dataset.audience;
        state.surveySlug = '';
        renderAll();
      });
      $('sidebar').addEventListener('click', (event) => {
        const button = event.target.closest('[data-survey-slug]');
        if (!button) return;
        state.surveySlug = button.dataset.surveySlug;
        renderAll();
      });
      document.body.addEventListener('click', (event) => {
        const chip = event.target.closest('[data-toggle-chip]');
        if (chip) chip.classList.toggle('selected');
      });
      $('surveySearch').addEventListener('input', (event) => {
        state.surveySearch = event.target.value;
        renderSidebar();
      });
      $('questionSearch').addEventListener('input', (event) => {
        state.questionSearch = event.target.value;
        renderDetail();
      });
      $('questionTypeFilter').addEventListener('change', (event) => {
        state.questionType = event.target.value;
        renderDetail();
      });
      renderAll();
    }

    init();
  </script>
</body>
</html>
"""
    return html.replace('__AUDIT_DATA__', data)


def render_survey_priority_audit_html(audit: dict[str, Any]) -> str:
    data = json.dumps(audit, ensure_ascii=False).replace('</', '<\\/')
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WhoamI Survey Sidebar Order Editor</title>
  <style>
    :root {
      --ink: #182026;
      --muted: #66717a;
      --line: #d8dfdf;
      --paper: #f5f6f3;
      --panel: #fff;
      --soft: #edf4f1;
      --accent: #126a5a;
      --warn: #7b4b00;
      --danger: #982121;
      --mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      --body: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--paper); color: var(--ink); font-family: var(--body); line-height: 1.42; }
    header { padding: 18px 22px; border-bottom: 1px solid var(--line); background: #fbfbf8; display: grid; gap: 7px; }
    h1, h2, h3 { margin: 0; letter-spacing: 0; }
    h1 { font-size: clamp(25px, 4vw, 40px); line-height: 1.05; }
    h2 { font-size: 18px; }
    h3 { font-size: 15px; }
    .subtitle, .muted { color: var(--muted); }
    .subtitle { margin: 0; max-width: 1040px; font-size: 14px; }
    .nav-links { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .nav-links a { border: 1px solid var(--line); border-radius: 7px; background: #fff; color: var(--ink); padding: 7px 10px; text-decoration: none; font-size: 13px; font-weight: 650; }
    .nav-links a.active { border-color: var(--accent); background: var(--soft); color: #163d36; }
    .shell { display: grid; grid-template-columns: minmax(330px, 420px) minmax(0, 1fr); min-height: calc(100vh - 100px); }
    aside { border-right: 1px solid var(--line); background: #fbfbf8; padding: 14px; display: grid; align-content: start; gap: 12px; position: sticky; top: 0; max-height: calc(100vh - 100px); overflow: auto; }
    main { padding: 14px; display: grid; align-content: start; gap: 12px; max-height: calc(100vh - 100px); overflow: auto; }
    .panel, .survey-row, textarea, input, select, button { border: 1px solid var(--line); border-radius: 8px; background: var(--panel); }
    .panel { padding: 12px; display: grid; gap: 10px; }
    .toolbar { display: grid; gap: 8px; }
    .controls-grid { display: grid; grid-template-columns: 1fr 140px; gap: 8px; }
    input, select, button, textarea { font: inherit; }
    input, select { min-height: 38px; padding: 7px 9px; width: 100%; }
    button { min-height: 36px; padding: 7px 10px; cursor: pointer; color: var(--ink); }
    button.active { border-color: var(--accent); background: var(--soft); font-weight: 700; }
    .button-row, .pill-row { display: flex; flex-wrap: wrap; gap: 7px; align-items: center; }
    .action { min-height: 30px; padding: 4px 8px; font-size: 12px; }
    .survey-list { display: grid; gap: 8px; }
    .survey-row { padding: 10px; display: grid; gap: 8px; }
    .survey-top { display: grid; grid-template-columns: minmax(0, 1fr) 120px 82px; gap: 10px; align-items: start; }
    .survey-title { font-weight: 750; }
    code, .mono { font-family: var(--mono); font-size: 12px; }
    .pill { display: inline-flex; align-items: center; min-height: 22px; padding: 2px 7px; border-radius: 999px; border: 1px solid var(--line); background: var(--soft); color: #24433d; white-space: nowrap; font-size: 12px; font-weight: 650; }
    .pill.gray { background: #f0f1f2; color: #4d5962; }
    .pill.warn { background: #fff4de; color: var(--warn); border-color: #ead2a2; }
    .pill.danger { background: #fff0ef; color: var(--danger); border-color: #edc8c3; }
    .order-input { text-align: right; font-family: var(--mono); }
    .tiny-controls { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; }
    .preview-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 12px; }
    .bucket { border: 1px solid var(--line); border-radius: 8px; background: #fcfcfb; padding: 10px; display: grid; gap: 7px; }
    .preview-section { display: grid; gap: 6px; }
    .preview-section-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .preview-list { display: grid; gap: 7px; min-height: 8px; }
    .preview-entry { border: 1px solid var(--line); border-radius: 7px; background: #fff; padding: 8px; display: grid; gap: 4px; }
    .preview-entry[draggable="true"] { cursor: grab; }
    .preview-entry.dragging { opacity: .45; border-style: dashed; cursor: grabbing; }
    .preview-entry.drop-target { box-shadow: inset 0 2px 0 var(--accent); }
    .scope-list { display: grid; gap: 5px; }
    .scope-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; border-top: 1px solid var(--line); padding-top: 6px; }
    .conflict { border: 1px solid #edc8c3; background: #fff0ef; color: var(--danger); border-radius: 8px; padding: 9px; }
    textarea { width: 100%; min-height: 132px; padding: 9px; font-family: var(--mono); font-size: 12px; color: #263238; resize: vertical; }
    .empty { border: 1px dashed var(--line); border-radius: 8px; padding: 12px; color: var(--muted); background: #fff; }
    @media (max-width: 920px) {
      .shell { grid-template-columns: 1fr; }
      aside, main { position: static; max-height: none; }
      .controls-grid, .survey-top { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>WhoamI Survey Sidebar Order Editor</h1>
    <p class="subtitle">Assign exact order numbers to scheduled survey rows, preview the no-response sidebar by audience/date, then run the generated command to update the local DB and commit-ready backend order map.</p>
    <nav class="nav-links" aria-label="Audit pages">
      <a href="survey_user_audit.html">Full click-through audit</a>
      <a href="survey_audit.html">Source timeline audit</a>
      <a href="survey_priority_audit.html" class="active">Sidebar order editor</a>
    </nav>
  </header>
  <div class="shell">
    <aside>
      <section class="panel toolbar">
        <div class="controls-grid">
          <input id="search" type="search" placeholder="Search title, slug, file, cadence">
          <select id="audienceFilter"></select>
        </div>
        <div class="controls-grid">
          <select id="dateFilter"></select>
          <select id="fileFilter"></select>
        </div>
        <label class="pill-row"><input id="changedOnly" type="checkbox" style="width:auto; min-height:auto;"> <span>Show changed only</span></label>
        <div class="button-row">
          <button type="button" id="renumberShown">Renumber shown</button>
          <button type="button" id="clearShown">Clear shown</button>
          <button type="button" id="clearDateOrders">Clear date drags</button>
          <button type="button" id="resetAll">Reset all</button>
          <button type="button" id="selectChanged">Select changed</button>
        </div>
      </section>
      <section class="panel">
        <h2>Date Orders</h2>
        <div class="pill-row">
          <span class="pill" id="savedScopeCount">0 saved</span>
          <span class="pill gray" id="compiledCount">0 compiled</span>
        </div>
        <div id="conflictBox" class="conflict" hidden></div>
        <div class="scope-list" id="scopeList"></div>
      </section>
      <section class="panel">
        <h2>Export</h2>
        <div class="button-row">
          <button type="button" id="copyJson">Select JSON</button>
          <button type="button" id="copyCommand">Select command</button>
          <button type="button" id="copySource">Select source</button>
        </div>
        <textarea id="jsonOut" readonly></textarea>
        <textarea id="commandOut" readonly></textarea>
        <textarea id="sourceOut" readonly></textarea>
      </section>
    </aside>
    <main>
      <section class="panel">
        <div class="pill-row">
          <span class="pill" id="changedCount">0 changed</span>
          <span class="pill gray" id="surveyCount">0 rows</span>
          <span class="pill gray">Sort key: sidebar_order asc, priority desc, window start asc, sequence asc</span>
        </div>
      </section>
      <section class="panel">
        <h2>No-response Sidebar Preview</h2>
        <div class="preview-grid" id="preview"></div>
      </section>
      <section class="panel">
        <h2>Scheduled Survey Rows</h2>
        <div class="survey-list" id="surveyList"></div>
      </section>
    </main>
  </div>
  <script>
    const AUDIT_DATA = __AUDIT_DATA__;
    const MANAGE_PY = "/Users/jaewonk/Documents/active/whoami-code/WhoamI-Today-backend/adoorback/manage.py";
    const ALL = "all";
    const state = { search: "", file: "", audience: ALL, date: ALL, changedOnly: false, selected: new Set(), orders: {}, dateOrders: {}, synthesizedIds: new Set(), dragging: null };
    const $ = (id) => document.getElementById(id);
    const lower = (value) => String(value || "").toLowerCase();
    const esc = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
    const audienceLabels = {
      all_participants: "All participants",
      group_w_first: "Ver.W-first users",
      group_q_first: "Ver.Q-first users",
    };
    const scheduleRows = (AUDIT_DATA.schedule_rows || []).map((row) => {
      const survey = AUDIT_DATA.surveys[row.survey_slug] || {};
      const id = `${row.cadence}:${row.sequence_index}`;
      return {
        ...row,
        id,
        survey,
        title: survey.title || row.title || row.survey_slug,
        source_file: survey.source_file || row.source_file || "",
        priority: Number(survey.priority || 0),
        originalOrder: row.sidebar_order == null ? null : Number(row.sidebar_order),
      };
    }).sort(baseSort);
    const rowById = Object.fromEntries(scheduleRows.map((row) => [row.id, row]));
    scheduleRows.forEach((row) => { state.orders[row.id] = row.originalOrder; });
    state.audience = (AUDIT_DATA.sidebar_simulations?.[0]?.audience) || ALL;
    state.date = AUDIT_DATA.logical_today || AUDIT_DATA.sidebar_simulations?.[0]?.logical_today || ALL;

    function currentOrder(id) {
      const value = state.orders[id];
      return value === "" || value == null || Number.isNaN(Number(value)) ? null : Number(value);
    }
    function baseSort(a, b) {
      return String(a.window_start || "").localeCompare(String(b.window_start || ""))
        || String(a.cadence || "").localeCompare(String(b.cadence || ""))
        || Number(a.sequence_index || 0) - Number(b.sequence_index || 0);
    }
    function orderSort(a, b) {
      const ao = currentOrder(a.id);
      const bo = currentOrder(b.id);
      return (ao == null) - (bo == null)
        || (ao ?? 0) - (bo ?? 0)
        || Number(b.priority || 0) - Number(a.priority || 0)
        || String(a.window_start || "").localeCompare(String(b.window_start || ""))
        || Number(a.sequence_index || 0) - Number(b.sequence_index || 0);
    }
    function allDates() {
      const dates = new Set();
      scheduleRows.forEach((row) => {
        if (row.window_start) dates.add(row.window_start);
        if (row.window_end) dates.add(row.window_end);
      });
      if (AUDIT_DATA.logical_today) dates.add(AUDIT_DATA.logical_today);
      return Array.from(dates).sort();
    }
    function scopeKey(audience, isoDate, bucketKey) {
      return `${audience}|${isoDate}|${bucketKey}`;
    }
    function parseScopeKey(key) {
      const [audience, isoDate, bucketKey] = String(key).split("|");
      return { audience, isoDate, bucketKey };
    }
    function scopeLabel(key) {
      const { audience, isoDate, bucketKey } = parseScopeKey(key);
      const bucket = bucketKey === "available_now" ? "Available now" : "Late";
      return `${audienceLabels[audience] || audience} / ${isoDate} / ${bucket}`;
    }
    function cleanIds(ids) {
      const seen = new Set();
      const out = [];
      (ids || []).forEach((id) => {
        if (!rowById[id] || seen.has(id)) return;
        seen.add(id);
        out.push(id);
      });
      return out;
    }
    function idSort(a, b) {
      const ao = currentOrder(a);
      const bo = currentOrder(b);
      return (ao == null) - (bo == null)
        || (ao ?? 0) - (bo ?? 0)
        || baseSort(rowById[a], rowById[b]);
    }
    function compiledOrder() {
      const scopeEntries = Object.entries(state.dateOrders)
        .map(([key, ids]) => [key, cleanIds(ids)])
        .filter(([, ids]) => ids.length > 1);
      const nodes = new Set();
      const edges = new Map();
      const indegree = new Map();

      function ensureNode(id) {
        nodes.add(id);
        if (!edges.has(id)) edges.set(id, new Set());
        if (!indegree.has(id)) indegree.set(id, 0);
      }

      scopeEntries.forEach(([, ids]) => {
        ids.forEach(ensureNode);
        for (let index = 0; index < ids.length - 1; index += 1) {
          const before = ids[index];
          const after = ids[index + 1];
          ensureNode(before);
          ensureNode(after);
          if (!edges.get(before).has(after)) {
            edges.get(before).add(after);
            indegree.set(after, indegree.get(after) + 1);
          }
        }
      });

      const ordered = [];
      const queue = Array.from(nodes).filter((id) => indegree.get(id) === 0).sort(idSort);
      while (queue.length) {
        const id = queue.shift();
        ordered.push(id);
        Array.from(edges.get(id) || []).sort(idSort).forEach((next) => {
          indegree.set(next, indegree.get(next) - 1);
          if (indegree.get(next) === 0) {
            queue.push(next);
            queue.sort(idSort);
          }
        });
      }

      if (ordered.length !== nodes.size) {
        const orderedSet = new Set(ordered);
        const conflicted = Array.from(nodes)
          .filter((id) => !orderedSet.has(id))
          .sort(idSort)
          .map((id) => `${rowById[id]?.survey_slug || id} (${id})`);
        return {
          ok: false,
          map: {},
          scopeEntries,
          constraintIds: nodes,
          conflict: `Conflicting date orders: ${conflicted.join(", ")}`,
        };
      }

      const map = {};
      let nextOrder = 1;
      ordered.forEach((id) => { map[id] = nextOrder; nextOrder += 1; });

      const extras = scheduleRows
        .filter((row) => map[row.id] == null && currentOrder(row.id) != null)
        .sort((a, b) => currentOrder(a.id) - currentOrder(b.id) || orderSort(a, b));
      extras.forEach((row) => { map[row.id] = nextOrder; nextOrder += 1; });

      return { ok: true, map, scopeEntries, constraintIds: nodes, conflict: "" };
    }
    function syncOrdersFromCompiled() {
      const compiled = compiledOrder();
      if (!compiled.ok) return compiled;
      state.synthesizedIds.forEach((id) => {
        if (!compiled.constraintIds.has(id) && rowById[id]) {
          state.orders[id] = rowById[id].originalOrder;
        }
      });
      state.synthesizedIds = new Set(compiled.constraintIds);
      state.synthesizedIds.forEach((id) => {
        state.orders[id] = compiled.map[id];
      });
      return compiled;
    }
    function changedMap() {
      const compiled = compiledOrder();
      if (!compiled.ok) return {};
      const out = {};
      scheduleRows.forEach((row) => {
        const next = compiled.map[row.id] ?? null;
        if (next !== row.originalOrder) out[row.id] = next;
      });
      return out;
    }
    function fullOrderMap() {
      const compiled = compiledOrder();
      return compiled.ok ? compiled.map : {};
    }
    function filteredSurveys() {
      const q = lower(state.search);
      return scheduleRows.filter((row) => {
        if (state.changedOnly && currentOrder(row.id) === row.originalOrder) return false;
        if (state.file && row.source_file !== state.file) return false;
        if (state.audience !== ALL && row.audience !== "all_participants" && row.audience !== state.audience) return false;
        if (state.date !== ALL && !rowTouchesDate(row, state.date)) return false;
        if (!q) return true;
        const haystack = [row.id, row.survey_slug, row.title, row.source_file, row.cadence, row.audience_label, row.featured_surface].join(" ");
        return lower(haystack).includes(q);
      });
    }
    function rowTouchesDate(row, isoDate) {
      return rowAvailableOnDate(row, isoDate) || rowLateOnDate(row, isoDate);
    }
    function rowAvailableOnDate(row, isoDate) {
      return String(row.window_start || "") <= isoDate && (!row.window_end || isoDate <= row.window_end);
    }
    function rowLateOnDate(row, isoDate) {
      return Boolean(row.window_end && row.window_end < isoDate && row.allow_late);
    }
    function routesToAudience(row, audience) {
      if (audience === ALL) return true;
      if (row.audience && row.audience !== "all_participants") return row.audience === audience;
      return true;
    }
    function isWeekendSkipped(row, isoDate) {
      if (row.cadence !== "daily" || row.survey_slug === "daily_base") return false;
      const day = new Date(`${isoDate}T12:00:00`).getDay();
      return day === 0 || day === 6;
    }
    function visibleForPreview(row, audience, isoDate) {
      if (!row.survey || !row.survey.slug) return false;
      if (!routesToAudience(row, audience)) return false;
      if (isWeekendSkipped(row, isoDate)) return false;
      if ((row.survey.required_tokens || []).length) return false;
      return true;
    }
    function renderFilters() {
      const files = Array.from(new Set(scheduleRows.map((row) => row.source_file).filter(Boolean))).sort();
      $("fileFilter").innerHTML = '<option value="">All files</option>' + files.map((file) => `<option value="${esc(file)}">${esc(file)}</option>`).join("");
      const audiences = [ALL, "group_w_first", "group_q_first"];
      $("audienceFilter").innerHTML = audiences.map((audience) => `<option value="${esc(audience)}">${esc(audience === ALL ? "All audiences" : audienceLabels[audience])}</option>`).join("");
      $("audienceFilter").value = state.audience;
      $("dateFilter").innerHTML = `<option value="${ALL}">All dates</option>` + allDates().map((date) => `<option value="${esc(date)}">${esc(date)}</option>`).join("");
      $("dateFilter").value = state.date;
    }
    function renderSurveyRow(row) {
      const current = currentOrder(row.id);
      const changed = current !== row.originalOrder;
      const selected = state.selected.has(row.id);
      return `<article class="survey-row" data-row-id="${esc(row.id)}" style="${selected ? "box-shadow: inset 4px 0 0 var(--accent)" : ""}">
        <div class="survey-top">
          <div><div class="survey-title">${esc(row.title || row.survey_slug)}</div><code>${esc(row.survey_slug)} · ${esc(row.id)}</code></div>
          <input class="order-input" type="number" min="1" step="1" placeholder="blank" value="${current ?? ""}" data-order-for="${esc(row.id)}">
          <div class="tiny-controls">
            <button type="button" class="action" data-move="${esc(row.id)}" data-delta="-1">Up</button>
            <button type="button" class="action" data-move="${esc(row.id)}" data-delta="1">Down</button>
          </div>
        </div>
        <div class="pill-row">
          <span class="pill">${esc(row.source_file || "missing source")}</span>
          <span class="pill gray">${esc(row.cadence)} #${row.sequence_index}</span>
          <span class="pill gray">${esc(row.window_start)}${row.window_end ? `-${esc(row.window_end)}` : "+"}</span>
          <span class="pill gray">${esc(row.audience_label || audienceLabels[row.audience] || row.audience || "")}</span>
          <span class="pill gray">priority ${row.priority}</span>
          <span class="pill gray">original ${row.originalOrder ?? "blank"}</span>
          ${changed ? '<span class="pill warn">changed</span>' : ""}
          ${row.allow_late ? '<span class="pill">late accepted</span>' : '<span class="pill gray">expires</span>'}
          ${row.survey?.repeatable ? '<span class="pill">repeatable</span>' : ""}
          ${row.survey?.editable ? '<span class="pill">editable</span>' : ""}
        </div>
      </article>`;
    }
    function renderList() {
      const rows = filteredSurveys().sort(orderSort);
      $("surveyCount").textContent = `${rows.length} shown`;
      $("surveyList").innerHTML = rows.length ? rows.map(renderSurveyRow).join("") : '<div class="empty">No surveys match this filter.</div>';
    }
    function sortForScope(entries, audience, isoDate, bucketKey) {
      const ids = cleanIds(state.dateOrders[scopeKey(audience, isoDate, bucketKey)]);
      if (!ids.length) return entries.sort(orderSort);
      const position = new Map(ids.map((id, index) => [id, index]));
      return entries.sort((a, b) => {
        const ai = position.has(a.id) ? position.get(a.id) : Number.MAX_SAFE_INTEGER;
        const bi = position.has(b.id) ? position.get(b.id) : Number.MAX_SAFE_INTEGER;
        return ai - bi || orderSort(a, b);
      });
    }
    function previewBuckets(audience, isoDate) {
      const available = [];
      const late = [];
      scheduleRows.forEach((row) => {
        if (!visibleForPreview(row, audience, isoDate)) return;
        if (rowAvailableOnDate(row, isoDate)) available.push(row);
        else if (rowLateOnDate(row, isoDate)) late.push(row);
      });
      return [
        ["available_now", "Available now", sortForScope(available, audience, isoDate, "available_now")],
        ["late_but_accepted", "Late but accepted", sortForScope(late, audience, isoDate, "late_but_accepted")],
        ["completed", "Completed", []],
      ];
    }
    function renderPreviewEntry(entry, date) {
      return `<div class="preview-entry" draggable="true" data-drag-row="${esc(entry.id)}">
        <div><strong>${esc(entry.title || entry.survey_slug)}</strong></div>
        <div class="pill-row">
          <span class="pill">${currentOrder(entry.id) ?? "blank"}</span>
          <code>${esc(entry.survey_slug)} · ${esc(entry.id)}</code>
          <span class="muted">${entry.window_end && entry.window_end < date ? `Was due ${esc(entry.window_end)}` : ""}</span>
        </div>
      </div>`;
    }
    function renderPreview() {
      const date = state.date === ALL ? (AUDIT_DATA.logical_today || AUDIT_DATA.sidebar_simulations?.[0]?.logical_today || allDates()[0]) : state.date;
      const audiences = state.audience === ALL ? ["group_w_first", "group_q_first"] : [state.audience];
      $("preview").innerHTML = audiences.map((audience) => `<div class="bucket">
        <h3>${esc(audienceLabels[audience] || audience)} · ${esc(date)}</h3>
        ${previewBuckets(audience, date).map(([bucketKey, label, entries]) => {
          const key = scopeKey(audience, date, bucketKey);
          const savedCount = cleanIds(state.dateOrders[key]).length;
          return `<div class="preview-section" data-scope="${esc(key)}">
            <div class="preview-section-head">
              <div class="muted">${esc(label)}</div>
              <div class="button-row">
                ${savedCount ? `<span class="pill">${savedCount} saved</span>` : ""}
                ${entries.length > 1 ? `<button type="button" class="action" data-save-scope="${esc(key)}">Commit</button>` : ""}
                ${savedCount ? `<button type="button" class="action" data-clear-scope="${esc(key)}">Clear</button>` : ""}
              </div>
            </div>
            <div class="preview-list" data-drop-scope="${esc(key)}">
              ${entries.length ? entries.map((entry) => renderPreviewEntry(entry, date)).join("") : '<div class="empty">Empty</div>'}
            </div>
          </div>`;
        }).join("")}
      </div>`).join("");
    }
    function renderExport() {
      const compiled = compiledOrder();
      const changes = changedMap();
      const full = compiled.ok ? compiled.map : {};
      $("savedScopeCount").textContent = `${compiled.scopeEntries.length} saved`;
      $("compiledCount").textContent = compiled.ok ? `${Object.keys(full).length} compiled` : "conflict";
      $("conflictBox").hidden = compiled.ok;
      $("conflictBox").textContent = compiled.conflict || "";
      $("scopeList").innerHTML = compiled.scopeEntries.length
        ? compiled.scopeEntries.map(([key, ids]) => `<div class="scope-row">
            <div><code>${esc(scopeLabel(key))}</code><div class="muted">${ids.length} rows</div></div>
            <button type="button" class="action" data-clear-scope="${esc(key)}">Clear</button>
          </div>`).join("")
        : '<div class="empty">No committed date orders yet.</div>';
      $("jsonOut").value = compiled.ok ? JSON.stringify(full, null, 2) : "{}";
      $("commandOut").value = compiled.ok
        ? `DB_HOST=localhost python ${MANAGE_PY} apply_survey_sidebar_order --clear-missing --write-source --json '${JSON.stringify(full)}'`
        : "Resolve ordering conflict before applying.";
      $("sourceOut").value = compiled.ok
        ? "SIDEBAR_ORDER = {\\n" + Object.entries(full).sort((a, b) => a[1] - b[1] || a[0].localeCompare(b[0])).map(([key, value]) => `    '${key}': ${value},`).join("\\n") + "\\n}"
        : "Resolve ordering conflict before applying.";
      $("changedCount").textContent = `${Object.keys(changes).length} changed`;
    }
    function renderAll() { renderList(); renderPreview(); renderExport(); }
    function renumberRows(rows) {
      rows.sort(orderSort).forEach((row, index) => { state.orders[row.id] = index + 1; });
      renderAll();
    }
    function clearRows(rows) {
      rows.forEach((row) => { state.orders[row.id] = null; });
      renderAll();
    }
    function moveRow(id, delta) {
      const rows = filteredSurveys().sort(orderSort);
      if (!rows.every((row) => currentOrder(row.id) != null)) {
        rows.forEach((row, index) => { state.orders[row.id] = index + 1; });
      }
      const index = rows.findIndex((row) => row.id === id);
      const nextIndex = index + Number(delta);
      if (index < 0 || nextIndex < 0 || nextIndex >= rows.length) return;
      const a = rows[index];
      const b = rows[nextIndex];
      const ao = currentOrder(a.id);
      state.orders[a.id] = currentOrder(b.id);
      state.orders[b.id] = ao;
      renderAll();
    }
    function scopeListElement(key) {
      return Array.from(document.querySelectorAll("[data-drop-scope]"))
        .find((element) => element.dataset.dropScope === key);
    }
    function idsFromScopeDom(key) {
      const list = scopeListElement(key);
      if (!list) return [];
      return Array.from(list.querySelectorAll("[data-drag-row]"))
        .map((element) => element.dataset.dragRow);
    }
    function commitScopeOrder(key, ids) {
      const clean = cleanIds(ids);
      if (clean.length > 1) state.dateOrders[key] = clean;
      else delete state.dateOrders[key];
      syncOrdersFromCompiled();
      renderAll();
    }
    function clearScopeOrder(key) {
      delete state.dateOrders[key];
      syncOrdersFromCompiled();
      renderAll();
    }
    function dragAfterElement(container, y) {
      const candidates = Array.from(container.querySelectorAll("[data-drag-row]:not(.dragging)"));
      return candidates.reduce((closest, child) => {
        const box = child.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;
        if (offset < 0 && offset > closest.offset) return { offset, element: child };
        return closest;
      }, { offset: Number.NEGATIVE_INFINITY, element: null }).element;
    }
    function handlePreviewDragStart(event) {
      const row = event.target.closest("[data-drag-row]");
      const list = event.target.closest("[data-drop-scope]");
      if (!row || !list) return;
      state.dragging = { rowId: row.dataset.dragRow, scopeKey: list.dataset.dropScope };
      row.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", row.dataset.dragRow);
    }
    function handlePreviewDragOver(event) {
      const list = event.target.closest("[data-drop-scope]");
      if (!list || !state.dragging || list.dataset.dropScope !== state.dragging.scopeKey) return;
      event.preventDefault();
      const dragging = list.querySelector(".dragging");
      if (!dragging) return;
      const after = dragAfterElement(list, event.clientY);
      if (after) list.insertBefore(dragging, after);
      else list.appendChild(dragging);
    }
    function handlePreviewDrop(event) {
      const list = event.target.closest("[data-drop-scope]");
      if (!list || !state.dragging || list.dataset.dropScope !== state.dragging.scopeKey) return;
      event.preventDefault();
      commitScopeOrder(list.dataset.dropScope, idsFromScopeDom(list.dataset.dropScope));
    }
    function handlePreviewDragEnd() {
      document.querySelectorAll(".preview-entry.dragging").forEach((element) => {
        element.classList.remove("dragging");
      });
      state.dragging = null;
    }
    function selectText(id) { const el = $(id); el.focus(); el.select(); }
    function init() {
      renderFilters();
      $("search").addEventListener("input", (event) => { state.search = event.target.value; renderAll(); });
      $("fileFilter").addEventListener("change", (event) => { state.file = event.target.value; renderAll(); });
      $("audienceFilter").addEventListener("change", (event) => { state.audience = event.target.value; renderAll(); });
      $("dateFilter").addEventListener("change", (event) => { state.date = event.target.value; renderAll(); });
      $("changedOnly").addEventListener("change", (event) => { state.changedOnly = event.target.checked; renderAll(); });
      $("preview").addEventListener("dragstart", handlePreviewDragStart);
      $("preview").addEventListener("dragover", handlePreviewDragOver);
      $("preview").addEventListener("drop", handlePreviewDrop);
      $("preview").addEventListener("dragend", handlePreviewDragEnd);
      $("preview").addEventListener("click", (event) => {
        const save = event.target.closest("[data-save-scope]");
        if (save) {
          commitScopeOrder(save.dataset.saveScope, idsFromScopeDom(save.dataset.saveScope));
          return;
        }
        const clear = event.target.closest("[data-clear-scope]");
        if (clear) clearScopeOrder(clear.dataset.clearScope);
      });
      $("scopeList").addEventListener("click", (event) => {
        const clear = event.target.closest("[data-clear-scope]");
        if (clear) clearScopeOrder(clear.dataset.clearScope);
      });
      $("surveyList").addEventListener("input", (event) => {
        const input = event.target.closest("[data-order-for]");
        if (!input) return;
        state.orders[input.dataset.orderFor] = input.value === "" ? null : Number(input.value);
        renderPreview();
        renderExport();
      });
      $("surveyList").addEventListener("click", (event) => {
        const mover = event.target.closest("[data-move]");
        if (mover) {
          moveRow(mover.dataset.move, mover.dataset.delta);
          return;
        }
        if (event.target.closest("[data-order-for]")) return;
        const row = event.target.closest("[data-row-id]");
        if (!row) return;
        const id = row.dataset.rowId;
        if (state.selected.has(id)) state.selected.delete(id);
        else state.selected.add(id);
        renderList();
      });
      $("renumberShown").addEventListener("click", () => renumberRows(state.selected.size ? filteredSurveys().filter((row) => state.selected.has(row.id)) : filteredSurveys()));
      $("clearShown").addEventListener("click", () => clearRows(state.selected.size ? filteredSurveys().filter((row) => state.selected.has(row.id)) : filteredSurveys()));
      $("clearDateOrders").addEventListener("click", () => {
        state.dateOrders = {};
        syncOrdersFromCompiled();
        renderAll();
      });
      $("resetAll").addEventListener("click", () => {
        scheduleRows.forEach((row) => { state.orders[row.id] = row.originalOrder; });
        state.dateOrders = {};
        state.synthesizedIds = new Set();
        state.selected.clear();
        renderAll();
      });
      $("selectChanged").addEventListener("click", () => { state.selected = new Set(Object.keys(changedMap())); renderList(); });
      $("copyJson").addEventListener("click", () => selectText("jsonOut"));
      $("copyCommand").addEventListener("click", () => selectText("commandOut"));
      $("copySource").addEventListener("click", () => selectText("sourceOut"));
      renderAll();
    }
    init();
  </script>
</body>
</html>
"""
    return html.replace('__AUDIT_DATA__', data)


def render_audit_html(audit: dict[str, Any]) -> str:
    data = json.dumps(audit, ensure_ascii=False).replace('</', '<\\/')
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WhoamI Survey Audit</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #172026;
      --muted: #5d6872;
      --line: #d7dde2;
      --paper: #f7f8f5;
      --panel: #ffffff;
      --accent: #126a5a;
      --accent-2: #b45f06;
      --danger: #9f1d1d;
      --soft: #eef4f1;
      --soft-2: #f3ede5;
      --mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      --body: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: var(--body);
      line-height: 1.45;
    }}
    header {{
      padding: 28px clamp(16px, 4vw, 48px) 18px;
      border-bottom: 1px solid var(--line);
      background: #fcfcfa;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: clamp(30px, 5vw, 54px);
      line-height: .96;
      letter-spacing: 0;
      font-weight: 780;
    }}
    .subtitle {{
      margin: 0;
      color: var(--muted);
      max-width: 960px;
      font-size: 15px;
    }}
    .nav-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin-top: 12px;
    }}
    .nav-links a {{
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      color: var(--ink);
      padding: 7px 10px;
      text-decoration: none;
      font-size: 13px;
      font-weight: 650;
    }}
    .nav-links a.active {{
      border-color: var(--accent);
      background: var(--soft);
      color: #163d36;
    }}
    main {{
      padding: 20px clamp(12px, 3vw, 36px) 44px;
      display: grid;
      gap: 16px;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 10px;
    }}
    .metric, .panel, details.survey-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .metric {{
      padding: 14px;
      min-height: 76px;
    }}
    .metric strong {{
      display: block;
      font-size: 28px;
      line-height: 1;
    }}
    .metric span {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    .panel {{
      padding: 14px;
      overflow: hidden;
    }}
    .controls {{
      display: grid;
      grid-template-columns: minmax(220px, 2fr) repeat(4, minmax(130px, 1fr));
      gap: 10px;
    }}
    input, select {{
      width: 100%;
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      padding: 8px 10px;
      font: inherit;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 18px;
      letter-spacing: 0;
    }}
    .warnings {{
      display: grid;
      gap: 8px;
    }}
    .warning {{
      border-left: 4px solid var(--danger);
      background: #fff7f5;
      padding: 10px 12px;
      border-radius: 6px;
      color: #4d1b17;
    }}
    .sidebar-simulations {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
      align-items: start;
    }}
    .sidebar-phone {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f8faf8;
      padding: 12px;
      display: grid;
      gap: 12px;
    }}
    .sidebar-top {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: baseline;
      border-bottom: 1px solid var(--line);
      padding-bottom: 8px;
    }}
    .pause-banner {{
      border: 1px solid #8700ff;
      border-radius: 12px;
      background: #f3e8ff;
      color: #4b008f;
      padding: 12px 14px;
      font-size: 14px;
      font-weight: 650;
    }}
    .sidebar-bucket {{
      display: grid;
      gap: 8px;
    }}
    .sidebar-bucket h3 {{
      margin: 0;
      font-size: 17px;
      letter-spacing: 0;
    }}
    .sidebar-row {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 12px 14px;
      display: grid;
      gap: 6px;
    }}
    .sidebar-row-head {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .hidden-available {{
      border-top: 1px dashed var(--line);
      padding-top: 10px;
    }}
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      min-width: 1080px;
      background: #fff;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 11px;
      text-align: left;
      vertical-align: top;
      font-size: 13px;
    }}
    th {{
      position: sticky;
      top: 0;
      z-index: 1;
      background: #eef2ee;
      color: #263238;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    tr:last-child td {{ border-bottom: 0; }}
    tr[data-missing="true"] td {{ background: #fff8f3; }}
    code, .slug {{
      font-family: var(--mono);
      font-size: 12px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 7px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--soft);
      color: #24433d;
      white-space: nowrap;
      font-size: 12px;
      font-weight: 650;
    }}
    .pill.orange {{
      background: var(--soft-2);
      color: #653800;
    }}
    .pill.gray {{
      background: #f0f1f2;
      color: #4d5962;
    }}
    .survey-list {{
      display: grid;
      gap: 10px;
    }}
    details.survey-card {{
      padding: 0;
    }}
    summary {{
      cursor: pointer;
      list-style: none;
      padding: 13px 14px;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: center;
    }}
    summary::-webkit-details-marker {{ display: none; }}
    .survey-title {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: baseline;
    }}
    .survey-title strong {{
      font-size: 15px;
    }}
    .survey-body {{
      border-top: 1px solid var(--line);
      padding: 12px 14px 16px;
      display: grid;
      gap: 12px;
    }}
    .meta-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
    }}
    .question {{
      border-top: 1px solid var(--line);
      padding-top: 10px;
      display: grid;
      gap: 5px;
    }}
    .q-head {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .q-text {{
      font-size: 14px;
    }}
    .muted {{
      color: var(--muted);
    }}
    .hidden {{
      display: none !important;
    }}
    @media (max-width: 760px) {{
      .controls {{ grid-template-columns: 1fr; }}
      summary {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 34px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>WhoamI Survey Audit</h1>
    <p class="subtitle">Expanded from endpoint.yaml, weekly_anytime.yaml, sotd.yaml, daily.yaml, and pre.yaml. Dates reflect setup_survey_state schedule overlays, including W/Q routing, weekend-only weekly windows, SOTD reschedules, and late-answer rules.</p>
    <nav class="nav-links" aria-label="Audit pages">
      <a href="survey_user_audit.html">Full click-through audit</a>
      <a href="survey_audit.html" class="active">Source timeline audit</a>
      <a href="survey_priority_audit.html">Sidebar order editor</a>
    </nav>
  </header>
  <main>
    <section class="summary" id="summary"></section>
    <section class="panel">
      <div class="controls">
        <input id="search" type="search" placeholder="Search slug, title, prompt, date, audience">
        <select id="dateFilter"><option value="">All dates</option></select>
        <select id="fixtureFilter"><option value="">All fixtures</option></select>
        <select id="cadenceFilter"><option value="">All cadences</option></select>
        <select id="audienceFilter"><option value="">All audiences</option></select>
      </div>
    </section>
    <section class="panel" id="warningsPanel">
      <h2>Warnings</h2>
      <div class="warnings" id="warnings"></div>
    </section>
    <section class="panel" id="sidebarSimulationPanel">
      <h2>No-response sidebar simulation</h2>
      <p class="muted">What a user with no survey responses would see on the Surveys page, split by W/Q assignment and rendered in the same bucket order as the app.</p>
      <div class="sidebar-simulations" id="sidebarSimulations"></div>
    </section>
    <section class="panel">
      <h2>Schedule Timeline</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Date window</th>
              <th>Audience</th>
              <th>Cadence</th>
              <th>Surface</th>
              <th>Survey</th>
              <th>Fixture</th>
              <th>Questions</th>
              <th>Late rule</th>
            </tr>
          </thead>
          <tbody id="scheduleRows"></tbody>
        </table>
      </div>
    </section>
    <section class="panel">
      <h2>Survey Questions</h2>
      <div class="survey-list" id="surveyList"></div>
    </section>
  </main>
  <script>
    const AUDIT_DATA = {data};

    const state = {{
      search: '',
      date: '',
      fixture: '',
      cadence: '',
      audience: '',
    }};

    const $ = (id) => document.getElementById(id);
    const lower = (value) => String(value || '').toLowerCase();
    const unique = (values) => [...new Set(values.filter(Boolean))].sort();

    function setOptions(id, values, labeler = (v) => v) {{
      const select = $(id);
      for (const value of values) {{
        const option = document.createElement('option');
        option.value = value;
        option.textContent = labeler(value);
        select.appendChild(option);
      }}
    }}

    function scheduleText(row) {{
      return [
        row.window_start,
        row.window_end,
        row.audience,
        row.audience_label,
        row.cadence,
        row.featured_surface,
        row.survey_slug,
        row.source_file,
        row.title,
        row.late_behavior,
      ].join(' ');
    }}

    function surveyText(survey) {{
      return [
        survey.slug,
        survey.source_file,
        survey.title,
        survey.description,
        ...survey.questions.flatMap((q) => [
          q.slug,
          q.type,
          q.prompt,
          q.content,
          q.description,
          q.options.map((o) => o.label).join(' '),
        ]),
      ].join(' ');
    }}

    function rowPasses(row) {{
      if (state.date && row.window_start !== state.date) return false;
      if (state.fixture && row.source_file !== state.fixture) return false;
      if (state.cadence && row.cadence !== state.cadence) return false;
      if (state.audience && row.audience !== state.audience) return false;
      if (state.search && !lower(scheduleText(row)).includes(state.search)) return false;
      return true;
    }}

    function surveyPasses(survey) {{
      if (state.fixture && survey.source_file !== state.fixture) return false;
      if (state.search && !lower(surveyText(survey)).includes(state.search)) return false;
      if (state.cadence || state.audience || state.date) {{
        return AUDIT_DATA.schedule_rows.some((row) =>
          row.survey_slug === survey.slug && rowPasses(row)
        );
      }}
      return true;
    }}

    function renderSummary() {{
      const summary = AUDIT_DATA.summary;
      const metrics = [
        ['Surveys', summary.survey_count],
        ['Questions', summary.question_count],
        ['Schedule rows', summary.schedule_row_count],
        ['Warnings', summary.warning_count],
        ['Unscheduled', summary.unscheduled_survey_count],
      ];
      $('summary').innerHTML = metrics.map(([label, value]) => `
        <div class="metric"><strong>${{value}}</strong><span>${{label}}</span></div>
      `).join('');
    }}

    function renderWarnings() {{
      const warnings = AUDIT_DATA.warnings || [];
      $('warningsPanel').classList.toggle('hidden', warnings.length === 0);
      $('warnings').innerHTML = warnings.map((warning) =>
        `<div class="warning">${{escapeHtml(warning)}}</div>`
      ).join('');
    }}

    function renderSidebarSimulations() {{
      const simulations = AUDIT_DATA.sidebar_simulations || [];
      $('sidebarSimulationPanel').classList.toggle('hidden', simulations.length === 0);
      $('sidebarSimulations').innerHTML = simulations.map(renderSidebarSimulation).join('');
    }}

    function renderSidebarSimulation(simulation) {{
      const visibleBuckets = simulation.bucket_order
        .map((bucket) => renderSidebarBucket(simulation, bucket))
        .filter(Boolean)
        .join('');
      const hiddenAvailable = renderHiddenAvailable(simulation);
      const emptyState = visibleBuckets
        ? ''
        : '<div class="muted">Nothing here yet.</div>';
      return `
        <div class="sidebar-phone">
          <div class="sidebar-top">
            <strong>${{escapeHtml(simulation.audience_label)}}</strong>
            <span class="muted">${{escapeHtml(simulation.logical_today)}}</span>
          </div>
          ${{simulation.is_paused ? `<div class="pause-banner">🛠️ ${{escapeHtml(simulation.pause_message_en)}}</div>` : ''}}
          ${{emptyState}}
          ${{visibleBuckets}}
          ${{hiddenAvailable}}
        </div>
      `;
    }}

    function renderSidebarBucket(simulation, bucket) {{
      const entries = simulation.buckets[bucket] || [];
      if (!entries.length) return '';
      const label = simulation.bucket_labels[bucket] || bucket;
      return `
        <div class="sidebar-bucket">
          <h3>${{escapeHtml(label)}}</h3>
          ${{entries.map(renderSidebarRow).join('')}}
        </div>
      `;
    }}

    function renderHiddenAvailable(simulation) {{
      const entries = simulation.hidden_available_now || [];
      if (!entries.length) return '';
      return `
        <div class="sidebar-bucket hidden-available">
          <h3>Available now hidden while paused</h3>
          <div class="muted">These are the rows the API would return in Available now; the app hides this whole bucket until the pause lifts.</div>
          ${{entries.map(renderSidebarRow).join('')}}
        </div>
      `;
    }}

    function renderSidebarRow(entry) {{
      const sourceNote = entry.source_found_in_selected_fixtures
        ? ''
        : `<div class="muted"><code>${{escapeHtml(entry.survey_slug)}}</code> source is outside the selected audit fixtures: ${{escapeHtml(entry.runtime_source_file || 'missing')}}</div>`;
      return `
        <div class="sidebar-row">
          <div class="sidebar-row-head">
            <strong>${{escapeHtml(entry.survey_title || entry.survey_slug)}}</strong>
            <span class="pill gray">${{escapeHtml(entry.cadence_label)}}</span>
          </div>
          ${{entry.subtitle_en ? `<div class="muted">${{escapeHtml(entry.subtitle_en)}}</div>` : ''}}
          <div class="muted"><code>${{escapeHtml(entry.survey_slug)}}</code> · ${{escapeHtml(entry.redirect_url)}}</div>
          ${{sourceNote}}
        </div>
      `;
    }}

    function renderSchedule() {{
      const rows = AUDIT_DATA.schedule_rows.filter(rowPasses);
      $('scheduleRows').innerHTML = rows.map((row) => `
        <tr data-missing="${{!row.source_found}}">
          <td><strong>${{row.window_start}}</strong>${{row.window_end ? ` to ${{row.window_end}}` : ' onward'}}</td>
          <td>${{escapeHtml(row.audience_label)}}</td>
          <td><span class="pill gray">${{escapeHtml(row.cadence)}} #${{row.sequence_index}}</span></td>
          <td><span class="pill ${{row.featured_surface === 'Survey of the Day card' ? 'orange' : ''}}">${{escapeHtml(row.featured_surface)}}</span></td>
          <td><code>${{escapeHtml(row.survey_slug)}}</code><br><span class="muted">${{escapeHtml(row.title || 'Source not in selected fixtures')}}</span></td>
          <td>${{row.source_file ? `<code>${{escapeHtml(row.source_file)}}</code>` : '<span class="muted">missing</span>'}}</td>
          <td>${{row.question_count}}</td>
          <td>${{escapeHtml(row.late_behavior)}}</td>
        </tr>
      `).join('');
    }}

    function renderSurveys() {{
      const surveys = Object.values(AUDIT_DATA.surveys)
        .sort((a, b) => a.source_file.localeCompare(b.source_file) || a.slug.localeCompare(b.slug))
        .filter(surveyPasses);
      $('surveyList').innerHTML = surveys.map((survey) => renderSurveyCard(survey)).join('');
    }}

    function renderSurveyCard(survey) {{
      const schedules = AUDIT_DATA.schedule_rows.filter((row) => row.survey_slug === survey.slug);
      const scheduleBits = schedules.map((row) =>
        `${{row.window_start}}${{row.window_end ? `..${{row.window_end}}` : '+'}} / ${{row.audience_label}} / ${{row.cadence}} #${{row.sequence_index}}`
      );
      return `
        <details class="survey-card">
          <summary>
            <div class="survey-title">
              <strong>${{escapeHtml(survey.title || survey.slug)}}</strong>
              <code>${{escapeHtml(survey.slug)}}</code>
              <span class="pill gray">${{escapeHtml(survey.source_file)}}</span>
              <span class="pill">${{survey.question_count}} questions</span>
            </div>
            <span class="muted">${{scheduleBits.length ? escapeHtml(scheduleBits[0]) : 'not scheduled'}}</span>
          </summary>
          <div class="survey-body">
            <div class="meta-grid">
              <div><strong>Type</strong><br>${{escapeHtml(survey.type)}}</div>
              <div><strong>Priority</strong><br>${{survey.priority}}</div>
              <div><strong>Results</strong><br>${{survey.results_hidden ? 'hidden' : 'visible'}}</div>
              <div><strong>Friend visible</strong><br>${{survey.friend_visible ? 'yes' : 'no'}}</div>
              <div><strong>Editable</strong><br>${{survey.editable ? 'yes' : 'no'}}</div>
              <div><strong>Repeatable</strong><br>${{survey.repeatable ? 'yes' : 'no'}}</div>
            </div>
            ${{survey.description ? `<p>${{escapeHtml(survey.description)}}</p>` : ''}}
            ${{scheduleBits.length ? `<div class="muted"><strong>Schedule:</strong> ${{escapeHtml(scheduleBits.join(' | '))}}</div>` : '<div class="muted"><strong>Schedule:</strong> not scheduled by current schedule overlays</div>'}}
            <div>
              ${{survey.questions.map(renderQuestion).join('')}}
            </div>
          </div>
        </details>
      `;
    }}

    function renderQuestion(q) {{
      const text = q.prompt || q.content || '';
      const options = q.options && q.options.length
        ? `<div class="muted"><strong>Options:</strong> ${{q.options.map((o) => `${{o.value}}=${{o.label}}`).map(escapeHtml).join(' | ')}}</div>`
        : '';
      const condition = q.conditional_display && Object.keys(q.conditional_display).length
        ? `<span class="pill orange">conditional</span>`
        : '';
      return `
        <div class="question">
          <div class="q-head">
            <span class="pill gray">#${{q.order}}</span>
            ${{q.slug ? `<code>${{escapeHtml(q.slug)}}</code>` : '<span class="muted">no slug</span>'}}
            <span class="pill">${{escapeHtml(q.type)}}</span>
            ${{q.result_hidden ? '<span class="pill orange">result hidden</span>' : ''}}
            ${{condition}}
          </div>
          <div class="q-text">${{escapeHtml(text)}}</div>
          ${{q.description ? `<div class="muted">${{escapeHtml(q.description)}}</div>` : ''}}
          ${{options}}
        </div>
      `;
    }}

    function escapeHtml(value) {{
      return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
    }}

    function renderAll() {{
      renderSchedule();
      renderSurveys();
    }}

    function init() {{
      renderSummary();
      renderWarnings();
      renderSidebarSimulations();
      setOptions('dateFilter', unique(AUDIT_DATA.schedule_rows.map((row) => row.window_start)));
      setOptions('fixtureFilter', unique(Object.values(AUDIT_DATA.surveys).map((survey) => survey.source_file)));
      setOptions('cadenceFilter', unique(AUDIT_DATA.schedule_rows.map((row) => row.cadence)));
      setOptions('audienceFilter', unique(AUDIT_DATA.schedule_rows.map((row) => row.audience)), (value) => {{
        const row = AUDIT_DATA.schedule_rows.find((candidate) => candidate.audience === value);
        return row ? row.audience_label : value;
      }});
      $('search').addEventListener('input', (event) => {{
        state.search = lower(event.target.value);
        renderAll();
      }});
      for (const [id, key] of [
        ['dateFilter', 'date'],
        ['fixtureFilter', 'fixture'],
        ['cadenceFilter', 'cadence'],
        ['audienceFilter', 'audience'],
      ]) {{
        $(id).addEventListener('change', (event) => {{
          state[key] = event.target.value;
          renderAll();
        }});
      }}
      renderAll();
    }}

    init();
  </script>
</body>
</html>
"""
