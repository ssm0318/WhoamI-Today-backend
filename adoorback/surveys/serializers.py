from rest_framework import serializers

from surveys.models import (
    CADENCE_DAILY, DISPLAY_ONLY, INPUT_LESS_TYPES, LIKERT_5_NA, LIKERT_RANGES, NA_SENTINEL,
    PER_FRIEND_TYPES, SLIDER, ScheduledSurvey, Survey, SurveyOption,
    SurveyDraft, SurveyQuestion, SurveyResponse,
)
from surveys.scheduling import _today_la_7am


def _page_count_for_questions(questions) -> int:
    """Mirror the frontend's page grouping for draft/edit hydration."""
    total = 0
    in_per_friend_block = False
    for question in questions:
        if question.type in PER_FRIEND_TYPES:
            if not in_per_friend_block:
                total += 1
                in_per_friend_block = True
            continue
        total += 1
        in_per_friend_block = False
    return total


def _response_as_draft_payload(response: SurveyResponse) -> dict:
    """Shape an existing editable response like SurveyDraftSerializer.

    The frontend already knows how to hydrate answer state from `draft`.
    Reusing that shape means edit mode opens with saved answers populated,
    including per-friend answers grouped as question_id -> target_user_id.
    """
    answers = {}
    for answer in response.answers.select_related('question').order_by(
        'question__order', 'target_user_id',
    ):
        question_id = str(answer.question_id)
        if answer.question.type in PER_FRIEND_TYPES:
            if answer.target_user_id is None:
                continue
            answers.setdefault(question_id, {})[str(answer.target_user_id)] = answer.value
            continue
        answers[question_id] = answer.value

    total_pages = _page_count_for_questions(response.survey.questions.order_by('order'))
    return {
        'answers': answers,
        'current_page_index': 0,
        'total_pages': total_pages,
        'answered_pages': total_pages,
        'progress_pct': 100 if total_pages else 0,
        'saved_at': response.submitted_at,
    }


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
        # Per-friend question types are fanned out into one virtual question
        # per friend by SurveyDetailSerializer post-processing; skip token
        # substitution here so {{friend_name}} etc. survive the survey-level
        # pass intact and get resolved later with the per-friend token map.
        if instance.type in PER_FRIEND_TYPES:
            return data
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


def _expand_per_friend_questions(questions_data, questions_qs, *, viewer, survey_tokens):
    """Fan out per_friend_* question rows into one virtual row per friend.

    Per-friend question types render once per friend the viewer currently
    has. Each virtual row carries:
      - target_user_id  / target_user_username  → identifies the friend
      - baseline_closeness  / baseline_relationship_type  → from the
        viewer's earliest non-skipped FriendEvaluation for that friend
        (NULL when no baseline exists)
      - prompt / description / placeholder / content fields with
        {{friend_name}} and {{baseline_*}} tokens substituted
    Non-per-friend questions pass through unchanged. With 0 friends, all
    per-friend questions are dropped from the output (their inputs would
    have no targets) — non-per-friend questions still render so the survey
    isn't a blank page.
    Friends are sorted by username for predictable display.
    """
    has_per_friend = any(q.type in PER_FRIEND_TYPES for q in questions_qs)
    if not has_per_friend:
        return questions_data

    friends = list(viewer.connected_users.order_by('username'))
    if not friends:
        return [
            q for q, qm in zip(questions_data, questions_qs)
            if qm.type not in PER_FRIEND_TYPES
        ]

    # Baseline lookup: {friend_id → most recent non-skipped FriendEvaluation}.
    # `order_by('-created_at')` + `setdefault` picks the most recent row per
    # friend. Single query for all friends.
    from account.models import FriendEvaluation
    baselines: dict[int, FriendEvaluation] = {}
    for ev in (
        FriendEvaluation.objects
        .filter(evaluator=viewer, evaluated_user__in=friends, skipped=False)
        .order_by('-created_at')
    ):
        baselines.setdefault(ev.evaluated_user_id, ev)

    from surveys.tokens import apply_to_question_dict, build_per_friend_tokens

    expanded = []
    survey_tokens = survey_tokens or {}
    for q_dict, q_model in zip(questions_data, questions_qs):
        if q_model.type not in PER_FRIEND_TYPES:
            expanded.append(q_dict)
            continue
        for friend in friends:
            baseline = baselines.get(friend.id)
            per_friend_tokens = build_per_friend_tokens(friend, baseline)
            merged_tokens = {**survey_tokens, **per_friend_tokens}
            virtual = dict(q_dict)
            apply_to_question_dict(virtual, merged_tokens)
            virtual['target_user_id'] = friend.id
            virtual['target_user_username'] = friend.username
            virtual['baseline_closeness'] = baseline.closeness if baseline else None
            virtual['baseline_relationship_type'] = (
                baseline.relationship_type if baseline else None
            )
            expanded.append(virtual)
    return expanded


class SurveyDetailSerializer(serializers.ModelSerializer):
    questions = SurveyQuestionSerializer(many=True, read_only=True)
    user_has_responded = serializers.SerializerMethodField()
    responder_count = serializers.SerializerMethodField()
    draft = serializers.SerializerMethodField()
    point_locked_by_prereq_slug = serializers.SerializerMethodField()
    point_locked_by_prereq_title_en = serializers.SerializerMethodField()
    point_locked_by_prereq_title_ko = serializers.SerializerMethodField()
    point_award = serializers.SerializerMethodField()

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
            'point_value',
            'point_prereq_slug',
            'point_locked_by_prereq_slug',
            'point_locked_by_prereq_title_en',
            'point_locked_by_prereq_title_ko',
            'point_award',
            'result_kind',
            'questions',
            'user_has_responded',
            'responder_count',
            'draft',
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
        # Fan out per-friend question types: each per_friend_* source row in
        # `data['questions']` is replaced with N virtual rows, one per friend
        # the viewer currently has. Each virtual row carries a `target_user_id`
        # and pre-substituted text. Skipped when there's no authenticated
        # viewer (e.g. anonymous preview) — the source row passes through
        # untouched and the frontend will show an empty state.
        if viewer is not None and getattr(viewer, 'is_authenticated', False):
            data['questions'] = _expand_per_friend_questions(
                data.get('questions', []),
                instance.questions.all(),
                viewer=viewer,
                survey_tokens=tokens,
            )
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

    def get_draft(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        existing = (
            SurveyResponse.objects
            .filter(survey=obj, user=request.user)
            .select_related('survey')
            .prefetch_related('answers__question')
            .first()
        )
        if existing is not None:
            if obj.editable and not obj.repeatable and not obj.closed:
                return _response_as_draft_payload(existing)
            return None
        draft = SurveyDraft.objects.filter(survey=obj, user=request.user).first()
        if draft is None:
            return None
        return SurveyDraftSerializer(draft).data

    def _point_lock(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        from surveys.points import point_prereq_lock_for_user
        return point_prereq_lock_for_user(obj, request.user)

    def get_point_locked_by_prereq_slug(self, obj):
        lock = self._point_lock(obj)
        return lock['slug'] if lock else None

    def get_point_locked_by_prereq_title_en(self, obj):
        lock = self._point_lock(obj)
        return lock['title_en'] if lock else None

    def get_point_locked_by_prereq_title_ko(self, obj):
        lock = self._point_lock(obj)
        return lock['title_ko'] if lock else None

    def get_point_award(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        from surveys.points import get_point_award_for_survey, serialize_point_award
        return serialize_point_award(
            get_point_award_for_survey(
                request.user,
                obj,
                scheduled_survey=self.context.get('scheduled_survey'),
            )
        )


class SurveyAnswerInputSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    # `allow_null=True` so likert_5_na N/A picks (NA_SENTINEL) submit
    # cleanly. JSONField rejects None by default.
    value = serializers.JSONField(allow_null=True)
    # For per-friend question types: which friend this answer is about.
    # Required on per_friend_* types; ignored on every other type. Submit
    # view validates friend-list membership before write.
    target_user_id = serializers.IntegerField(required=False, allow_null=True)


class SurveyResponseInputSerializer(serializers.Serializer):
    answers = SurveyAnswerInputSerializer(many=True)


class SurveyDraftSerializer(serializers.ModelSerializer):
    saved_at = serializers.DateTimeField(source='updated_at', read_only=True)

    class Meta:
        model = SurveyDraft
        fields = [
            'answers',
            'current_page_index',
            'total_pages',
            'answered_pages',
            'progress_pct',
            'saved_at',
        ]

    def validate(self, attrs):
        total_pages = attrs.get('total_pages', 0)
        answered_pages = attrs.get('answered_pages', 0)
        current_page_index = attrs.get('current_page_index', 0)
        progress_pct = attrs.get('progress_pct', 0)

        if progress_pct > 100:
            raise serializers.ValidationError({'progress_pct': 'Must be between 0 and 100.'})
        if answered_pages > total_pages:
            raise serializers.ValidationError({'answered_pages': 'Cannot exceed total_pages.'})
        if total_pages > 0 and current_page_index >= total_pages:
            raise serializers.ValidationError({
                'current_page_index': 'Must be lower than total_pages.',
            })
        return attrs


class SurveyDraftSummarySerializer(serializers.ModelSerializer):
    saved_at = serializers.DateTimeField(source='updated_at', read_only=True)

    class Meta:
        model = SurveyDraft
        fields = ['progress_pct', 'answered_pages', 'total_pages', 'saved_at']


class PastSurveySerializer(serializers.ModelSerializer):
    """Daily-archive serializer. Wraps a daily ScheduledSurvey row in the same
    {date, survey, user_answered, results_unlocked} shape that DailySurvey rows
    used to produce, so the existing daily-archive frontend doesn't change.
    """
    date = serializers.DateField(source='window_start', read_only=True)
    survey = serializers.SerializerMethodField()
    user_answered = serializers.SerializerMethodField()
    results_unlocked = serializers.SerializerMethodField()

    class Meta:
        model = ScheduledSurvey
        fields = ['id', 'date', 'survey', 'user_answered', 'results_unlocked']

    def get_survey(self, obj):
        return SurveyDetailSerializer(
            obj.survey,
            context={**self.context, 'scheduled_survey': obj},
        ).data

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
    results_unlocked = serializers.SerializerMethodField()
    draft = serializers.SerializerMethodField()
    point_value = serializers.IntegerField(source='survey.point_value', read_only=True)
    point_locked_by_prereq_slug = serializers.SerializerMethodField()
    point_locked_by_prereq_title_en = serializers.SerializerMethodField()
    point_locked_by_prereq_title_ko = serializers.SerializerMethodField()
    point_award = serializers.SerializerMethodField()

    class Meta:
        model = ScheduledSurvey
        fields = [
            'id', 'cadence', 'sequence_index', 'sidebar_order',
            'window_start', 'window_end', 'allow_late',
            'survey', 'bucket',
            'user_answered', 'submitted_at',
            'redirect_url',
            'results_unlocked',
            'draft',
            'point_value',
            'point_locked_by_prereq_slug',
            'point_locked_by_prereq_title_en',
            'point_locked_by_prereq_title_ko',
            'point_award',
        ]

    def get_redirect_url(self, obj):
        if getattr(obj, 'bucket', None) == 'completed':
            if obj.survey.editable and not obj.survey.repeatable and not obj.survey.closed:
                return f'/surveys/{obj.survey.slug}/answer'
            return f'/surveys/{obj.survey.slug}/results'
        return f'/surveys/{obj.survey.slug}/answer'

    def get_results_unlocked(self, obj):
        if not getattr(obj, 'user_answered', False):
            return False
        if obj.survey.results_hidden:
            return False
        if obj.cadence == CADENCE_DAILY:
            return obj.window_start < _today_la_7am()
        return True

    def get_draft(self, obj):
        if getattr(obj, 'user_answered', False):
            return None
        draft_by_survey_id = self.context.get('draft_by_survey_id') or {}
        draft = draft_by_survey_id.get(obj.survey_id)
        if draft is None:
            return None
        return SurveyDraftSummarySerializer(draft).data

    def _point_lock(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        from surveys.points import point_prereq_lock_for_user
        return point_prereq_lock_for_user(obj.survey, request.user)

    def get_point_locked_by_prereq_slug(self, obj):
        lock = self._point_lock(obj)
        return lock['slug'] if lock else None

    def get_point_locked_by_prereq_title_en(self, obj):
        lock = self._point_lock(obj)
        return lock['title_en'] if lock else None

    def get_point_locked_by_prereq_title_ko(self, obj):
        lock = self._point_lock(obj)
        return lock['title_ko'] if lock else None

    def get_point_award(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        from surveys.points import get_point_award_for_scheduled, serialize_point_award
        return serialize_point_award(get_point_award_for_scheduled(request.user, obj))
