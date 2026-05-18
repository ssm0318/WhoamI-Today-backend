from rest_framework import serializers

from surveys.models import (
    DISPLAY_ONLY, INPUT_LESS_TYPES, LIKERT_5_NA, LIKERT_RANGES, NA_SENTINEL,
    SLIDER, ScheduledSurvey, Survey, SurveyOption, SurveyQuestion, SurveyResponse,
)
from surveys.scheduling import _today_la_7am


def validate_answer_value(question: SurveyQuestion, value) -> None:
    """Per-question-type validation for an inbound SurveyAnswer value.

    Raises ``serializers.ValidationError`` on rejection — DRF surfaces it as
    a 400. Slider range, likert variant range, and the likert_5_na N/A
    sentinel are checked; other types accept the JSONField shape as-is.
    """
    # likert_5_na N/A pick: explicit None is the canonical "did pick N/A"
    # value — accepted unconditionally. (Other likert variants don't have
    # an N/A option; None there means "didn't answer" and should be
    # filtered before submit.)
    if question.type == LIKERT_5_NA and value is NA_SENTINEL:
        return

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

    if question.type in LIKERT_RANGES:
        if isinstance(value, bool) or not isinstance(value, int):
            raise serializers.ValidationError({
                'answers': [
                    f'likert answer for {question.type} must be an integer '
                    f'(got {type(value).__name__})'
                ],
            })
        lo, hi = LIKERT_RANGES[question.type]
        if value < lo or value > hi:
            raise serializers.ValidationError({
                'answers': [
                    f'likert value {value} out of range [{lo}, {hi}] for {question.type}'
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
            'slug',
            'prompt_en', 'prompt_ko',
            'description_en', 'description_ko',
            'placeholder_en', 'placeholder_ko',
            'low_label_en', 'low_label_ko',
            'high_label_en', 'high_label_ko',
            'na_option_en', 'na_option_ko',
            'content_en', 'content_ko',
            'min_length',
            'min_length_warning_en', 'min_length_warning_ko',
            'required',
            'reverse_scored',
            'conditional_display',
            'slider_min_value', 'slider_max_value',
            'options',
        ]

    def to_representation(self, instance):
        # Token substitution runs server-side so the frontend doesn't need a
        # template engine. Tokens come from the parent SurveyDetailSerializer's
        # context (`survey_tokens` key) — see `to_representation` there for
        # how the map is built once per Survey, not per question.
        data = super().to_representation(instance)
        tokens = self.context.get('survey_tokens')
        if tokens:
            from surveys.tokens import apply_to_question_dict
            apply_to_question_dict(data, tokens)
        return data


class SurveyMinimalSerializer(serializers.ModelSerializer):
    """Lightweight Survey shape for the bucketed index (no questions).

    Surfaces `priority`, `editable`, and `closed` so the frontend index page
    can sort + render badges (e.g. "Open until closed", "Edit response")
    without a second round-trip per row.
    """
    class Meta:
        model = Survey
        fields = ['slug', 'title_en', 'title_ko', 'priority', 'editable', 'closed']

    def to_representation(self, instance):
        # Even the minimal index payload needs token substitution on the
        # title — otherwise `{{habit_platform_label}}`-style references in
        # survey titles leak through to the /surveys index card. Build a
        # fresh token map per survey row; the overhead is one UserSurvey-
        # EmbeddedData query per row, which is acceptable for the index.
        from surveys.tokens import apply_to_survey_dict, build_token_map

        data = super().to_representation(instance)
        request = self.context.get('request')
        viewer = getattr(request, 'user', None) if request else None
        tokens = build_token_map(instance, viewer=viewer)
        if tokens:
            apply_to_survey_dict(data, tokens)
        return data


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
            # Long-form study extensions:
            'tokens',
            'repeatable',
            'editable',
            'closed',
            'priority',
            'result_kind',
            'questions',
            'user_has_responded',
            'responder_count',
        ]

    def to_representation(self, instance):
        # Build the tokens map once per Survey and pass it down via context
        # so each question doesn't re-query UserSurveyEmbeddedData. Also
        # apply substitution to the survey-level text fields (title,
        # description, interpretation) — previously only question-level
        # fields ran through token substitution, so a title with
        # `{{habit_platform_label}}` would render as the literal token on
        # the survey-of-the-day card and daily archive.
        from surveys.tokens import apply_to_survey_dict, build_token_map

        request = self.context.get('request')
        viewer = getattr(request, 'user', None) if request else None
        tokens = build_token_map(instance, viewer=viewer)
        # Cloning the context preserves request/view for the nested serializer
        # while letting us add `survey_tokens` without mutating the parent.
        self.context['survey_tokens'] = tokens
        data = super().to_representation(instance)
        if tokens:
            apply_to_survey_dict(data, tokens)
        return data

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
    # `allow_null=True` so likert_5_na N/A picks (NA_SENTINEL) submit
    # cleanly. JSONField rejects None by default.
    value = serializers.JSONField(allow_null=True)


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
