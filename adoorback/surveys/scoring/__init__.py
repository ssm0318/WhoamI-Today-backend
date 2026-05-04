"""Score formula registry for survey-level scale_score_histogram results.

Surveys with `score_formula` set on the Survey row dispatch to a registered
function here. Surveys without `score_formula` use the default sum-with-
reverse formula in `surveys.aggregation` (which honors `score_components`
and `reverse_scored`, and excludes likert_5_na N/A responses).

Registering a formula:

    from surveys.scoring.registry import register_formula

    @register_formula('rsq_brief_weighted')
    def rsq_brief_weighted(survey, response):
        '''Compute Σ over situations of (concern × (7 − expectation)).'''
        ...
        return total

The decorated function receives:
  - survey: the Survey instance
  - response: a SurveyResponse (use response.answers.all() to read values
    by question.slug; values follow SurveyAnswer.value semantics, with None
    sentinel for likert_5_na N/A picks)

It returns an int score.
"""
from surveys.scoring import formulas  # noqa: F401  — populates the registry on import
from surveys.scoring.registry import (
    get_formula,
    list_formulas,
    register_formula,
    score_response,
)


__all__ = [
    'get_formula',
    'list_formulas',
    'register_formula',
    'score_response',
]
