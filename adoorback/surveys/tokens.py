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

# Tokens resolved per virtual row when a per_friend_* question is expanded.
# These are not survey prerequisites and should not be required in
# UserSurveyEmbeddedData before the survey appears in the index.
PER_FRIEND_DYNAMIC_TOKENS = frozenset({
    'friend_name',
    'friend_username',
    'baseline_closeness',
    'baseline_relationship_type',
})

# Question fields whose values are strings and should have token substitution
# applied. Both _en and _ko variants are processed.
_SUBSTITUTABLE_QUESTION_TEXT_FIELDS = (
    'prompt',
    'description',
    'placeholder',
    'content',
)

# Survey-level fields that may contain `{{token}}` references in their
# bilingual variants. The serializer applies substitution to these once per
# survey (cheap — at most six string scans) so the frontend never sees a
# literal `{{habit_platform_label}}` on the survey-of-the-day card,
# /surveys index, or daily archive.
_SUBSTITUTABLE_SURVEY_TEXT_FIELDS = (
    'title',
    'description',
    'interpretation',
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


# Per-question dynamic tokens — populated at expand time when a per-friend
# question is fanned out into one virtual question per friend. Not part of
# the survey-level / embedded-data resolution; built freshly per (question,
# friend) pair so each virtual question carries the right friend's name and
# baseline metadata into the rendered text fields.
def build_per_friend_tokens(friend, baseline_evaluation=None) -> dict:
    """Return a token map for one (per_friend question × friend) expansion.

    `friend` is a User. `baseline_evaluation` is the most recent non-skipped
    FriendEvaluation row written by the requesting user about this friend,
    or None if no evaluation exists.

    Tokens emitted:
      - friend_name             — display name (matches friend-list UI)
      - friend_username         — raw Adoor handle (used for profile links)
      - baseline_closeness      — int 1–5, or omitted if no baseline
      - baseline_relationship_type — code string (e.g. "school_friend"), or omitted
    """
    # Always populate the baseline tokens (with an em-dash fallback when
    # missing) so the substitute() pass doesn't emit "token not found"
    # warnings for friends without a FriendEvaluation row. The frontend
    # reads the dedicated `baseline_closeness` field on the virtual question
    # (set to None when missing) for any conditional UI like hiding the
    # corrected-baseline row when there's nothing to correct.
    tokens = {
        'friend_name': _display_name(friend),
        'friend_username': friend.username,
        'baseline_closeness': '—',
        'baseline_relationship_type': '—',
    }
    if baseline_evaluation is not None:
        if baseline_evaluation.closeness is not None:
            tokens['baseline_closeness'] = baseline_evaluation.closeness
        if baseline_evaluation.relationship_type:
            tokens['baseline_relationship_type'] = baseline_evaluation.relationship_type
    return tokens


def _display_name(user) -> str:
    """Display name used wherever {{friend_name}} appears in a per-friend
    survey question.

    Today this returns the Adoor handle (username), which is what the friend
    list UI shows. If the frontend ever switches to nickname-primary display
    on friend cards, update both places at once so the survey matches what
    participants see elsewhere in the app.
    """
    return user.username


def apply_to_survey_dict(survey_data: dict, tokens: dict) -> dict:
    """Mutate-and-return a serialized survey dict with substitution applied
    to title / description / interpretation (en + ko each).

    The bug this closes: prior to this helper, only question-level fields
    ran through substitution, so a survey whose TITLE contained
    `{{habit_platform_label}}` would surface the literal token on the
    survey-of-the-day card, the /surveys index, and the daily archive.
    """
    for base in _SUBSTITUTABLE_SURVEY_TEXT_FIELDS:
        for lang in ('en', 'ko'):
            key = f'{base}_{lang}'
            if key in survey_data:
                survey_data[key] = substitute(survey_data[key], tokens)
    return survey_data
