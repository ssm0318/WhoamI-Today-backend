from django.conf import settings
from django.db import models
from django.utils import timezone

from adoorback.models import AdoorTimestampedModel


class Survey(AdoorTimestampedModel):
    LIKERT_5 = 'likert_5'
    SINGLE_CHOICE = 'single_choice'
    MULTI_CHOICE = 'multi_choice'
    TYPE_CHOICES = (
        (LIKERT_5, 'Likert 5-point'),
        (SINGLE_CHOICE, 'Single choice'),
        (MULTI_CHOICE, 'Multi choice'),
    )

    slug = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    interpretation = models.TextField(
        blank=True,
        default='',
        help_text='Markdown shown after results unlock (e.g., "Higher scores indicate ...")',
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
    prompt = models.TextField()
    low_label = models.CharField(max_length=80, blank=True, default='')
    high_label = models.CharField(max_length=80, blank=True, default='')
    reverse_scored = models.BooleanField(default=False)

    class Meta:
        ordering = ['survey_id', 'order']
        constraints = [
            models.UniqueConstraint(fields=['survey', 'order'], name='unique_question_order_per_survey'),
        ]


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
    value = models.JSONField(help_text='Integer for likert/single, list of integers for multi.')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['response', 'question'], name='unique_answer_per_response_per_question'),
        ]
