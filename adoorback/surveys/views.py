from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from surveys.aggregation import (
    build_panel_distribution,
    compute_user_percentile,
    group_panels,
    group_panels_for_survey_level_kind,
)
from surveys.models import (
    CADENCE_DAILY, INPUT_LESS_TYPES, ScheduledSurvey, Survey, SurveyAnswer,
    SurveyQuestion, SurveyResponse, UserSurveyEmbeddedData,
)
from surveys.privacy import compute_panel_eligibility, compute_responder_ids
from surveys.scheduling import (
    _today_la_7am, get_survey_index, get_today_daily,
    get_today_daily_with_prereq, routes_to_user,
)
from surveys.serializers import (
    PastSurveySerializer, SurveyDetailSerializer, SurveyIndexEntrySerializer,
    SurveyResponseInputSerializer, validate_answer_value,
)


def _persist_embedded_data(user, response: SurveyResponse) -> None:
    """Copy answers from `embedded_data: true` questions into the per-user
    store, keyed by the question's slug.

    Called inside the submit view's transaction. update_or_create lets a
    repeatable survey's later submission overwrite an earlier one's value
    for the same key — the most-recent answer wins, matching how research
    instruments treat resubmits.

    For `habit_platform` specifically, an additional resolver writes the
    human-readable label as `<slug>_label` so subsequent surveys can render
    it via tokens. Other slugs persist their raw value only — explicit
    label-translation is opt-in per slug here.
    """
    flagged_answers = response.answers.filter(question__embedded_data=True).select_related('question')
    for ans in flagged_answers:
        slug = ans.question.slug
        if not slug:
            continue
        UserSurveyEmbeddedData.objects.update_or_create(
            user=user, key=slug,
            defaults={'value': ans.value, 'source_question': ans.question},
        )
        # habit_platform → habit_platform_label resolution (option's label).
        if slug == 'habit_platform' and isinstance(ans.value, (str, int)):
            label = _resolve_habit_platform_label(ans.question, ans.value)
            if label is not None:
                UserSurveyEmbeddedData.objects.update_or_create(
                    user=user, key='habit_platform_label',
                    defaults={'value': label, 'source_question': ans.question},
                )


def _resolve_habit_platform_label(question: SurveyQuestion, value):
    """Look up the matching SurveyOption's label_en for `value` and return it.

    Returns None when no option matches (e.g. user picked the "other" branch
    that surfaces `habit_platform_other` as its own free-text question).
    """
    opt = question.options.filter(value=value).first()
    return opt.label_en if opt else None


def _bereal_gate(viewer, survey: Survey):
    """Return (visible, error_payload). error_payload is None if visible.

    Daily surveys keep the BeReal-style lock: results unlock only after the
    daily window closes. Non-daily surveys (weekly, biweekly, anytime,
    endpoint) have no daily ScheduledSurvey row, so this gate is a no-op for
    them — results are visible as soon as the user submits.
    """
    has_response = SurveyResponse.objects.filter(survey=survey, user=viewer).exists()
    if not has_response:
        return False, {
            'detail': 'Submit your response first to view results.',
            'needs_submission': True,
            'available_at': None,
        }
    survey_day = (
        ScheduledSurvey.objects
        .filter(survey=survey, cadence=CADENCE_DAILY)
        .order_by('window_start')
        .values_list('window_start', flat=True)
        .first()
    )
    if survey_day is None:
        return True, None
    if survey_day >= _today_la_7am():
        return False, {
            'detail': 'Results available tomorrow.',
            'needs_submission': False,
            'available_at': survey_day.isoformat(),
        }
    return True, None


class SurveyOfTheDayView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Use the prereq-aware resolver: if today's scheduled survey
        # references `{{token}}` keys the user hasn't populated, this
        # returns the upstream survey that would populate them (so the
        # user does the prereq first instead of seeing literal tokens).
        # Returns None when nothing is scheduled OR when missing tokens
        # have no findable source.
        today = get_today_daily_with_prereq(request.user)
        if today is None:
            return Response({'survey': None})
        ser = SurveyDetailSerializer(today.survey, context={'request': request})
        payload = {'survey': ser.data}
        if today.date is not None:
            payload['date'] = today.date.isoformat()
        if today.is_prereq_redirect:
            # Frontend can use this flag to badge the card ("Before today's
            # survey: …") or just ignore it. Today the SOTD card doesn't
            # surface it, but exposing it now means we don't need a second
            # round-trip if/when the UX wants to differentiate.
            payload['is_prereq_redirect'] = True
        return Response(payload)


class SurveyDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        try:
            survey = Survey.objects.get(slug=slug)
        except Survey.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        # Route version-suffixed slugs by user_group — direct URL access to
        # the wrong variant returns 404 so the schema mirror's "this slug
        # exists" doesn't leak through. Same predicate as the index queries.
        if not routes_to_user(survey, request.user):
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
        # Same routing check as SurveyDetailView — block submissions to the
        # wrong variant so research data stays cleanly partitioned.
        if not routes_to_user(survey, request.user):
            return Response(status=status.HTTP_404_NOT_FOUND)
        # Researcher-set close flag — survey accepts no new / updated answers.
        # Existing responses are preserved; this just rejects further submits.
        if survey.closed:
            return Response(
                {'detail': 'This survey has been closed by researchers.'},
                status=status.HTTP_410_GONE,
            )
        # Submit semantics depend on Survey.repeatable + Survey.editable:
        #   - repeatable=True: each submit creates a new SurveyResponse row.
        #   - editable=True (and not repeatable): one row per user, but the
        #     answers are REPLACED on resubmit — caller is editing.
        #   - default (neither): single submit, 409 on resubmit.
        existing = SurveyResponse.objects.filter(survey=survey, user=request.user).first()
        is_edit = bool(existing and survey.editable and not survey.repeatable)
        if existing and not survey.repeatable and not survey.editable:
            return Response(
                {'detail': 'Already submitted.'}, status=status.HTTP_409_CONFLICT
            )
        # Reject submissions only when there is NO currently-valid window
        # for this survey. Mirrors the bucketing logic in
        # `get_survey_index`: a survey is answerable if it has at least
        # one ScheduledSurvey row that is either (a) currently open
        # [window_start <= today AND (window_end IS NULL OR
        # window_end >= today)] or (b) past its window but flagged
        # allow_late=True.
        #
        # The previous check fired 410 if ANY past row had
        # allow_late=False, regardless of whether the survey ALSO had a
        # currently-open row. That broke `daily_base` (28 ScheduledSurvey
        # rows, allow_late=False on each, so every day after May 4 had
        # at least one past expired row) and any other survey scheduled
        # across multiple discrete daily windows. Manifested first on
        # May 9 (Saturday), when weekend SOTD skip made daily_base the
        # featured Survey-of-the-Day card.
        today = _today_la_7am()
        scheduled_for_survey = ScheduledSurvey.objects.filter(survey=survey)
        if scheduled_for_survey.exists():
            currently_open = Q(window_start__lte=today) & (
                Q(window_end__isnull=True) | Q(window_end__gte=today)
            )
            late_accepted = Q(window_end__lt=today, allow_late=True)
            has_valid_window = scheduled_for_survey.filter(
                currently_open | late_accepted,
            ).exists()
            if not has_valid_window:
                # Disambiguate "expired" vs "not yet open" so the
                # frontend / dev tools see a helpful error.
                future_only = scheduled_for_survey.filter(
                    window_start__gt=today,
                ).exists()
                if future_only:
                    return Response(
                        {'detail': 'This survey is not yet open for responses.'},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                return Response(
                    {'detail': 'This survey has expired and can no longer be answered.'},
                    status=status.HTTP_410_GONE,
                )
        ser = SurveyResponseInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                if is_edit:
                    # Edit mode: keep the SurveyResponse row but wipe + replace
                    # answers. Bumping submitted_at so analyses can see the
                    # most recent edit time.
                    response = existing
                    response.submitted_at = timezone.now()
                    response.save(update_fields=['submitted_at'])
                    response.answers.all().delete()
                else:
                    response = SurveyResponse.objects.create(user=request.user, survey=survey)
                for a in ser.validated_data['answers']:
                    question = SurveyQuestion.objects.get(id=a['question_id'], survey=survey)
                    # display_only blocks accept no value — defensively skip
                    # if the frontend sends one.
                    if question.type in INPUT_LESS_TYPES:
                        continue
                    validate_answer_value(question, a['value'])
                    SurveyAnswer.objects.create(response=response, question=question, value=a['value'])
                # Persist `embedded_data: true` answers into the per-user
                # store keyed by question.slug. Subsequent surveys read these
                # via `{{slug}}` tokens or `serving_condition`.
                _persist_embedded_data(request.user, response)
        except IntegrityError:
            return Response(
                {'detail': 'Already submitted.'}, status=status.HTTP_409_CONFLICT
            )
        return Response({'id': response.id}, status=status.HTTP_201_CREATED)


class MyResponseView(APIView):
    """Return the requesting user's existing answers for this survey, or 404
    if they haven't submitted yet.

    Used by the frontend to pre-fill the form when editing an `editable`
    survey. Shape: `{ id, submitted_at, answers: [{ question_id, value }, ...] }`.
    Routing-blocked surveys return 404 (same as SurveyDetailView).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        try:
            survey = Survey.objects.get(slug=slug)
        except Survey.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not routes_to_user(survey, request.user):
            return Response(status=status.HTTP_404_NOT_FOUND)
        response = SurveyResponse.objects.filter(
            survey=survey, user=request.user,
        ).prefetch_related('answers').order_by('-submitted_at').first()
        if response is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response({
            'id': response.id,
            'submitted_at': response.submitted_at.isoformat(),
            'answers': [
                {'question_id': a.question_id, 'value': a.value}
                for a in response.answers.all()
            ],
        })


class SurveyResultsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        try:
            survey = Survey.objects.get(slug=slug)
        except Survey.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        # Hide off-route variants so a w-first user can't peek at q results.
        if not routes_to_user(survey, request.user):
            return Response(status=status.HTTP_404_NOT_FOUND)
        if survey.results_hidden:
            # Treat hidden surveys as if they have no results page at all.
            return Response(status=status.HTTP_404_NOT_FOUND)
        visible, err = _bereal_gate(request.user, survey)
        if not visible:
            return Response(err, status=status.HTTP_403_FORBIDDEN)

        ids = compute_responder_ids(request.user, survey)
        viewer_response = SurveyResponse.objects.filter(survey=survey, user=request.user).first()

        # Survey-level result_kind (scale_score_histogram /
        # slider_histogram_paired) overrides per-question grouping. Each
        # variant returns its own panel layout, but every panel shares the
        # render path below — only the question grouping differs.
        if survey.result_kind:
            panels = group_panels_for_survey_level_kind(survey)
            forced_kind = survey.result_kind
        else:
            panels = group_panels(survey)
            forced_kind = None

        panels_payload = []
        for group_key, questions in panels:
            panel_kind = forced_kind or questions[0].effective_result_kind
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
    """Daily-only archive of past dailies.

    Includes:
      - rows the user has answered (any allow_late) → results page
      - unanswered rows with allow_late=True → still submittable from the
        archive's "Answer to view results" chip

    Excludes unanswered rows with allow_late=False (real-study missed dailies):
    they can no longer be submitted and have no results to view, matching the
    "expired hidden" semantics in the bucketed index.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = _today_la_7am()
        answered_survey_ids = list(
            SurveyResponse.objects.filter(user=request.user).values_list('survey_id', flat=True)
        )
        qs = (
            ScheduledSurvey.objects
            .filter(
                cadence=CADENCE_DAILY,
                survey__results_hidden=False,
                window_start__lte=today,
            )
            .filter(Q(survey_id__in=answered_survey_ids) | Q(allow_late=True))
            .select_related('survey')
            .order_by('-window_start')
        )
        ser = PastSurveySerializer(qs, many=True, context={'request': request})
        return Response({'results': ser.data})


class SurveyIndexView(APIView):
    """Three-bucket survey index for the /surveys page.

    GET /api/surveys/index/ →
        {
          "available_now":     [SurveyIndexEntry, ...],
          "late_but_accepted": [SurveyIndexEntry, ...],
          "completed":         [SurveyIndexEntry, ...]
        }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        result = get_survey_index(request.user)
        for bucket_name in ('available_now', 'late_but_accepted', 'completed'):
            for entry in result[bucket_name]:
                entry.bucket = bucket_name
        return Response({
            'available_now': SurveyIndexEntrySerializer(
                result['available_now'], many=True, context={'request': request},
            ).data,
            'late_but_accepted': SurveyIndexEntrySerializer(
                result['late_but_accepted'], many=True, context={'request': request},
            ).data,
            'completed': SurveyIndexEntrySerializer(
                result['completed'], many=True, context={'request': request},
            ).data,
        })
