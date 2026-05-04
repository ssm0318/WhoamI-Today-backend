"""Render-time token substitution for survey content.

Survey questions reference tokens via `{{name}}` syntax in their prompt,
description, placeholder, and (for display_only) content fields. The
serializer calls `substitute_in_question` to expand these into final
strings before sending the question to the frontend.

Resolution order, first match wins:
  1. Survey-level `tokens` block (e.g. {"phase_label": "Phase 1"}).
  2. User-level UserSurveyEmbeddedData (per-user store populated by prior
     surveys' `embedded_data: true` answers, keyed by question.slug).

Unknown tokens render as the literal `{{name}}` and emit a one-line
warning to the logger so a typo or stale slug surfaces in dev / staging
logs without breaking the survey.
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Optional


if TYPE_CHECKING:
    from surveys.models import Survey, SurveyQuestion


logger = logging.getLogger(__name__)


# Match `{{name}}` where name is alphanumeric + underscores. Whitespace
# inside the braces is allowed and stripped.
_TOKEN_RE = re.compile(r'\{\{\s*(\w+)\s*\}\}')

# Question fields whose values are strings and should have token substitution
# applied. Both _en and _ko variants are processed.
_SUBSTITUTABLE_QUESTION_TEXT_FIELDS = (
    'prompt',
    'description',
    'placeholder',
    'content',
)


def substitute(text: str, tokens: dict) -> str:
    """Replace `{{name}}` occurrences in `text` with `tokens[name]`.

    Tokens are stringified (str(value)) before substitution — JSON ints,
    bools, etc. all become their str representation. Unknown tokens are
    left as literal `{{name}}` and logged.
    """
    if not text or not isinstance(text, str):
        return text

    def repl(m: 're.Match[str]') -> str:
        name = m.group(1)
        if name in tokens:
            return str(tokens[name])
        logger.warning('survey token %r not found; rendering literal', name)
        return m.group(0)

    return _TOKEN_RE.sub(repl, text)


def build_token_map(survey: 'Survey', viewer=None) -> dict:
    """Merge survey-level tokens with the viewer's embedded data.

    Survey-level wins on key collision (intentionally — survey authors can
    override / shadow per-user values when they want phase-specific
    interpolation that doesn't depend on user history).

    `viewer=None` is supported for callers that want substitution outside
    a request context (e.g. management commands, tests).
    """
    # Local import — keeps this module's own import cheap and avoids a
    # circular import via surveys.serializers.
    from surveys.models import UserSurveyEmbeddedData

    tokens: dict = {}
    if viewer is not None and getattr(viewer, 'is_authenticated', False):
        for row in UserSurveyEmbeddedData.objects.filter(user=viewer).only('key', 'value'):
            tokens[row.key] = row.value
    tokens.update(survey.tokens or {})
    return tokens


def apply_to_question_dict(question_data: dict, tokens: dict) -> dict:
    """Mutate-and-return a serialized question dict with substitution applied
    to every (en, ko) pair of the substitutable text fields.

    Intended for use inside SurveyQuestionSerializer.to_representation, where
    the dict has already been built from the model. Mutating in place is
    safe because each request gets its own serializer instance.
    """
    for base in _SUBSTITUTABLE_QUESTION_TEXT_FIELDS:
        for lang in ('en', 'ko'):
            key = f'{base}_{lang}'
            if key in question_data:
                question_data[key] = substitute(question_data[key], tokens)
    return question_data
