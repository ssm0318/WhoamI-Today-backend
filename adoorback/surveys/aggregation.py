"""
Build distributions per-bucket. Two shapes:
- likert_5: aggregated trait-score histogram (sum of item values, reverse-scored applied).
            Returned as {'kind': 'aggregated_likert', 'bins': [{'score': int, 'count': int}, ...],
                          'min_score': int, 'max_score': int, 'user_score': int|None}
- single_choice / multi_choice: per-option counts on the FIRST question.
            Note: multi-question single/multi surveys are out of scope; only the first
            question's distribution is rendered.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from surveys.models import Survey, SurveyAnswer, SurveyResponse


LIKERT_MIN_VALUE = 1
LIKERT_MAX_VALUE = 5


def _trait_score_for_response(response: SurveyResponse) -> int:
    total = 0
    for ans in response.answers.select_related('question').all():
        v = int(ans.value)
        if ans.question.reverse_scored:
            v = LIKERT_MAX_VALUE + LIKERT_MIN_VALUE - v
        total += v
    return total


def build_likert_distribution(survey: Survey, responder_ids: list[int], viewer_id: int):
    n_questions = survey.questions.count()
    min_score = LIKERT_MIN_VALUE * n_questions
    max_score = LIKERT_MAX_VALUE * n_questions
    responses = SurveyResponse.objects.filter(survey=survey, user_id__in=responder_ids).prefetch_related(
        'answers__question'
    )
    scores: list[int] = []
    user_score: Optional[int] = None
    for r in responses:
        s = _trait_score_for_response(r)
        scores.append(s)
        if r.user_id == viewer_id:
            user_score = s
    counter = Counter(scores)
    bins = [{'score': i, 'count': counter.get(i, 0)} for i in range(min_score, max_score + 1)]
    return {
        'kind': 'aggregated_likert',
        'bins': bins,
        'min_score': min_score,
        'max_score': max_score,
        'user_score': user_score,
    }


def build_choice_distribution(survey: Survey, responder_ids: list[int], viewer_id: int):
    question = survey.questions.order_by('order').first()
    if question is None:
        return {'kind': 'option_counts', 'question_id': None, 'options': [], 'user_choice': None}
    options = list(question.options.order_by('order').all())
    counts: Counter = Counter()
    user_choice = None
    answers = SurveyAnswer.objects.filter(
        question=question, response__user_id__in=responder_ids
    ).select_related('response')
    for ans in answers:
        v = ans.value
        if isinstance(v, list):
            for item in v:
                counts[int(item)] += 1
        else:
            counts[int(v)] += 1
        if ans.response.user_id == viewer_id:
            user_choice = v
    return {
        'kind': 'option_counts',
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


def build_distribution(survey: Survey, responder_ids: list[int], viewer_id: int):
    if survey.type == Survey.LIKERT_5:
        return build_likert_distribution(survey, responder_ids, viewer_id)
    return build_choice_distribution(survey, responder_ids, viewer_id)


def compute_user_percentile(distribution: dict, viewer_score: Optional[int]) -> Optional[float]:
    """Percentile rank: fraction of responders with strictly lower score, plus half of those equal."""
    if distribution.get('kind') != 'aggregated_likert' or viewer_score is None:
        return None
    bins = distribution['bins']
    total = sum(b['count'] for b in bins)
    if total == 0:
        return None
    below = sum(b['count'] for b in bins if b['score'] < viewer_score)
    equal = sum(b['count'] for b in bins if b['score'] == viewer_score)
    return round((below + 0.5 * equal) / total, 4)
