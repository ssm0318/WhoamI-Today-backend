from datetime import date

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from surveys.aggregation import (
    build_panel_distribution,
    compute_user_percentile,
    group_panels,
)
from surveys.models import (
    DailySurvey, Survey, SurveyAnswer, SurveyQuestion, SurveyResponse,
)
from surveys.privacy import compute_panel_eligibility, compute_responder_ids
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
            with transaction.atomic():
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
        if survey.results_hidden:
            # Treat hidden surveys as if they have no results page at all.
            return Response(status=status.HTTP_404_NOT_FOUND)
        visible, err = _bereal_gate(request.user, survey)
        if not visible:
            return Response(err, status=status.HTTP_403_FORBIDDEN)

        ids = compute_responder_ids(request.user, survey)
        viewer_response = SurveyResponse.objects.filter(survey=survey, user=request.user).first()

        panels_payload = []
        for group_key, questions in group_panels(survey):
            panel_kind = questions[0].effective_result_kind
            eligibility = compute_panel_eligibility(request.user, survey, panel_kind, ids)

            payload = {
                'group_key': group_key,
                'kind': panel_kind,
                'title_en': questions[0].prompt_en if len(questions) == 1 else '',
                'title_ko': questions[0].prompt_ko if len(questions) == 1 else '',
                'question_count': len(questions),
                'population_available': eligibility['population']['available'],
                'friends_available': eligibility['friends']['available'],
                'close_friends_available': eligibility['close_friends']['available'],
                'population_suppressed_reason': eligibility['population']['suppressed_reason'],
                'friends_suppressed_reason': eligibility['friends']['suppressed_reason'],
                'close_friends_suppressed_reason': eligibility['close_friends']['suppressed_reason'],
                'population_required_n': eligibility['population']['required_n'],
                'friends_required_n': eligibility['friends']['required_n'],
                'close_friends_required_n': eligibility['close_friends']['required_n'],
                'population': None,
                'friends': None,
                'close_friends': None,
            }

            if eligibility['population']['available']:
                dist = build_panel_distribution(survey, questions, ids['population'], request.user.id)
                payload['population'] = {
                    'n': len(ids['population']),
                    'distribution': dist,
                    'user_percentile': compute_user_percentile(dist, dist.get('user_score')),
                }
            if eligibility['friends']['available']:
                dist = build_panel_distribution(survey, questions, ids['friend'], request.user.id)
                payload['friends'] = {
                    'n': len(ids['friend']),
                    'distribution': dist,
                    'user_percentile': compute_user_percentile(dist, dist.get('user_score')),
                }
            if eligibility['close_friends']['available']:
                dist = build_panel_distribution(survey, questions, ids['close_friend'], request.user.id)
                payload['close_friends'] = {
                    'n': len(ids['close_friend']),
                    'distribution': dist,
                    'user_percentile': compute_user_percentile(dist, dist.get('user_score')),
                }
            panels_payload.append(payload)

        return Response({
            'user_response': {'id': viewer_response.id if viewer_response else None},
            'panels': panels_payload,
        })


class PastSurveysView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = DailySurvey.objects.select_related('survey').filter(survey__results_hidden=False).order_by('-date')
        ser = PastSurveySerializer(qs, many=True, context={'request': request})
        return Response({'results': ser.data})
