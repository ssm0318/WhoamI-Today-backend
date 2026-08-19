import hashlib
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from adoorback.utils.alerts import send_user_event_to_slack
from surveys.aggregation import (
    build_panel_distribution,
    compute_user_percentile,
    group_panels,
    group_panels_for_survey_level_kind,
)
from surveys.models import (
    CADENCE_DAILY, INPUT_LESS_TYPES, PER_FRIEND_TYPES, ScheduledSurvey, Survey,
    DropoutSurveyDraft, DropoutSurveyResponse, PointAward, SurveyAnswer, SurveyDraft,
    SurveyQuestion, SurveyResponse, UserSurveyEmbeddedData,
)
from surveys.privacy import compute_panel_eligibility, compute_responder_ids
from surveys.points import (
    create_survey_point_award, credit_dropout_survey_award, reimbursement_state_for_user,
    resolve_submit_scheduled_survey, serialize_point_award,
    wit_bot_audit_version_for_group,
)
from surveys.scheduling import (
    _today_la_7am, get_survey_index, get_today_daily,
    get_today_daily_with_prereq, routes_to_user,
)
from surveys.retired import is_retired_survey_slug
from surveys.recovery import missing_recovery_question_ids_for_user
from surveys.serializers import (
    PastSurveySerializer, SurveyDetailSerializer, SurveyDraftSerializer,
    SurveyIndexEntrySerializer, SurveyResponseInputSerializer, validate_answer_value,
)
DAILY_ARCHIVE_SURVEY_SLUG = 'daily_base'
LA_TZ = ZoneInfo('America/Los_Angeles')
DROP_OUT_PARTICIPANT_ID_MIN = 8
DROP_OUT_PARTICIPANT_ID_MAX = 87
DROP_OUT_PARTICIPANT_REPLACED_ID = 64
DROP_OUT_PARTICIPANT_REPLACEMENT_ID = 114
DROPOUT_LOOKUP_TOKEN_SALT = 'surveys.dropout.lookup'
DROPOUT_LOOKUP_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 6
DROPOUT_PHASES = {
    'phase1': {'label': 'Phase 1', 'date_range': 'May 4-May 17'},
    'phase2': {'label': 'Phase 2', 'date_range': 'May 18-May 31'},
}
DROPOUT_VERSION_LABELS = {
    'version_w': 'Ver.W',
    'version_q': 'Ver.Q',
    '': '',
}


def _dropout_participant_queryset():
    User = get_user_model()
    return (
        User.objects
        .filter(is_superuser=False)
        .filter(
            Q(id__gte=DROP_OUT_PARTICIPANT_ID_MIN, id__lte=DROP_OUT_PARTICIPANT_ID_MAX)
            | Q(id=DROP_OUT_PARTICIPANT_REPLACEMENT_ID)
        )
        .exclude(id=DROP_OUT_PARTICIPANT_REPLACED_ID)
    )


def _normalize_dropout_identifier(identifier) -> str:
    return str(identifier or '').strip()


def _dropout_identifier_hash(identifier: str) -> str:
    normalized = _normalize_dropout_identifier(identifier).casefold()
    if not normalized:
        return ''
    raw = f'{settings.SECRET_KEY}:dropout-survey:{normalized}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _dropout_decode_lookup_token(lookup_token):
    """Decode a signed dropout lookup token. Returns the payload dict, or None
    if the token is missing, tampered with, or older than the max age
    (SignatureExpired subclasses BadSignature, so both are covered)."""
    if not lookup_token:
        return None
    try:
        return signing.loads(
            lookup_token,
            salt=DROPOUT_LOOKUP_TOKEN_SALT,
            max_age=DROPOUT_LOOKUP_TOKEN_MAX_AGE_SECONDS,
        )
    except signing.BadSignature:
        return None


def _dropout_phase_payload(user_group: str) -> dict:
    if not user_group:
        phase1_version = ''
        phase2_version = ''
    else:
        phase1_version = wit_bot_audit_version_for_group(user_group, 1)
        phase2_version = wit_bot_audit_version_for_group(user_group, 2)

    return {
        'phase1': {
            **DROPOUT_PHASES['phase1'],
            'version': phase1_version,
            'version_label': DROPOUT_VERSION_LABELS.get(phase1_version, phase1_version),
        },
        'phase2': {
            **DROPOUT_PHASES['phase2'],
            'version': phase2_version,
            'version_label': DROPOUT_VERSION_LABELS.get(phase2_version, phase2_version),
        },
    }


def _dropout_lookup_user(identifier: str):
    cleaned = _normalize_dropout_identifier(identifier)
    if not cleaned:
        return None, DropoutSurveyResponse.MATCHED_UNMATCHED

    participants = _dropout_participant_queryset().order_by('id')
    email_match = participants.filter(email__iexact=cleaned).first()
    if email_match is not None:
        return email_match, DropoutSurveyResponse.MATCHED_EMAIL

    username_match = participants.filter(username__iexact=cleaned).first()
    if username_match is not None:
        return username_match, DropoutSurveyResponse.MATCHED_USERNAME

    return None, DropoutSurveyResponse.MATCHED_UNMATCHED


def _dropout_lookup_payload(identifier: str, user, matched_identifier_type: str) -> dict:
    user_group = user.user_group if user is not None else ''
    phases = _dropout_phase_payload(user_group)
    identifier_hash = _dropout_identifier_hash(identifier)
    token_payload = {
        'user_id': user.id if user is not None else None,
        'identifier_hash': identifier_hash,
        'matched_identifier_type': matched_identifier_type,
        'user_group': user_group,
        'phase1_version': phases['phase1']['version'],
        'phase2_version': phases['phase2']['version'],
    }
    return {
        'matched': user is not None,
        'already_submitted': (
            user is not None
            and DropoutSurveyResponse.objects.filter(user=user).exists()
        ),
        'matched_identifier_type': matched_identifier_type,
        'lookup_token': signing.dumps(
            token_payload,
            salt=DROPOUT_LOOKUP_TOKEN_SALT,
            compress=True,
        ),
        'participant': {'username': user.username} if user is not None else None,
        'phases': phases,
    }


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


class DropoutSurveyContextView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        identifier = _normalize_dropout_identifier(request.data.get('identifier'))
        if not identifier:
            return Response(
                {'detail': 'Enter a username or email.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user, matched_identifier_type = _dropout_lookup_user(identifier)
        return Response(_dropout_lookup_payload(identifier, user, matched_identifier_type))


class DropoutSurveyResponseSubmitView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        answers = request.data.get('answers')
        if not isinstance(answers, dict) or not answers:
            return Response(
                {'detail': 'Submit at least one survey answer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lookup_token = request.data.get('lookup_token')
        if lookup_token:
            try:
                token_payload = signing.loads(
                    lookup_token,
                    salt=DROPOUT_LOOKUP_TOKEN_SALT,
                    max_age=DROPOUT_LOOKUP_TOKEN_MAX_AGE_SECONDS,
                )
            except signing.SignatureExpired:
                return Response(
                    {'detail': 'This lookup session expired. Please look up your account again.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except signing.BadSignature:
                return Response(
                    {'detail': 'Invalid lookup token.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            token_payload = {
                'user_id': None,
                'identifier_hash': '',
                'matched_identifier_type': DropoutSurveyResponse.MATCHED_UNMATCHED,
                'user_group': '',
                'phase1_version': '',
                'phase2_version': '',
            }

        user = None
        user_id = token_payload.get('user_id')
        if user_id is not None:
            user = _dropout_participant_queryset().filter(id=user_id).first()
            if user is None:
                return Response(
                    {'detail': 'This participant lookup is no longer valid.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if DropoutSurveyResponse.objects.filter(user=user).exists():
                return Response(
                    {'detail': 'Dropout survey already submitted.'},
                    status=status.HTTP_409_CONFLICT,
                )

        identifier_hash = token_payload.get('identifier_hash') or ''
        matched_identifier_type = (
            token_payload.get('matched_identifier_type')
            or DropoutSurveyResponse.MATCHED_UNMATCHED
        )
        with transaction.atomic():
            response = DropoutSurveyResponse.objects.create(
                user=user,
                identifier_hash=identifier_hash,
                matched_identifier_type=matched_identifier_type,
                user_group=token_payload.get('user_group') or '',
                phase1_version=token_payload.get('phase1_version') or '',
                phase2_version=token_payload.get('phase2_version') or '',
                answers=answers,
                lookup_metadata={
                    'identifier_hash': identifier_hash,
                    'matched': user is not None,
                    'matched_identifier_type': matched_identifier_type,
                    'source': 'jaewonkim.me/whoami-dropout',
                },
            )
            if user is not None:
                credit_dropout_survey_award(user=user)

        # A real response landed — clear any server-side autosave for it.
        if identifier_hash:
            DropoutSurveyDraft.objects.filter(identifier_hash=identifier_hash).delete()

        # Notify the research team on Slack. This endpoint is unauthenticated
        # and can be spammed with unmatched submissions, so never let a Slack
        # failure break the participant's submission.
        try:
            who = user.username if user else '(unmatched)'
            send_user_event_to_slack(
                f"🚪 Dropout survey submitted — {who} "
                f"(matched={user is not None}, via {matched_identifier_type}), "
                f"group={token_payload.get('user_group') or '?'}, "
                f"phase1={token_payload.get('phase1_version') or '?'}, "
                f"phase2={token_payload.get('phase2_version') or '?'}"
            )
        except Exception:
            pass

        return Response(
            {
                'id': response.id,
                'matched': user is not None,
                'submitted_at': response.submitted_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class DropoutSurveyDraftView(APIView):
    """Server-side autosave for an in-progress dropout survey. Authorized by the
    signed lookup token and keyed by the salted identifier hash it carries, so no
    raw username/email is stored and a participant can resume across devices.
    Best-effort — the frontend also keeps a local copy."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        payload = _dropout_decode_lookup_token(request.data.get('lookup_token'))
        identifier_hash = (payload or {}).get('identifier_hash') or ''
        if not identifier_hash:
            # Unmatched or expired token: nothing to persist server-side.
            return Response({'saved': False})

        draft = request.data.get('draft')
        if not isinstance(draft, dict):
            return Response(
                {'detail': 'Draft must be an object.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        DropoutSurveyDraft.objects.update_or_create(
            identifier_hash=identifier_hash,
            defaults={'data': draft},
        )
        return Response({'saved': True})


class DropoutSurveyDraftLoadView(APIView):
    """Return the saved in-progress draft for the token's identifier, if any."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        payload = _dropout_decode_lookup_token(request.data.get('lookup_token'))
        identifier_hash = (payload or {}).get('identifier_hash') or ''
        if not identifier_hash:
            return Response({'draft': None})

        draft = DropoutSurveyDraft.objects.filter(identifier_hash=identifier_hash).first()
        return Response({'draft': draft.data if draft else None})


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
        if is_retired_survey_slug(slug):
            return Response(status=status.HTTP_404_NOT_FOUND)
        try:
            survey = Survey.objects.get(slug=slug)
        except Survey.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        # Route version-suffixed slugs by user_group — direct URL access to
        # the wrong variant returns 404 so the schema mirror's "this slug
        # exists" doesn't leak through. Same predicate as the index queries.
        if not routes_to_user(survey, request.user):
            return Response(status=status.HTTP_404_NOT_FOUND)
        recovery_question_ids = missing_recovery_question_ids_for_user(request.user, survey)
        if recovery_question_ids is not None and not recovery_question_ids:
            return Response(status=status.HTTP_404_NOT_FOUND)
        ser = SurveyDetailSerializer(
            survey,
            context={
                'request': request,
                'recovery_question_ids': recovery_question_ids,
            },
        )
        return Response(ser.data)


class SurveyResponseSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, slug):
        if is_retired_survey_slug(slug):
            return Response(status=status.HTTP_404_NOT_FOUND)
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
                {'detail': 'This survey is closed.'},
                status=status.HTTP_410_GONE,
            )
        recovery_question_ids = missing_recovery_question_ids_for_user(request.user, survey)
        if recovery_question_ids is not None and not recovery_question_ids:
            return Response(status=status.HTTP_404_NOT_FOUND)
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
        schedule_resolution = resolve_submit_scheduled_survey(request.user, survey)
        if schedule_resolution.rejection == 'not_routed':
            return Response(status=status.HTTP_404_NOT_FOUND)
        if schedule_resolution.rejection == 'future':
            return Response(
                {'detail': 'This survey is not yet open for responses.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if schedule_resolution.rejection == 'expired':
            return Response(
                {'detail': 'This survey has expired and can no longer be answered.'},
                status=status.HTTP_410_GONE,
            )
        ser = SurveyResponseInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if recovery_question_ids is not None:
            invalid_question_ids = sorted({
                answer['question_id']
                for answer in ser.validated_data['answers']
                if answer['question_id'] not in recovery_question_ids
            })
            if invalid_question_ids:
                raise ValidationError({
                    'answers': [
                        'Some submitted questions are not currently needed for this participant.',
                    ],
                    'question_ids': invalid_question_ids,
                })
        point_award = None
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
                # Cache the viewer's friend ID set once for per-friend
                # tampering checks across all answers in this submission.
                friend_ids: set[int] | None = None
                for a in ser.validated_data['answers']:
                    question = SurveyQuestion.objects.get(id=a['question_id'], survey=survey)
                    # display_only blocks accept no value — defensively skip
                    # if the frontend sends one.
                    if question.type in INPUT_LESS_TYPES:
                        continue
                    validate_answer_value(question, a['value'])
                    target_user = None
                    if question.type in PER_FRIEND_TYPES:
                        target_user_id = a.get('target_user_id')
                        if target_user_id is None:
                            raise ValidationError({
                                'answers': [
                                    f'target_user_id is required for {question.type} '
                                    f'(question_id={question.id})'
                                ]
                            })
                        if friend_ids is None:
                            from surveys.friend_scope import (
                                eligible_friend_ids_for_survey,
                                is_friend_closeness_survey,
                            )
                            if is_friend_closeness_survey(survey):
                                friend_ids = eligible_friend_ids_for_survey(request.user, survey)
                            else:
                                friend_ids = set(
                                    request.user.connected_users.values_list('id', flat=True)
                                )
                        if target_user_id not in friend_ids:
                            raise ValidationError({
                                'answers': [
                                    f'target_user_id {target_user_id} is not eligible for '
                                    f'this per-friend survey'
                                ]
                            })
                        target_user = target_user_id  # FK by ID assignment
                    SurveyAnswer.objects.create(
                        response=response,
                        question=question,
                        value=a['value'],
                        target_user_id=target_user,
                    )
                # Persist `embedded_data: true` answers into the per-user
                # store keyed by question.slug. Subsequent surveys read these
                # via `{{slug}}` tokens or `serving_condition`.
                _persist_embedded_data(request.user, response)
                SurveyDraft.objects.filter(user=request.user, survey=survey).delete()
                point_award = create_survey_point_award(
                    user=request.user,
                    survey=survey,
                    response=response,
                    scheduled_survey=schedule_resolution.scheduled_survey,
                )
        except IntegrityError:
            return Response(
                {'detail': 'Already submitted.'}, status=status.HTTP_409_CONFLICT
            )
        # Ping the research team when a participant drops feedback via the
        # "Drop us a note" channel (anytime_reflection). GATED to that one
        # slug: this endpoint is the generic submit handler for EVERY survey,
        # so an ungated hook would flood Slack. Skip edit resubmissions and
        # never let a Slack failure break the submission.
        if survey.slug == 'anytime_reflection' and not is_edit:
            try:
                category = (
                    response.answers.filter(question__slug='anytime_category')
                    .values_list('value', flat=True)
                    .first()
                )
                send_user_event_to_slack(
                    f"*🗒️ Drop us a note*\n"
                    f"```\n"
                    f"User: {request.user.username} (ID: {request.user.id})\n"
                    f"Category: {category or 'N/A'}\n"
                    f"```"
                )
            except Exception:
                pass
        return Response(
            {'id': response.id, 'point_award': serialize_point_award(point_award)},
            status=status.HTTP_201_CREATED,
        )


class SurveyDraftView(APIView):
    """Lifecycle-triggered backup for in-progress survey drafts.

    The UI writes localStorage synchronously on every answer. This endpoint is
    a best-effort mirror used for reinstall recovery, so callers never need to
    block navigation on it.
    """
    permission_classes = [IsAuthenticated]

    def _get_survey(self, request, slug):
        if is_retired_survey_slug(slug):
            return None
        try:
            survey = Survey.objects.get(slug=slug)
        except Survey.DoesNotExist:
            return None
        if not routes_to_user(survey, request.user):
            return None
        return survey

    def get(self, request, slug):
        survey = self._get_survey(request, slug)
        if survey is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        draft = SurveyDraft.objects.filter(user=request.user, survey=survey).first()
        if draft is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(SurveyDraftSerializer(draft).data)

    def put(self, request, slug):
        survey = self._get_survey(request, slug)
        if survey is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        ser = SurveyDraftSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        draft, _ = SurveyDraft.objects.update_or_create(
            user=request.user,
            survey=survey,
            defaults=ser.validated_data,
        )
        return Response(SurveyDraftSerializer(draft).data)

    def delete(self, request, slug):
        survey = self._get_survey(request, slug)
        if survey is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        SurveyDraft.objects.filter(user=request.user, survey=survey).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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
        answers = []
        for answer in response.answers.all():
            item = {
                'question_id': answer.question_id,
                'value': answer.value,
            }
            if answer.target_user_id is not None:
                item['target_user_id'] = answer.target_user_id
            answers.append(item)
        return Response({
            'id': response.id,
            'submitted_at': response.submitted_at.isoformat(),
            'answers': answers,
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
    """Answered Today on WIT archive.

    This endpoint backs the grouped "Today on WIT" row in the survey index.
    It intentionally excludes SOTD-style daily surveys and unanswered/missed
    rows; those are separate surveys, not part of the completed daily diary
    results archive.
    """
    permission_classes = [IsAuthenticated]

    def _answered_daily_base_schedule_ids(self, user):
        awarded_ids = set(
            PointAward.objects.filter(
                user=user,
                source_kind=PointAward.SOURCE_SURVEY,
                scheduled_survey__survey__slug=DAILY_ARCHIVE_SURVEY_SLUG,
            ).values_list('scheduled_survey_id', flat=True)
        )

        response_dates = {
            (submitted_at.astimezone(LA_TZ) - timedelta(hours=7)).date()
            for submitted_at in SurveyResponse.objects.filter(
                user=user,
                survey__slug=DAILY_ARCHIVE_SURVEY_SLUG,
            ).values_list('submitted_at', flat=True)
        }
        fallback_ids = set()
        if response_dates:
            fallback_ids = set(
                ScheduledSurvey.objects.filter(
                    cadence=CADENCE_DAILY,
                    survey__slug=DAILY_ARCHIVE_SURVEY_SLUG,
                    window_start__in=response_dates,
                ).values_list('id', flat=True)
            )
        return awarded_ids | fallback_ids

    def get(self, request):
        today = _today_la_7am()
        answered_scheduled_ids = self._answered_daily_base_schedule_ids(request.user)
        qs = (
            ScheduledSurvey.objects
            .filter(
                cadence=CADENCE_DAILY,
                survey__slug=DAILY_ARCHIVE_SURVEY_SLUG,
                survey__results_hidden=False,
                window_start__lte=today,
                id__in=answered_scheduled_ids,
            )
            .select_related('survey')
            .order_by('-window_start')
        )
        ser = PastSurveySerializer(
            qs,
            many=True,
            context={
                'request': request,
                'answered_scheduled_ids': answered_scheduled_ids,
            },
        )
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
        all_entries = [
            entry
            for bucket_name in ('available_now', 'late_but_accepted', 'completed')
            for entry in result[bucket_name]
        ]
        draft_by_survey_id = {
            draft.survey_id: draft
            for draft in SurveyDraft.objects.filter(
                user=request.user,
                survey_id__in=[entry.survey_id for entry in all_entries],
            )
        }
        serializer_context = {
            'request': request,
            'draft_by_survey_id': draft_by_survey_id,
        }
        for bucket_name in ('available_now', 'late_but_accepted', 'completed'):
            for entry in result[bucket_name]:
                entry.bucket = bucket_name
        return Response({
            'available_now': SurveyIndexEntrySerializer(
                result['available_now'], many=True, context=serializer_context,
            ).data,
            'late_but_accepted': SurveyIndexEntrySerializer(
                result['late_but_accepted'], many=True, context=serializer_context,
            ).data,
            'completed': SurveyIndexEntrySerializer(
                result['completed'], many=True, context=serializer_context,
            ).data,
        })


class ReimbursementView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(reimbursement_state_for_user(request.user))
