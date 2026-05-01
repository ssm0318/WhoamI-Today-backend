from django.conf import settings
from django.db import models
from django.utils import timezone

from adoorback.models import AdoorTimestampedModel


# Question types — defined at the question level so a single Survey can mix them
# (e.g. 19 likert items + 1 free-text reflection). Adding a new type:
#   1. Add a constant + entry to TYPE_CHOICES below.
#   2. Add the input dispatcher case in surveys/serializers.py and the frontend's
#      SurveyAnswerForm.
#   3. Add the default result kind mapping below.
LIKERT_5 = 'likert_5'
SINGLE_CHOICE = 'single_choice'
MULTI_CHOICE = 'multi_choice'
FREE_TEXT = 'free_text'
TYPE_CHOICES = (
    (LIKERT_5, 'Likert 5-point'),
    (SINGLE_CHOICE, 'Single choice'),
    (MULTI_CHOICE, 'Multi choice'),
    (FREE_TEXT, 'Free text'),
)

# Result rendering kinds — the registry key shared between the backend aggregation
# strategy and the frontend renderer. Adding a new kind: see surveys/aggregation.py
# (backend strategy) and src/components/survey/results/registry.ts (frontend).
RESULT_AGGREGATED_LIKERT = 'aggregated_likert'
RESULT_OPTION_COUNTS = 'option_counts'
RESULT_WORDCLOUD = 'wordcloud'
RESULT_KIND_CHOICES = (
    (RESULT_AGGREGATED_LIKERT, 'Aggregated likert score'),
    (RESULT_OPTION_COUNTS, 'Per-option counts'),
    (RESULT_WORDCLOUD, 'Wordcloud (free-text tokens)'),
)

# Default result kind per question type. A panel can override with
# SurveyQuestion.result_kind, but most surveys won't need to.
DEFAULT_RESULT_KIND_FOR_TYPE = {
    LIKERT_5: RESULT_AGGREGATED_LIKERT,
    SINGLE_CHOICE: RESULT_OPTION_COUNTS,
    MULTI_CHOICE: RESULT_OPTION_COUNTS,
    FREE_TEXT: RESULT_WORDCLOUD,
}

# Result kinds for which friend / close-friend buckets are suppressed by default
# (token-level k-anonymity isn't enough protection in small friend pools).
PRIVACY_FRIEND_DISABLED_KINDS = frozenset({RESULT_WORDCLOUD})


class Survey(AdoorTimestampedModel):
    slug = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    interpretation = models.TextField(
        blank=True,
        default='',
        help_text='Markdown shown after results unlock (e.g., "Higher scores indicate ...")',
    )
    friend_visible = models.BooleanField(
        default=True,
        help_text=(
            'Survey-level kill switch for friend / close-friend buckets across all panels. '
            'Individual panels may still be suppressed when their kind is wordcloud-style.'
        ),
    )
    results_hidden = models.BooleanField(
        default=False,
        help_text='If True, this survey accepts responses but the results endpoint always 404s.',
    )
    last_used_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text='Date this Survey was last scheduled by RotateDailySurveyCronJob.',
    )

    class Meta:
        ordering = ['slug']

    def __str__(self):
        return f'Survey<{self.slug}>'


class SurveyQuestion(AdoorTimestampedModel):
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='questions')
    order = models.PositiveSmallIntegerField()
    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=LIKERT_5,
        help_text='Input type. Determines which input UI is rendered and how value is validated.',
    )
    prompt = models.TextField()
    low_label = models.CharField(max_length=80, blank=True, default='')
    high_label = models.CharField(max_length=80, blank=True, default='')
    reverse_scored = models.BooleanField(default=False)
    result_kind = models.CharField(
        max_length=32,
        choices=RESULT_KIND_CHOICES,
        blank=True,
        default='',
        help_text='Override the default renderer for this question. Blank → derived from `type`.',
    )
    result_group = models.CharField(
        max_length=64,
        blank=True,
        default='',
        help_text=(
            'Group key — questions sharing a non-empty group are aggregated into a single panel. '
            'Blank → grouped implicitly with sibling questions of the same type.'
        ),
    )
    result_hidden = models.BooleanField(
        default=False,
        help_text='If True, this question is answered but never appears on the results page.',
    )

    class Meta:
        ordering = ['survey_id', 'order']
        constraints = [
            models.UniqueConstraint(fields=['survey', 'order'], name='unique_question_order_per_survey'),
        ]

    @property
    def effective_result_kind(self) -> str:
        return self.result_kind or DEFAULT_RESULT_KIND_FOR_TYPE.get(self.type, RESULT_OPTION_COUNTS)

    @property
    def effective_group_key(self) -> str:
        """Implicit group when no explicit `result_group` set: one group per (kind, type)."""
        return self.result_group or f'__auto__:{self.effective_result_kind}'


class SurveyOption(AdoorTimestampedModel):
    question = models.ForeignKey(SurveyQuestion, on_delete=models.CASCADE, related_name='options')
    order = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=160)
    value = models.IntegerField(help_text='Numeric value used for scoring (likert) or option id (choice).')

    class Meta:
        ordering = ['question_id', 'order']
        constraints = [
            models.UniqueConstraint(fields=['question', 'order'], name='unique_option_order_per_question'),
        ]


class DailySurvey(AdoorTimestampedModel):
    date = models.DateField(unique=True)
    survey = models.ForeignKey(Survey, on_delete=models.PROTECT, related_name='scheduled_days')

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f'DailySurvey<{self.date}:{self.survey.slug}>'


class SurveyResponse(AdoorTimestampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='survey_responses')
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='responses')
    submitted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'survey'], name='unique_response_per_user_per_survey'),
        ]
        indexes = [
            models.Index(fields=['survey', 'user']),
        ]


class SurveyAnswer(AdoorTimestampedModel):
    response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(SurveyQuestion, on_delete=models.PROTECT, related_name='answers')
    value = models.JSONField(
        help_text=(
            'Shape depends on question.type: int for likert/single, list[int] for multi, '
            'str for free_text.'
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['response', 'question'], name='unique_answer_per_response_per_question'),
        ]
