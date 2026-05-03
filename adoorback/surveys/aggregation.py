"""
Result aggregation strategies, keyed by question result_kind.

Adding a new view = subclass AggregationStrategy + register in STRATEGIES.
The frontend has a mirrored renderer registry at src/components/survey/results/registry.ts;
keep the keys in sync.

Aggregation runs per *panel* — a panel is a group of questions sharing the same
``effective_group_key`` on a Survey. The strategy receives only the questions in
that panel plus the responder ID set, so it doesn't need to know about siblings.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import Iterable, Optional

from statistics import median

from surveys.models import (
    LIKERT_5,
    RESULT_AGGREGATED_LIKERT,
    RESULT_OPTION_COUNTS,
    RESULT_SLIDER_HISTOGRAM,
    RESULT_WORDCLOUD,
    Survey,
    SurveyAnswer,
    SurveyQuestion,
    SurveyResponse,
)


LIKERT_MIN_VALUE = 1
LIKERT_MAX_VALUE = 5
MIN_TOKEN_FREQUENCY = 3  # k-anonymity threshold for individual wordcloud tokens


class AggregationStrategy(ABC):
    """Each strategy turns a (questions, responder_ids) pair into a typed payload dict.

    The dict's `kind` field MUST match the registry key so the frontend can dispatch.
    """

    kind: str = ''

    @abstractmethod
    def build(
        self,
        survey: Survey,
        questions: list[SurveyQuestion],
        responder_ids: list[int],
        viewer_id: int,
    ) -> dict:
        ...


def _trait_score_for_response(response: SurveyResponse, question_ids: set[int]) -> int:
    """Sum reverse-aware values across the panel's questions for one response."""
    total = 0
    for ans in response.answers.select_related('question').all():
        if ans.question_id not in question_ids:
            continue
        v = int(ans.value)
        if ans.question.reverse_scored:
            v = LIKERT_MAX_VALUE + LIKERT_MIN_VALUE - v
        total += v
    return total


class AggregatedLikertStrategy(AggregationStrategy):
    kind = RESULT_AGGREGATED_LIKERT

    def build(self, survey, questions, responder_ids, viewer_id):
        n_questions = len(questions)
        question_ids = {q.id for q in questions}
        min_score = LIKERT_MIN_VALUE * n_questions
        max_score = LIKERT_MAX_VALUE * n_questions
        # Viewer's own score is queried separately so the highlight on the
        # results page works even when the viewer is filtered out of the
        # aggregation pool (e.g. operator accounts in `_exclude_system_users_qs`).
        user_score: Optional[int] = None
        viewer_response = SurveyResponse.objects.filter(
            survey=survey, user_id=viewer_id
        ).prefetch_related('answers__question').first()
        if viewer_response is not None:
            user_score = _trait_score_for_response(viewer_response, question_ids)
        responses = SurveyResponse.objects.filter(
            survey=survey, user_id__in=responder_ids
        ).prefetch_related('answers__question')
        scores: list[int] = [_trait_score_for_response(r, question_ids) for r in responses]
        counter = Counter(scores)
        bins = [{'score': i, 'count': counter.get(i, 0)} for i in range(min_score, max_score + 1)]
        return {
            'kind': self.kind,
            'bins': bins,
            'min_score': min_score,
            'max_score': max_score,
            'user_score': user_score,
        }


class OptionCountsStrategy(AggregationStrategy):
    """Per-option counts for a single-choice / multi-choice question.

    A panel of single/multi questions is aggregated as one chart per question; this
    strategy delegates: it only handles the FIRST question of the panel. Frontend
    convention is one panel = one chart, so multi-question single/multi panels are
    rare in practice. If they come up, callers should split them into one panel
    per question via explicit `result_group` values.
    """

    kind = RESULT_OPTION_COUNTS

    def build(self, survey, questions, responder_ids, viewer_id):
        question = questions[0] if questions else None
        if question is None:
            return {'kind': self.kind, 'question_id': None, 'options': [], 'user_choice': None}
        options = list(question.options.order_by('order').all())
        # Viewer's own choice is queried separately so the highlight works even
        # when the viewer is filtered out of `responder_ids` (e.g. operators).
        user_choice = SurveyAnswer.objects.filter(
            question=question, response__user_id=viewer_id
        ).values_list('value', flat=True).first()
        counts: Counter = Counter()
        answers = SurveyAnswer.objects.filter(
            question=question, response__user_id__in=responder_ids
        )
        for ans in answers:
            v = ans.value
            if isinstance(v, list):
                for item in v:
                    counts[int(item)] += 1
            else:
                counts[int(v)] += 1
        return {
            'kind': self.kind,
            'question_id': question.id,
            'options': [
                {
                    'option_id': opt.id,
                    'value': opt.value,
                    'label_en': opt.label_en,
                    'label_ko': opt.label_ko,
                    'count': counts.get(opt.value, 0),
                }
                for opt in options
            ],
            'user_choice': user_choice,
        }


_TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)
_STOPWORDS = frozenset({
    'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'i', 'me', 'my', 'we', 'our', 'you', 'your',
    'he', 'she', 'it', 'they', 'them', 'this', 'that', 'these', 'those', 'to', 'of', 'in',
    'on', 'at', 'for', 'with', 'by', 'from', 'as', 'so', 'if', 'then',
})


def _tokenize(text: str) -> list[str]:
    if not isinstance(text, str):
        return []
    tokens = _TOKEN_RE.findall(text.lower())
    return [t for t in tokens if t and t not in _STOPWORDS and len(t) > 1]


class WordcloudStrategy(AggregationStrategy):
    """Tokenize free-text answers across the panel's questions, return per-token counts.

    Privacy: tokens with fewer than MIN_TOKEN_FREQUENCY occurrences are suppressed
    (k-anonymity at the token level). Friend / close-friend buckets are also suppressed
    by ``compute_bucket_eligibility`` for wordcloud-kind panels regardless of group size.
    """

    kind = RESULT_WORDCLOUD

    def build(self, survey, questions, responder_ids, viewer_id):
        question_ids = {q.id for q in questions}
        responses = SurveyResponse.objects.filter(
            survey=survey, user_id__in=responder_ids
        ).prefetch_related('answers')
        token_counts: Counter = Counter()
        viewer_tokens: set[str] = set()
        for r in responses:
            for ans in r.answers.all():
                if ans.question_id not in question_ids:
                    continue
                value = ans.value
                if isinstance(value, list):
                    text = ' '.join(str(v) for v in value)
                else:
                    text = str(value) if value is not None else ''
                tokens = _tokenize(text)
                token_counts.update(tokens)
                if r.user_id == viewer_id:
                    viewer_tokens.update(tokens)
        suppressed = sum(1 for c in token_counts.values() if c < MIN_TOKEN_FREQUENCY)
        visible = [
            {'token': tok, 'count': count}
            for tok, count in token_counts.most_common()
            if count >= MIN_TOKEN_FREQUENCY
        ]
        return {
            'kind': self.kind,
            'tokens': visible,
            'min_token_frequency': MIN_TOKEN_FREQUENCY,
            'suppressed_token_count': suppressed,
            'viewer_tokens': sorted(viewer_tokens),
        }


SLIDER_BIN_COUNT = 10


class SliderHistogramStrategy(AggregationStrategy):
    """Histogram of slider answers across [slider_min_value, slider_max_value].

    Bins are SLIDER_BIN_COUNT equal-width buckets. The lowest bin is
    closed-closed; the rest are half-open on the left and closed on the right
    so every value (including slider_max_value itself) falls in exactly one bin.
    Returns mean and median across all answers.

    A panel of slider questions delegates to its FIRST question for the bin
    range — same convention as OptionCountsStrategy. Multi-question slider
    panels are uncommon; if needed, split via explicit ``result_group``.
    """

    kind = RESULT_SLIDER_HISTOGRAM

    def build(self, survey, questions, responder_ids, viewer_id):
        question = questions[0] if questions else None
        if question is None or question.slider_min_value is None or question.slider_max_value is None:
            return {
                'kind': self.kind,
                'question_id': question.id if question else None,
                'min_value': None,
                'max_value': None,
                'bins': [],
                'mean': None,
                'median': None,
                'user_value': None,
            }

        lo = question.slider_min_value
        hi = question.slider_max_value
        span = hi - lo
        edges = [lo + (span * i) / SLIDER_BIN_COUNT for i in range(SLIDER_BIN_COUNT + 1)]
        bins = [{'lo': edges[i], 'hi': edges[i + 1], 'count': 0} for i in range(SLIDER_BIN_COUNT)]

        # Viewer's own value is queried separately so the highlight works even
        # when the viewer is filtered out of `responder_ids` (e.g. operators).
        viewer_raw = SurveyAnswer.objects.filter(
            question=question, response__user_id=viewer_id
        ).values_list('value', flat=True).first()
        user_value = int(viewer_raw) if viewer_raw is not None else None
        values: list[int] = []
        answers = SurveyAnswer.objects.filter(
            question=question, response__user_id__in=responder_ids,
        )
        for ans in answers:
            v = int(ans.value)
            if v < lo or v > hi:
                continue  # defensive: out-of-range values shouldn't have made it past submission
            values.append(v)
            # Find the bin: clamp to last bucket when value == hi.
            idx = SLIDER_BIN_COUNT - 1 if v == hi else int((v - lo) / span * SLIDER_BIN_COUNT)
            bins[idx]['count'] += 1

        n = len(values)
        return {
            'kind': self.kind,
            'question_id': question.id,
            'min_value': lo,
            'max_value': hi,
            'bins': bins,
            'mean': round(sum(values) / n, 2) if n else None,
            'median': float(median(values)) if n else None,
            'user_value': user_value,
        }


STRATEGIES: dict[str, AggregationStrategy] = {
    RESULT_AGGREGATED_LIKERT: AggregatedLikertStrategy(),
    RESULT_OPTION_COUNTS: OptionCountsStrategy(),
    RESULT_WORDCLOUD: WordcloudStrategy(),
    RESULT_SLIDER_HISTOGRAM: SliderHistogramStrategy(),
}


def group_panels(survey: Survey) -> list[tuple[str, list[SurveyQuestion]]]:
    """Group a survey's non-hidden questions into panels by ``effective_group_key``.

    Returns a list of ``(group_key, [questions])`` preserving the order in which
    each group's first question appears. Hidden questions are skipped entirely.
    """
    groups: dict[str, list[SurveyQuestion]] = {}
    order: list[str] = []
    for q in survey.questions.order_by('order'):
        if q.result_hidden:
            continue
        key = q.effective_group_key
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(q)
    return [(key, groups[key]) for key in order]


def build_panel_distribution(
    survey: Survey,
    panel_questions: list[SurveyQuestion],
    responder_ids: list[int],
    viewer_id: int,
) -> dict:
    """Build the distribution for a single panel using the strategy keyed off the
    first question's effective_result_kind. Falls back to OptionCountsStrategy
    for unknown kinds rather than crashing the endpoint."""
    if not panel_questions:
        return {'kind': RESULT_OPTION_COUNTS, 'question_id': None, 'options': []}
    kind = panel_questions[0].effective_result_kind
    strategy = STRATEGIES.get(kind, STRATEGIES[RESULT_OPTION_COUNTS])
    return strategy.build(survey, panel_questions, responder_ids, viewer_id)


def compute_user_percentile(distribution: dict, viewer_score: Optional[int]) -> Optional[float]:
    """Percentile rank: fraction of responders with strictly lower score, plus half of those equal.

    Only meaningful for distributions that expose a single ordinal `user_score` (i.e. aggregated_likert).
    """
    if distribution.get('kind') != RESULT_AGGREGATED_LIKERT or viewer_score is None:
        return None
    bins = distribution['bins']
    total = sum(b['count'] for b in bins)
    if total == 0:
        return None
    below = sum(b['count'] for b in bins if b['score'] < viewer_score)
    equal = sum(b['count'] for b in bins if b['score'] == viewer_score)
    return round((below + 0.5 * equal) / total, 4)


# Back-compat alias for callers that still expect the old single-distribution shape.
# Deprecated; new callers should iterate group_panels() and call build_panel_distribution.
def build_distribution(survey, responder_ids, viewer_id):  # pragma: no cover
    panels = group_panels(survey)
    if not panels:
        return {'kind': RESULT_OPTION_COUNTS, 'question_id': None, 'options': []}
    _, questions = panels[0]
    return build_panel_distribution(survey, questions, responder_ids, viewer_id)
