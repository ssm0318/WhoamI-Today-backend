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
    DISPLAY_ONLY,
    INPUT_LESS_TYPES,
    LIKERT_RANGES,
    LIKERT_TYPES,
    NA_SENTINEL,
    RESULT_AGGREGATED_LIKERT,
    RESULT_OPTION_COUNTS,
    RESULT_SCALE_SCORE_HISTOGRAM,
    RESULT_SLIDER_HISTOGRAM,
    RESULT_SLIDER_HISTOGRAM_PAIRED,
    RESULT_WORDCLOUD,
    SLIDER,
    Survey,
    SurveyAnswer,
    SurveyQuestion,
    SurveyResponse,
)


# Default likert range — kept for back-compat with callers that don't know the
# specific likert variant. New code should reach into LIKERT_RANGES[type]
# instead. likert_5 is the dominant variant and matches the historical default.
LIKERT_MIN_VALUE = 1
LIKERT_MAX_VALUE = 5
MIN_TOKEN_FREQUENCY = 3  # k-anonymity threshold for individual wordcloud tokens


def _likert_range(question: SurveyQuestion) -> tuple[int, int]:
    """Return (min, max) for a likert question, defaulting to (1, 5) if the
    question's type isn't one of the registered variants."""
    return LIKERT_RANGES.get(question.type, (LIKERT_MIN_VALUE, LIKERT_MAX_VALUE))


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
    """Sum reverse-aware values across the panel's questions for one response.

    Per-question variant ranges (likert_3..likert_7) feed `_likert_range`, so
    the inversion math is correct for each item. likert_5_na N/A picks
    (value=None) are skipped — they contribute 0 to the sum, NOT (max+min)/2,
    matching the spec's "exclude entirely from scoring" rule.
    """
    total = 0
    for ans in response.answers.select_related('question').all():
        if ans.question_id not in question_ids:
            continue
        if ans.value is NA_SENTINEL:
            continue
        v = int(ans.value)
        if ans.question.reverse_scored:
            lo, hi = _likert_range(ans.question)
            v = (hi + lo) - v
        total += v
    return total


class AggregatedLikertStrategy(AggregationStrategy):
    kind = RESULT_AGGREGATED_LIKERT

    def build(self, survey, questions, responder_ids, viewer_id):
        n_questions = len(questions)
        question_ids = {q.id for q in questions}
        # Score range is the SUM of each item's individual range. For a panel of
        # mixed likert variants (rare but allowed), every variant contributes
        # its own min/max — likert_3 caps at 3 per item, likert_7 at 7, etc.
        # likert_5_na items are bounded by their non-N/A range; N/A is skipped
        # at scoring time (see _trait_score_for_response).
        min_score = sum(_likert_range(q)[0] for q in questions) if n_questions else 0
        max_score = sum(_likert_range(q)[1] for q in questions) if n_questions else 0
        responses = SurveyResponse.objects.filter(
            survey=survey, user_id__in=responder_ids
        ).prefetch_related('answers__question')
        scores: list[int] = []
        user_score: Optional[int] = None
        for r in responses:
            s = _trait_score_for_response(r, question_ids)
            scores.append(s)
            if r.user_id == viewer_id:
                user_score = s
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
        counts: Counter = Counter()
        user_choice = None
        answers = SurveyAnswer.objects.filter(
            question=question, response__user_id__in=responder_ids
        ).select_related('response')
        # Counter keys carry the answer's raw value type — int for ordinal
        # codes, str for categorical codes (e.g. "yes"/"no"). SurveyOption.value
        # matches the answer's value type for the same question, so the
        # counts.get(opt.value) lookup below pulls the right bucket without
        # any normalization. Skip None — likert_5_na N/A picks shouldn't
        # land in OptionCountsStrategy in practice, but be defensive.
        for ans in answers:
            v = ans.value
            if v is None:
                pass
            elif isinstance(v, list):
                for item in v:
                    counts[item] += 1
            else:
                counts[v] += 1
            if ans.response.user_id == viewer_id:
                user_choice = v
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

        values: list[int] = []
        user_value = None
        answers = SurveyAnswer.objects.filter(
            question=question, response__user_id__in=responder_ids,
        ).select_related('response')
        for ans in answers:
            v = int(ans.value)
            if v < lo or v > hi:
                continue  # defensive: out-of-range values shouldn't have made it past submission
            values.append(v)
            if ans.response.user_id == viewer_id:
                user_value = v
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


class ScaleScoreHistogramStrategy(AggregationStrategy):
    """Whole-survey summary score → histogram of all responders' scores.

    Activated when `survey.result_kind == 'scale_score_histogram'`. The view
    layer wraps the entire survey in a single synthetic panel and dispatches
    here, bypassing the per-question grouping. Score per response comes from
    `surveys.scoring.score_response`, which honors `survey.score_formula` if
    set (e.g. rsq_brief_weighted) and otherwise applies the default sum-with-
    reverse formula.
    """

    kind = RESULT_SCALE_SCORE_HISTOGRAM

    def build(self, survey, questions, responder_ids, viewer_id):
        # Local import — registry imports models which imports translation
        # which imports models, so module-level import would cycle.
        from surveys.scoring import score_response

        responses = (
            SurveyResponse.objects
            .filter(survey=survey, user_id__in=responder_ids)
            .prefetch_related('answers__question')
        )
        scores: list[int] = []
        user_score: Optional[int] = None
        for r in responses:
            s = score_response(survey, r)
            if s is not None:
                scores.append(s)
        # Viewer's own score queried separately so operator viewers (filtered
        # out of responder_ids by privacy.compute_responder_ids) still see
        # their own score highlighted on the histogram. Mirrors the pattern
        # in OptionCounts/SliderHistogram strategies.
        viewer_resp = (
            SurveyResponse.objects
            .filter(survey=survey, user_id=viewer_id)
            .prefetch_related('answers__question')
            .first()
        )
        if viewer_resp is not None:
            user_score = score_response(survey, viewer_resp)

        if not scores:
            return {
                'kind': self.kind,
                'min_score': None,
                'max_score': None,
                'bins': [],
                'mean': None,
                'median': None,
                'user_score': user_score,
            }

        min_score = min(scores)
        max_score = max(scores)
        counter = Counter(scores)
        bins = [
            {'score': i, 'count': counter.get(i, 0)}
            for i in range(min_score, max_score + 1)
        ]
        return {
            'kind': self.kind,
            'min_score': min_score,
            'max_score': max_score,
            'bins': bins,
            'mean': round(sum(scores) / len(scores), 2),
            'median': float(median(scores)),
            'user_score': user_score,
        }


class SliderHistogramPairedStrategy(AggregationStrategy):
    """2D circumplex for two slider questions sharing a result_group.

    Surveys with `result_kind = 'slider_histogram_paired'` route here. The
    panel must contain exactly two slider questions; their values for each
    responder form an (x, y) point. The frontend renders the points as a
    scatter plot, optionally with a density overlay.

    Mirrors the user_choice/user_value pattern from OptionCounts: builds the
    population dataset from `responder_ids` (operators excluded) and the
    viewer's own (x, y) separately so it can be highlighted regardless.
    """

    kind = RESULT_SLIDER_HISTOGRAM_PAIRED

    def build(self, survey, questions, responder_ids, viewer_id):
        sliders = [q for q in questions if q.type == SLIDER]
        if len(sliders) < 2:
            # Degenerate panel — can't form (x, y) pairs.
            return {
                'kind': self.kind,
                'x_question_id': sliders[0].id if sliders else None,
                'y_question_id': None,
                'x_min': None,
                'x_max': None,
                'y_min': None,
                'y_max': None,
                'points': [],
                'user_point': None,
            }
        qx, qy = sliders[0], sliders[1]
        # Pair answers by response_id — only count responses that have
        # values for BOTH sliders. Single-axis answers can't plot.
        x_answers = {
            ans.response_id: int(ans.value)
            for ans in SurveyAnswer.objects.filter(
                question=qx, response__user_id__in=responder_ids,
            )
            if ans.value is not None
        }
        y_answers = {
            ans.response_id: int(ans.value)
            for ans in SurveyAnswer.objects.filter(
                question=qy, response__user_id__in=responder_ids,
            )
            if ans.value is not None
        }
        points = [
            {'x': x_answers[rid], 'y': y_answers[rid]}
            for rid in x_answers
            if rid in y_answers
        ]
        # Viewer's own point — separate query so operator viewers see their
        # own point even when excluded from population aggregation.
        user_point = None
        viewer_x = SurveyAnswer.objects.filter(
            question=qx, response__user_id=viewer_id,
        ).values_list('value', flat=True).first()
        viewer_y = SurveyAnswer.objects.filter(
            question=qy, response__user_id=viewer_id,
        ).values_list('value', flat=True).first()
        if viewer_x is not None and viewer_y is not None:
            user_point = {'x': int(viewer_x), 'y': int(viewer_y)}
        return {
            'kind': self.kind,
            'x_question_id': qx.id,
            'y_question_id': qy.id,
            'x_min': qx.slider_min_value,
            'x_max': qx.slider_max_value,
            'y_min': qy.slider_min_value,
            'y_max': qy.slider_max_value,
            'points': points,
            'user_point': user_point,
        }


STRATEGIES: dict[str, AggregationStrategy] = {
    RESULT_AGGREGATED_LIKERT: AggregatedLikertStrategy(),
    RESULT_OPTION_COUNTS: OptionCountsStrategy(),
    RESULT_WORDCLOUD: WordcloudStrategy(),
    RESULT_SLIDER_HISTOGRAM: SliderHistogramStrategy(),
    RESULT_SCALE_SCORE_HISTOGRAM: ScaleScoreHistogramStrategy(),
    RESULT_SLIDER_HISTOGRAM_PAIRED: SliderHistogramPairedStrategy(),
}


def group_panels_for_survey_level_kind(
    survey: Survey,
) -> list[tuple[str, list[SurveyQuestion]]]:
    """Build the panel list when `survey.result_kind` is set on the Survey
    rather than per-question.

    - `scale_score_histogram` → ONE synthetic panel containing every
      non-hidden, scorable question. The strategy computes a single summary
      score per response, so per-question grouping is irrelevant.
    - `slider_histogram_paired` → ONE panel per `result_group` that
      contains 2+ slider questions. Each pair becomes a separate 2D plot.

    Returns the same shape as `group_panels` so callers can switch on
    `survey.result_kind` once and reuse the existing per-panel rendering
    pipeline.
    """
    questions = [
        q for q in survey.questions.order_by('order')
        if not q.result_hidden and q.type not in INPUT_LESS_TYPES
    ]
    if survey.result_kind == RESULT_SCALE_SCORE_HISTOGRAM:
        return [('__survey__', questions)] if questions else []
    if survey.result_kind == RESULT_SLIDER_HISTOGRAM_PAIRED:
        groups: dict[str, list[SurveyQuestion]] = {}
        order: list[str] = []
        for q in questions:
            if q.type != SLIDER:
                continue
            key = q.result_group or '__auto__:slider_paired'
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(q)
        # Filter to groups with 2+ sliders — single-slider groups can't pair.
        return [(k, groups[k]) for k in order if len(groups[k]) >= 2]
    # Fallback (shouldn't happen — caller checks survey.result_kind first).
    return []


def group_panels(survey: Survey) -> list[tuple[str, list[SurveyQuestion]]]:
    """Group a survey's non-hidden, scorable questions into panels by
    ``effective_group_key``.

    Returns a list of ``(group_key, [questions])`` preserving the order in which
    each group's first question appears.

    Skipped:
      - questions with ``result_hidden=True``
      - input-less questions (``display_only``) — they have no value to
        aggregate and shouldn't appear on the results page
    """
    groups: dict[str, list[SurveyQuestion]] = {}
    order: list[str] = []
    for q in survey.questions.order_by('order'):
        if q.result_hidden:
            continue
        if q.type in INPUT_LESS_TYPES:
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
