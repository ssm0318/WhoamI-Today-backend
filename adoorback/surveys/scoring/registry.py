"""Decorator-based registry of named score formulas.

Use `@register_formula('name')` to add a formula; look up via
`get_formula('name')` (raises KeyError if missing).

`score_response(survey, response)` is the canonical entry point used by
aggregation: it picks the registered formula if `survey.score_formula` is
set, otherwise applies the default sum-with-reverse formula.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional, TYPE_CHECKING


if TYPE_CHECKING:
    from surveys.models import Survey, SurveyResponse


ScoreFormula = Callable[['Survey', 'SurveyResponse'], int]


_REGISTRY: Dict[str, ScoreFormula] = {}


def register_formula(name: str) -> Callable[[ScoreFormula], ScoreFormula]:
    """Decorator: register `func` under `name` in the formula registry.

    Re-registering an existing name raises ValueError so a typo or duplicate
    import surfaces loudly rather than silently shadowing.
    """
    def decorator(func: ScoreFormula) -> ScoreFormula:
        if name in _REGISTRY:
            raise ValueError(f'score formula {name!r} is already registered')
        _REGISTRY[name] = func
        return func
    return decorator


def get_formula(name: str) -> ScoreFormula:
    """Look up a registered formula. Raises KeyError if unknown."""
    return _REGISTRY[name]


def list_formulas() -> list[str]:
    """Sorted list of registered formula names — for admin / debug surfaces."""
    return sorted(_REGISTRY.keys())


def score_response(survey: 'Survey', response: 'SurveyResponse') -> Optional[int]:
    """Compute the scale-score for one user's response to `survey`.

    Returns an int score, or None if no scorable items exist (e.g. the user
    answered every likert_5_na item as N/A).

    Dispatch order:
      1. If `survey.score_formula` is set, look it up and call it.
      2. Otherwise apply the default sum-with-reverse formula:
         - sum every likert_* item's value across the response,
         - inverted to (max + min - value) when reverse_scored=True,
         - skipping likert_5_na items whose value is the N/A sentinel,
         - restricted to `survey.score_components` (question slugs) when
           that list is non-empty.
    """
    if survey.score_formula:
        return get_formula(survey.score_formula)(survey, response)
    return _default_score(survey, response)


def _default_score(survey: 'Survey', response: 'SurveyResponse') -> Optional[int]:
    # Local imports to avoid a circular dependency: registry → models → translation
    # → registry-via-aggregation paths can otherwise tangle.
    from surveys.models import LIKERT_RANGES, NA_SENTINEL

    components = set(survey.score_components or [])
    total = 0
    counted = 0
    for ans in response.answers.select_related('question').all():
        q = ans.question
        if q.type not in LIKERT_RANGES:
            continue
        if components and q.slug not in components:
            continue
        if ans.value is NA_SENTINEL:
            # likert_5_na N/A response — exclude from the sum entirely.
            continue
        v = int(ans.value)
        if q.reverse_scored:
            lo, hi = LIKERT_RANGES[q.type]
            v = (hi + lo) - v
        total += v
        counted += 1
    if counted == 0:
        return None
    return total
