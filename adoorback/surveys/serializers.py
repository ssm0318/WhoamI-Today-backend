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

    class Meta:
        model = Survey
        fields = [
            'slug',
            'title_en', 'title_ko',
            'description_en', 'description_ko',
            'interpretation_en', 'interpretation_ko',
            'questions',
            'user_has_responded',
        ]

    def get_user_has_responded(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return SurveyResponse.objects.filter(survey=obj, user=request.user).exists()


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
