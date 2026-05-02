from rest_framework import serializers

from surveys.models import (
    SLIDER, ScheduledSurvey, Survey, SurveyOption, SurveyQuestion, SurveyResponse,
)
from surveys.scheduling import _today_la_7am


def validate_answer_value(question: SurveyQuestion, value) -> None:
    """Per-question-type validation for an inbound SurveyAnswer value.

    Raises ``serializers.ValidationError`` on rejection — DRF surfaces it as
    a 400. Currently only slider ranges are checked; other types accept the
    JSONField shape as-is (matches existing behavior).
    """
    if question.type == SLIDER:
        # Reject bool first (bool is an int subclass in Python).
        if isinstance(value, bool) or not isinstance(value, int):
            raise serializers.ValidationError({
                'answers': [f'slider answer must be an integer (got {type(value).__name__})'],
            })
        if value < question.slider_min_value or value > question.slider_max_value:
            raise serializers.ValidationError({
                'answers': [
                    f'slider value {value} out of range '
                    f'[{question.slider_min_value}, {question.slider_max_value}]'
                ],
            })


class SurveyOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyOption
        fields = ['id', 'order', 'label_en', 'label_ko', 'value']


class SurveyQuestionSerializer(serializers.ModelSerializer):
    options = SurveyOptionSerializer(many=True, read_only=True)

    class Meta:
        model = SurveyQuestion
        fields = [
            'id', 'order', 'type',
            'prompt_en', 'prompt_ko',
            'low_label_en', 'low_label_ko',
            'high_label_en', 'high_label_ko',
            'reverse_scored',
            'slider_min_value', 'slider_max_value',
            'options',
        ]


class SurveyMinimalSerializer(serializers.ModelSerializer):
    """Lightweight Survey shape for the bucketed index (no questions)."""
    class Meta:
        model = Survey
        fields = ['slug', 'title_en', 'title_ko']


class SurveyDetailSerializer(serializers.ModelSerializer):
    questions = SurveyQuestionSerializer(many=True, read_only=True)
    user_has_responded = serializers.SerializerMethodField()
    responder_count = serializers.SerializerMethodField()

    class Meta:
        model = Survey
        fields = [
            'slug',
            'title_en', 'title_ko',
            'description_en', 'description_ko',
            'interpretation_en', 'interpretation_ko',
            'questions',
            'user_has_responded',
            'responder_count',
        ]

    def get_user_has_responded(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return SurveyResponse.objects.filter(survey=obj, user=request.user).exists()

    def get_responder_count(self, obj):
        # Total non-system responders for this survey. For today's surveys this is
        # effectively today's count since past surveys would already have unlocked
        # results and shouldn't appear on the Share tab.
        from chat.wit_admin import ALL_OPERATOR_EMAILS, WIT_ADMIN_USERNAME
        from chat.wit_bot import WIT_BOT_USERNAME
        return (
            SurveyResponse.objects
            .filter(survey=obj)
            .exclude(user__username__in=[WIT_BOT_USERNAME, WIT_ADMIN_USERNAME])
            .exclude(user__email__in=ALL_OPERATOR_EMAILS)
            .count()
        )


class SurveyAnswerInputSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    value = serializers.JSONField()


class SurveyResponseInputSerializer(serializers.Serializer):
    answers = SurveyAnswerInputSerializer(many=True)


class PastSurveySerializer(serializers.ModelSerializer):
    """Daily-archive serializer. Wraps a daily ScheduledSurvey row in the same
    {date, survey, user_answered, results_unlocked} shape that DailySurvey rows
    used to produce, so the existing daily-archive frontend doesn't change.
    """
    date = serializers.DateField(source='window_start', read_only=True)
    survey = SurveyDetailSerializer(read_only=True)
    user_answered = serializers.SerializerMethodField()
    results_unlocked = serializers.SerializerMethodField()

    class Meta:
        model = ScheduledSurvey
        fields = ['date', 'survey', 'user_answered', 'results_unlocked']

    def get_user_answered(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return SurveyResponse.objects.filter(survey=obj.survey, user=request.user).exists()

    def get_results_unlocked(self, obj):
        if not self.get_user_answered(obj):
            return False
        return obj.window_start < _today_la_7am()


class SurveyIndexEntrySerializer(serializers.ModelSerializer):
    """One ScheduledSurvey row in the bucketed `/api/surveys/index/` payload.

    The view annotates `bucket` ('available_now' | 'late_but_accepted' |
    'completed') on each instance before serializing. `submitted_at` comes
    from the queryset annotation `user_submitted_at` (see scheduling.py).
    """
    survey = SurveyMinimalSerializer(read_only=True)
    bucket = serializers.CharField(read_only=True)
    user_answered = serializers.BooleanField(read_only=True)
    submitted_at = serializers.DateTimeField(
        source='user_submitted_at', allow_null=True, read_only=True,
    )
    redirect_url = serializers.SerializerMethodField()

    class Meta:
        model = ScheduledSurvey
        fields = [
            'id', 'cadence', 'sequence_index',
            'window_start', 'window_end',
            'survey', 'bucket',
            'user_answered', 'submitted_at',
            'redirect_url',
        ]

    def get_redirect_url(self, obj):
        if getattr(obj, 'bucket', None) == 'completed':
            return f'/surveys/{obj.survey.slug}/results'
        return f'/surveys/{obj.survey.slug}/answer'
