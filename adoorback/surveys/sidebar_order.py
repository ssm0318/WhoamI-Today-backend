"""Commit-backed ordering for rows in the survey sidebar.

Keys are ``"<cadence>:<sequence_index>"`` for ScheduledSurvey rows, e.g.
``"daily:104"`` or ``"endpoint:2"``. Lower numbers appear earlier within
each sidebar bucket. Rows omitted from this map fall back to the legacy order:
survey priority, window start, then sequence index.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


SIDEBAR_ORDER: dict[str, int] = {
    'endpoint:2': 1,
    'endpoint:3': 1,
    'endpoint:22': 1,
    'biweekly:6': 2,
    'endpoint:4': 3,
    'biweekly:2': 4,
    'biweekly:3': 4,
}


def schedule_order_key(cadence: str, sequence_index: int) -> str:
    return f'{cadence}:{int(sequence_index)}'


def scheduled_survey_order_key(row: Any) -> str:
    return schedule_order_key(row.cadence, row.sequence_index)


def normalize_sidebar_order_map(raw: dict[str, Any] | None) -> dict[str, int | None]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError('sidebar order map must be a JSON object / Python dict')

    normalized: dict[str, int | None] = {}
    for key, value in raw.items():
        key = str(key).strip()
        if ':' not in key:
            raise ValueError(f'invalid schedule key {key!r}; expected "<cadence>:<sequence_index>"')
        cadence, sequence = key.split(':', 1)
        if not cadence or not sequence.isdigit():
            raise ValueError(f'invalid schedule key {key!r}; expected "<cadence>:<sequence_index>"')

        if value in ('', None):
            normalized[key] = None
            continue

        try:
            order = int(value)
        except (TypeError, ValueError):
            raise ValueError(f'order for {key!r} must be an integer or null')
        if order < 1:
            raise ValueError(f'order for {key!r} must be 1 or greater')
        normalized[key] = order
    return normalized


def source_sidebar_order_map(raw: dict[str, Any] | None) -> dict[str, int]:
    normalized = normalize_sidebar_order_map(raw)
    return {
        key: value
        for key, value in normalized.items()
        if value is not None
    }


def apply_sidebar_order_to_model(
    ScheduledSurveyModel,
    order_map: dict[str, Any] | None = None,
    *,
    clear_missing: bool = False,
) -> dict[str, Any]:
    normalized = normalize_sidebar_order_map(SIDEBAR_ORDER if order_map is None else order_map)
    rows = {
        scheduled_survey_order_key(row): row
        for row in ScheduledSurveyModel.objects.all()
    }

    updated: list[str] = []
    cleared: list[str] = []
    missing: list[str] = []

    for key, order in normalized.items():
        row = rows.get(key)
        if not row:
            missing.append(key)
            continue
        if row.sidebar_order == order:
            continue
        row.sidebar_order = order
        row.save(update_fields=['sidebar_order'])
        (cleared if order is None else updated).append(key)

    if clear_missing:
        for key, row in rows.items():
            if key in normalized or row.sidebar_order is None:
                continue
            row.sidebar_order = None
            row.save(update_fields=['sidebar_order'])
            cleared.append(key)

    return {
        'updated': updated,
        'cleared': cleared,
        'missing': missing,
    }


def render_sidebar_order_source(order_map: dict[str, Any] | None) -> str:
    source_map = source_sidebar_order_map(order_map)
    lines = [
        '"""Commit-backed ordering for rows in the survey sidebar.',
        '',
        'Keys are ``"<cadence>:<sequence_index>"`` for ScheduledSurvey rows, e.g.',
        '``"daily:104"`` or ``"endpoint:2"``. Lower numbers appear earlier within',
        'each sidebar bucket. Rows omitted from this map fall back to the legacy order:',
        'survey priority, window start, then sequence index.',
        '"""',
        'from __future__ import annotations',
        '',
        'from pathlib import Path',
        'from typing import Any',
        '',
        '',
        'SIDEBAR_ORDER: dict[str, int] = {',
    ]
    for key, value in sorted(source_map.items(), key=lambda item: (item[1], item[0])):
        lines.append(f'    {key!r}: {value},')
    lines.extend([
        '}',
        '',
        '',
    ])
    helper_source = Path(__file__).read_text(encoding='utf-8').split(
        '\n\ndef schedule_order_key',
        1,
    )[1]
    lines.append('def schedule_order_key' + helper_source)
    if not lines[-1].endswith('\n'):
        lines[-1] += '\n'
    return '\n'.join(lines)


def write_sidebar_order_source(
    order_map: dict[str, Any] | None,
    *,
    path: Path | None = None,
) -> Path:
    target = path or Path(__file__)
    target.write_text(render_sidebar_order_source(order_map), encoding='utf-8')
    return target
