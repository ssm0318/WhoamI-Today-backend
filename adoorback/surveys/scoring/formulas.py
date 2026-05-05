"""Built-in score formulas. Imported by surveys.scoring.__init__ at module load
time so the registry is populated whenever Django wires up the app.

Add a new formula by writing a decorated function here. Each formula takes
`(survey, response)` and returns an int score (or None if the response has
no scorable data — see registry.score_response for semantics).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from surveys.scoring.registry import register_formula


if TYPE_CHECKING:
    from surveys.models import Survey, SurveyResponse


# ---------------------------------------------------------------------------
# RSQ — Rejection Sensitivity Questionnaire (Brief)
#
# Eight situations × (concern level × (7 − expectation level)). Each situation
# `i` contributes `concern_i × (7 − expectation_i)` to the total.
#
# Slug convention: `rsq_<n>_concern` and `rsq_<n>_expect` for n in 1..8.
# Both are likert_6 with values 1..6. A response that hasn't answered both
# questions for a situation contributes 0 (the situation is skipped).
# ---------------------------------------------------------------------------
@register_formula('rsq_brief_weighted')
def rsq_brief_weighted(survey: 'Survey', response: 'SurveyResponse') -> Optional[int]:
    """Σ over situations 1..8 of (concern × (7 − expectation))."""
    pairs: dict[int, dict[str, int]] = {}
    for ans in response.answers.select_related('question').all():
        slug = ans.question.slug
        if not slug.startswith('rsq_'):
            continue
        # Slug shape: rsq_<n>_<concern|expect>
        try:
            _, n_str, kind = slug.split('_', 2)
            n = int(n_str)
        except (ValueError, AttributeError):
            continue
        if kind not in {'concern', 'expect'}:
            continue
        if ans.value is None:
            # Defensive: rsq questions shouldn't be likert_5_na, but skip
            # gracefully if the YAML ever marks them so.
            continue
        pairs.setdefault(n, {})[kind] = int(ans.value)

    total = 0
    counted = 0
    for n, kv in pairs.items():
        if 'concern' in kv and 'expect' in kv:
            total += kv['concern'] * (7 - kv['expect'])
            counted += 1
    return total if counted > 0 else None
