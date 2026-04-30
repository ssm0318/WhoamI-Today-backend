from datetime import date

from django.db import IntegrityError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from surveys.aggregation import build_distribution, compute_user_percentile
from surveys.models import (
    DailySurvey, Survey, SurveyAnswer, SurveyQuestion, SurveyResponse,
)
from surveys.privacy import compute_bucket_eligibility
from surveys.serializers import (
    PastSurveySerializer, SurveyDetailSerializer, SurveyResponseInputSerializer,
)


def _bereal_gate(viewer, survey: Survey):
    """Return (visible, error_payload). error_payload is None if visible."""
    has_response = SurveyResponse.objects.filter(survey=survey, user=viewer).exists()
    if not has_response:
        return False, {
            'detail': 'Submit your response first to view results.',
            'needs_submission': True,
            'available_at': None,
        }
    survey_day = (
        DailySurvey.objects.filter(survey=survey).order_by('date').values_list('date', flat=True).first()
    )
    if survey_day is None:
        # never scheduled — treat as no day-elapsed gate
        return True, None
    if survey_day >= date.today():
        return False, {
            'detail': 'Results available tomorrow.',
            'needs_submission': False,
            'available_at': survey_day.isoformat(),
        }
    return True, None


class SurveyOfTheDayView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = date.today()
        ds = DailySurvey.objects.filter(date=today).select_related('survey').first()
        if ds is None:
            return Response({'survey': None})
        ser = SurveyDetailSerializer(ds.survey, context={'request': request})
        return Response({'date': today.isoformat(), 'survey': ser.data})


class SurveyDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        try:
            survey = Survey.objects.get(slug=slug)
        except Survey.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        ser = SurveyDetailSerializer(survey, context={'request': request})
        return Response(ser.data)


class SurveyResponseSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, slug):
        try:
            survey = Survey.objects.get(slug=slug)
        except Survey.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if SurveyResponse.objects.filter(survey=survey, user=request.user).exists():
            return Response(
                {'detail': 'Already submitted.'}, status=status.HTTP_409_CONFLICT
            )
        ser = SurveyResponseInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            response = SurveyResponse.objects.create(user=request.user, survey=survey)
            for a in ser.validated_data['answers']:
                question = SurveyQuestion.objects.get(id=a['question_id'], survey=survey)
                SurveyAnswer.objects.create(response=response, question=question, value=a['value'])
        except IntegrityError:
            return Response(
                {'detail': 'Already submitted.'}, status=status.HTTP_409_CONFLICT
            )
        return Response({'id': response.id}, status=status.HTTP_201_CREATED)


class SurveyResultsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        try:
            survey = Survey.objects.get(slug=slug)
        except Survey.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        visible, err = _bereal_gate(request.user, survey)
        if not visible:
            return Response(err, status=status.HTTP_403_FORBIDDEN)
        report = compute_bucket_eligibility(request.user, survey)
        viewer_response = SurveyResponse.objects.filter(survey=survey, user=request.user).first()
        out = {
            'user_response': {'id': viewer_response.id if viewer_response else None},
            'population_required_n': report['population']['required_n'],
            'friends_required_n': report['friends']['required_n'],
            'close_friends_required_n': report['close_friends']['required_n'],
            'population_available': report['population']['available'],
            'friends_available': report['friends']['available'],
            'close_friends_available': report['close_friends']['available'],
            'population_suppressed_reason': report['population']['suppressed_reason'],
            'friends_suppressed_reason': report['friends']['suppressed_reason'],
            'close_friends_suppressed_reason': report['close_friends']['suppressed_reason'],
            'population': None,
            'friends': None,
            'close_friends': None,
        }
        if report['population']['available']:
            dist = build_distribution(survey, report['_population_ids'], request.user.id)
            out['population'] = {
                'n': len(report['_population_ids']),
                'distribution': dist,
                'user_percentile': compute_user_percentile(dist, dist.get('user_score')),
            }
        if report['friends']['available']:
            dist = build_distribution(survey, report['_friend_ids'], request.user.id)
            out['friends'] = {
                'n': len(report['_friend_ids']),
                'distribution': dist,
                'user_percentile': compute_user_percentile(dist, dist.get('user_score')),
            }
        if report['close_friends']['available']:
            dist = build_distribution(survey, report['_close_friend_ids'], request.user.id)
            out['close_friends'] = {
                'n': len(report['_close_friend_ids']),
                'distribution': dist,
                'user_percentile': compute_user_percentile(dist, dist.get('user_score')),
            }
        return Response(out)


class PastSurveysView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = DailySurvey.objects.select_related('survey').order_by('-date')
        ser = PastSurveySerializer(qs, many=True, context={'request': request})
        return Response({'results': ser.data})
