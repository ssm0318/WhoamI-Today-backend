from datetime import date

from rest_framework import serializers

from surveys.models import (
    DailySurvey, Survey, SurveyOption, SurveyQuestion, SurveyResponse,
)


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
            'options',
        ]


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
    survey = SurveyDetailSerializer(read_only=True)
    user_answered = serializers.SerializerMethodField()
    results_unlocked = serializers.SerializerMethodField()

    class Meta:
        model = DailySurvey
        fields = ['date', 'survey', 'user_answered', 'results_unlocked']

    def get_user_answered(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return SurveyResponse.objects.filter(survey=obj.survey, user=request.user).exists()

    def get_results_unlocked(self, obj):
        if not self.get_user_answered(obj):
            return False
        return obj.date < date.today()
