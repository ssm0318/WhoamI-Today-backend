from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from adoorback.models import AdoorTimestampedModel


# Question types — defined at the question level so a single Survey can mix them
# (e.g. 19 likert items + 1 free-text reflection). Adding a new type:
#   1. Add a constant + entry to TYPE_CHOICES below.
#   2. Add the input dispatcher case in surveys/serializers.py and the frontend's
#      SurveyAnswerForm.
#   3. Add the default result kind mapping below.
#   4. If it's a new likert variant, extend LIKERT_RANGES below.
LIKERT_3 = 'likert_3'
LIKERT_4 = 'likert_4'
LIKERT_5 = 'likert_5'
LIKERT_5_NA = 'likert_5_na'
LIKERT_6 = 'likert_6'
LIKERT_7 = 'likert_7'
SINGLE_CHOICE = 'single_choice'
MULTI_CHOICE = 'multi_choice'
FREE_TEXT = 'free_text'
SLIDER = 'slider'
DISPLAY_ONLY = 'display_only'
# Per-friend question types: at render time the API expands one virtual
# question per friend the requesting user currently has. At submit time the
# frontend sends one answer per friend, each tagged with `target_user_id`,
# and the backend writes one SurveyAnswer row per (response, question,
# target_user). Used by the end-of-phase closeness re-evaluation surveys.
PER_FRIEND_LIKERT_5 = 'per_friend_likert_5'
PER_FRIEND_SINGLE_CHOICE = 'per_friend_single_choice'
TYPE_CHOICES = (
    (LIKERT_3, 'Likert 3-point'),
    (LIKERT_4, 'Likert 4-point'),
    (LIKERT_5, 'Likert 5-point'),
    (LIKERT_5_NA, 'Likert 5-point with N/A option'),
    (LIKERT_6, 'Likert 6-point'),
    (LIKERT_7, 'Likert 7-point'),
    (SINGLE_CHOICE, 'Single choice'),
    (MULTI_CHOICE, 'Multi choice'),
    (FREE_TEXT, 'Free text'),
    (SLIDER, 'Slider'),
    (DISPLAY_ONLY, 'Display-only content (no input)'),
    (PER_FRIEND_LIKERT_5, 'Likert 5-point asked once per friend'),
    (PER_FRIEND_SINGLE_CHOICE, 'Single choice asked once per friend'),
)
# Question types that expand into one virtual question per friend at render
# time. Aggregation / analysis treats the resulting SurveyAnswer rows as
# (target_user, value) tuples — see dump_friend_closeness_panel.
PER_FRIEND_TYPES = frozenset({PER_FRIEND_LIKERT_5, PER_FRIEND_SINGLE_CHOICE})

# Inclusive (min, max) numeric range per likert variant. likert_5_na uses the
# same numeric range as likert_5; the N/A response is stored as a sentinel
# (None) and excluded from scoring entirely — see aggregation.py.
LIKERT_RANGES = {
    LIKERT_3: (1, 3),
    LIKERT_4: (1, 4),
    LIKERT_5: (1, 5),
    LIKERT_5_NA: (1, 5),
    LIKERT_6: (1, 6),
    LIKERT_7: (1, 7),
    PER_FRIEND_LIKERT_5: (1, 5),
}
LIKERT_TYPES = frozenset(LIKERT_RANGES.keys())
# Sentinel value persisted in SurveyAnswer.value when the user picks N/A on a
# likert_5_na question. None is JSON-natural and trivially recognized by the
# aggregation strategies that need to skip it.
NA_SENTINEL = None

# Question types that NEVER store a value (no input rendered, no row in
# SurveyAnswer expected for these questions on submission).
INPUT_LESS_TYPES = frozenset({DISPLAY_ONLY})

# Result rendering kinds — the registry key shared between the backend aggregation
# strategy and the frontend renderer. Adding a new kind: see surveys/aggregation.py
# (backend strategy) and src/components/survey/results/registry.ts (frontend).
RESULT_AGGREGATED_LIKERT = 'aggregated_likert'
RESULT_OPTION_COUNTS = 'option_counts'
RESULT_WORDCLOUD = 'wordcloud'
RESULT_SLIDER_HISTOGRAM = 'slider_histogram'
RESULT_SCALE_SCORE_HISTOGRAM = 'scale_score_histogram'
RESULT_SLIDER_HISTOGRAM_PAIRED = 'slider_histogram_paired'
RESULT_KIND_CHOICES = (
    (RESULT_AGGREGATED_LIKERT, 'Aggregated likert score'),
    (RESULT_OPTION_COUNTS, 'Per-option counts'),
    (RESULT_WORDCLOUD, 'Wordcloud (free-text tokens)'),
    (RESULT_SLIDER_HISTOGRAM, 'Slider histogram'),
    (RESULT_SCALE_SCORE_HISTOGRAM, 'Scale-score histogram (survey-level summary)'),
    (RESULT_SLIDER_HISTOGRAM_PAIRED, 'Paired-slider 2D circumplex'),
)

# Default result kind per question type. A panel can override with
# SurveyQuestion.result_kind, but most surveys won't need to.
DEFAULT_RESULT_KIND_FOR_TYPE = {
    LIKERT_3: RESULT_AGGREGATED_LIKERT,
    LIKERT_4: RESULT_AGGREGATED_LIKERT,
    LIKERT_5: RESULT_AGGREGATED_LIKERT,
    LIKERT_5_NA: RESULT_AGGREGATED_LIKERT,
    LIKERT_6: RESULT_AGGREGATED_LIKERT,
    LIKERT_7: RESULT_AGGREGATED_LIKERT,
    SINGLE_CHOICE: RESULT_OPTION_COUNTS,
    MULTI_CHOICE: RESULT_OPTION_COUNTS,
    FREE_TEXT: RESULT_WORDCLOUD,
    SLIDER: RESULT_SLIDER_HISTOGRAM,
    # Per-friend likerts aggregate the same way as regular likerts (mean / SD)
    # over all (response, question, target_user) tuples. Per-friend single
    # choice aggregates to per-option counts. Neither type currently surfaces
    # results to participants (results_hidden=True on the closeness re-eval
    # surveys), so this is for analysis-side completeness.
    PER_FRIEND_LIKERT_5: RESULT_AGGREGATED_LIKERT,
    PER_FRIEND_SINGLE_CHOICE: RESULT_OPTION_COUNTS,
    # display_only never aggregates — group_panels skips these questions entirely.
}

# Result kinds for which friend / close-friend buckets are suppressed by default
# (token-level k-anonymity isn't enough protection in small friend pools).
PRIVACY_FRIEND_DISABLED_KINDS = frozenset({RESULT_WORDCLOUD})


class Survey(AdoorTimestampedModel):
    slug = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    interpretation = models.TextField(
        blank=True,
        default='',
        help_text='Markdown shown after results unlock (e.g., "Higher scores indicate ...")',
    )
    friend_visible = models.BooleanField(
        default=True,
        help_text=(
            'Survey-level kill switch for friend / close-friend buckets across all panels. '
            'Individual panels may still be suppressed when their kind is wordcloud-style.'
        ),
    )
    results_hidden = models.BooleanField(
        default=False,
        help_text='If True, this survey accepts responses but the results endpoint always 404s.',
    )
    last_used_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text='Legacy field — written by the now-deleted rotation cron. Unused.',
    )
    # Survey-level result_kind. When set (non-empty), it overrides every
    # question's `result_kind` on the results page — used for whole-survey
    # summaries like scale_score_histogram. Blank → fall back to per-question
    # rendering, which is the default flow.
    result_kind = models.CharField(
        max_length=32,
        choices=RESULT_KIND_CHOICES,
        blank=True,
        default='',
        help_text=(
            'Optional whole-survey result renderer. When set, overrides the '
            'per-question result_kind on the results page (e.g. '
            'scale_score_histogram for a single summary score across all items).'
        ),
    )
    score_formula = models.CharField(
        max_length=64,
        blank=True,
        default='',
        help_text=(
            'Name of a registered formula in surveys/scoring/registry.py. When '
            'blank, scale_score_histogram falls back to the default sum-with-'
            'reverse formula. See `surveys.scoring.registry.score_formulas`.'
        ),
    )
    score_components = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            'Optional list of question slugs to include in scale_score_histogram '
            'scoring. Empty list = include every likert_* item in the survey.'
        ),
    )
    tokens = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            'Static token map substituted into prompts/descriptions/placeholders '
            'at render time via {{token_name}}. e.g. {"phase_label": "Phase 1"}.'
        ),
    )
    repeatable = models.BooleanField(
        default=False,
        help_text=(
            'When True, the same user may submit this survey multiple times '
            'within its window. Each submission is a separate SurveyResponse '
            'row. Used for anytime_reflection-style ongoing feedback surveys.'
        ),
    )
    serving_condition = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            'Optional rule for skipping this survey for specific users. Form: '
            '{"skip_if_user_embedded_data": {"<key>": <value>, ...}}. When all '
            'key/value pairs match the user\'s embedded data, the survey is '
            'not served to that user.'
        ),
    )
    editable = models.BooleanField(
        default=False,
        help_text=(
            'When True, re-submitting REPLACES the existing answers instead of '
            '409. One SurveyResponse per user, but updateable until the survey '
            'is closed. Frontend should pre-fill the form with prior answers.'
        ),
    )
    closed = models.BooleanField(
        default=False,
        help_text=(
            'Researcher-only flag. When True, new submissions return 410 (gone). '
            'Existing responses are preserved. Daily / SOTD surveys naturally '
            'close at end-of-day via window_end; this flag is for biweekly / '
            'anytime / endpoint surveys that researchers manually close at '
            'study end.'
        ),
    )
    priority = models.IntegerField(
        default=0,
        help_text=(
            'Higher = surfaced earlier in the survey index. Convention: '
            '100 = research-critical (feature_eval, goal_comparison), '
            '80 = daily / SOTD, 50 = weekly, 40 = mid/post/pre, 20 = anytime.'
        ),
    )
    point_value = models.PositiveIntegerField(
        default=0,
        help_text=(
            'Provisional max points credited on first submit. 0 = no points. '
            'Researcher audit at study end may downgrade individual awards.'
        ),
    )
    point_prereq_slug = models.CharField(
        max_length=64,
        blank=True,
        default='',
        help_text=(
            'Slug of a survey that must be completed before this one credits '
            'its full point_value. Blank = no prereq. Submission with prereq '
            'unmet still creates a PointAward row with awarded_points=0.'
        ),
    )

    class Meta:
        ordering = ['slug']

    def __str__(self):
        return f'Survey<{self.slug}>'


class SurveyQuestion(AdoorTimestampedModel):
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='questions')
    order = models.PositiveSmallIntegerField()
    type = models.CharField(
        max_length=32,
        choices=TYPE_CHOICES,
        default=LIKERT_5,
        help_text='Input type. Determines which input UI is rendered and how value is validated.',
    )
    prompt = models.TextField()
    low_label = models.CharField(max_length=80, blank=True, default='')
    high_label = models.CharField(max_length=80, blank=True, default='')
    reverse_scored = models.BooleanField(default=False)
    result_kind = models.CharField(
        max_length=32,
        choices=RESULT_KIND_CHOICES,
        blank=True,
        default='',
        help_text='Override the default renderer for this question. Blank → derived from `type`.',
    )
    result_group = models.CharField(
        max_length=64,
        blank=True,
        default='',
        help_text=(
            'Group key — questions sharing a non-empty group are aggregated into a single panel. '
            'Blank → grouped implicitly with sibling questions of the same type.'
        ),
    )
    result_hidden = models.BooleanField(
        default=False,
        help_text='If True, this question is answered but never appears on the results page.',
    )
    # Slider-only inclusive bounds. Always nullable; required (and validated by
    # clean()) when type=slider. low_label / high_label double as the slider's
    # min/max labels — no parallel fields.
    slider_min_value = models.IntegerField(null=True, blank=True)
    slider_max_value = models.IntegerField(null=True, blank=True)
    # Stable identifier within a survey — used by score_formulas, embedded-data
    # storage, conditional_display.depends_on, and data exports. Optional on
    # legacy questions (blank='') so existing rows don't need backfill, but the
    # uniqueness constraint below applies to non-empty slugs.
    slug = models.SlugField(
        max_length=80,
        blank=True,
        default='',
        help_text='Stable per-question identifier. Required for any question referenced by a score formula or conditional_display.',
    )
    # Secondary text below `prompt`. Markdown-rendered. Empty if not used.
    description = models.TextField(blank=True, default='')
    # free_text-only hint shown inside an empty input.
    placeholder = models.CharField(max_length=200, blank=True, default='')
    # Soft length floor for free_text. NULL = no minimum. Combined with
    # `min_length_warning` to nudge — does not block submission.
    min_length = models.PositiveIntegerField(null=True, blank=True)
    min_length_warning = models.TextField(
        blank=True,
        default='',
        help_text='Markdown shown when `min_length` is unmet. Submission still allowed after one acknowledgment.',
    )
    required = models.BooleanField(
        default=True,
        help_text='If True, submission is blocked until this question is answered (unless conditionally hidden).',
    )
    # 6th option label for likert_5_na. Stored as None ("N/A") in the user's
    # response and excluded from numeric aggregations.
    na_option = models.CharField(
        max_length=80,
        blank=True,
        default='',
        help_text='Label for the N/A option on likert_5_na questions. Empty string suppresses the N/A choice.',
    )
    # When True, the answer to this question is persisted into the user's
    # UserSurveyEmbeddedData store (keyed by question.slug) on submission.
    # Subsequent surveys can reference it via tokens / serving_condition.
    embedded_data = models.BooleanField(
        default=False,
        help_text='If True, the answer is copied into UserSurveyEmbeddedData (keyed by slug) on submission.',
    )
    # Display-time gating rule. Empty dict = always shown. Form:
    #   {"depends_on": "<other_question_slug>", "show_when_value": <v>}
    #   {"depends_on": "<other_question_slug>", "show_when_value_not": <v>}
    #   {"depends_on": "<other_question_slug>", "show_when_value_in": [<v1>, ...]}
    #   {"depends_on": "<other_question_slug>", "show_when_value_includes": <v>}
    conditional_display = models.JSONField(
        default=dict,
        blank=True,
        help_text='Rule for showing this question based on a prior answer in the same submission.',
    )
    # display_only-only: markdown content rendered as a header/explanation
    # block. No input is rendered, no value stored.
    content = models.TextField(
        blank=True,
        default='',
        help_text='Markdown body for display_only questions. Token substitution applies.',
    )

    class Meta:
        ordering = ['survey_id', 'order']
        constraints = [
            models.UniqueConstraint(fields=['survey', 'order'], name='unique_question_order_per_survey'),
            # Slug must be unique within a survey when set; empty slugs (legacy
            # questions and display_only blocks that don't need a stable ID)
            # are skipped by the partial-index condition.
            models.UniqueConstraint(
                fields=['survey', 'slug'],
                condition=~models.Q(slug=''),
                name='unique_question_slug_per_survey',
            ),
        ]

    def clean(self):
        super().clean()
        if self.type == SLIDER:
            if self.slider_min_value is None or self.slider_max_value is None:
                raise ValidationError(
                    'slider questions require both slider_min_value and slider_max_value'
                )
            if self.slider_min_value >= self.slider_max_value:
                raise ValidationError(
                    'slider_min_value must be strictly less than slider_max_value'
                )
        if self.type == DISPLAY_ONLY and self.required:
            # display_only blocks have no input — they cannot be "required".
            raise ValidationError("display_only questions cannot be required=True")
        if self.embedded_data and not self.slug:
            raise ValidationError(
                "embedded_data=True requires a non-empty slug (used as the storage key)"
            )

    @property
    def effective_result_kind(self) -> str:
        return self.result_kind or DEFAULT_RESULT_KIND_FOR_TYPE.get(self.type, RESULT_OPTION_COUNTS)

    @property
    def effective_group_key(self) -> str:
        """Implicit group when no explicit `result_group` set: one group per (kind, type)."""
        return self.result_group or f'__auto__:{self.effective_result_kind}'


class SurveyOption(AdoorTimestampedModel):
    question = models.ForeignKey(SurveyQuestion, on_delete=models.CASCADE, related_name='options')
    order = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=160)
    # JSONField so options can carry either integer codes (1, 2, 3 — typical
    # for likert + ordinal choices) or string codes ("yes", "minor", "real" —
    # typical for categorical choices that read better in research exports).
    # SurveyAnswer.value follows the same shape: choice answers carry the
    # selected option's value verbatim, so aggregation Counter lookups stay
    # type-consistent across answer ↔ option.
    value = models.JSONField(
        help_text=(
            'Score code (int for likert / ordinal) or category code (string for '
            'categorical). Multi-choice answers store a list of these values.'
        ),
    )

    class Meta:
        ordering = ['question_id', 'order']
        constraints = [
            models.UniqueConstraint(fields=['question', 'order'], name='unique_option_order_per_question'),
        ]


# Cadences for the 4-week study schedule. See surveys/scheduling.py for the
# bucketing rules and surveys/migrations/0004_seed_study_schedule.py for the
# hardcoded calendar.
CADENCE_DAILY = 'daily'
CADENCE_WEEKLY = 'weekly'
CADENCE_BIWEEKLY = 'biweekly'
CADENCE_ANYTIME = 'anytime'
CADENCE_ENDPOINT = 'endpoint'
CADENCE_CHOICES = (
    (CADENCE_DAILY, 'Daily'),
    (CADENCE_WEEKLY, 'Weekly'),
    (CADENCE_BIWEEKLY, 'Biweekly'),
    (CADENCE_ANYTIME, 'Anytime'),
    (CADENCE_ENDPOINT, 'Endpoint'),
)


class ScheduledSurvey(AdoorTimestampedModel):
    """Schedules a Survey for participants of the 4-week study.

    Cohort-wide absolute dates: every user is on the same calendar.
    `window_start` and `window_end` define the eligibility window.
    `window_end=None` means the survey never closes (anytime / endpoint).

    Bucketing rules (see surveys/services/scheduling.get_survey_index):
      - Available now:     window_start <= today AND
                           (window_end IS NULL OR today <= window_end) AND
                           user has not answered.
      - Late but accepted: window_end < today AND allow_late=True AND
                           user has not answered.
      - Completed:         user has answered.
      - Expired (hidden):  window_end < today AND allow_late=False AND
                           user has not answered. Only daily falls here —
                           never returned by the API.
    """
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='schedules')
    cadence = models.CharField(max_length=16, choices=CADENCE_CHOICES)
    window_start = models.DateField()
    window_end = models.DateField(null=True, blank=True)
    allow_late = models.BooleanField(default=True)
    sequence_index = models.PositiveSmallIntegerField()
    sidebar_order = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            'Optional explicit order within each survey index bucket. Lower '
            'numbers appear earlier. Blank falls back to survey priority, '
            'window_start, then sequence_index.'
        ),
    )
    target_user_group = models.CharField(
        max_length=32,
        blank=True,
        default='',
        help_text=(
            "Restrict this row to a single user_group (e.g. 'group_w_first'). "
            "Empty = all groups (default). Combined with the slug-suffix "
            "routing in `routes_to_user`, this lets the SAME survey content "
            "be scheduled twice with different windows per group — useful "
            "for `feature_eval_w` opening Day 5 for w_first / Day 19 for "
            "q_first without needing two distinct slugs."
        ),
    )

    class Meta:
        ordering = ['window_start', 'sequence_index']
        constraints = [
            models.UniqueConstraint(
                fields=['cadence', 'sequence_index'],
                name='unique_scheduled_survey_cadence_seq',
            ),
        ]

    def __str__(self):
        return f'{self.cadence}#{self.sequence_index} → {self.survey.slug} ({self.window_start})'


class SurveyResponse(AdoorTimestampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='survey_responses')
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='responses')
    submitted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        # No DB-level uniqueness on (user, survey): repeatable surveys
        # (anytime_reflection-style) intentionally allow multiple rows per
        # user. The view-level check in SurveyResponseSubmitView enforces
        # the single-submit semantics for non-repeatable surveys, so the
        # data layer doesn't need a partial constraint that's awkward to
        # express in Postgres (would require a FK-dependent expression).
        indexes = [
            models.Index(fields=['survey', 'user']),
        ]


class PointAward(AdoorTimestampedModel):
    SOURCE_SURVEY = 'survey'
    SOURCE_WIT_BOT_AUDIT = 'wit_bot_audit'
    SOURCE_APP_USAGE = 'app_usage'
    SOURCE_INTERVIEW_SIGNUP = 'interview_signup'
    SOURCE_RESEARCHER_ADJUSTMENT = 'researcher_adjustment'
    SOURCE_KIND_CHOICES = (
        (SOURCE_SURVEY, 'Survey response'),
        (SOURCE_WIT_BOT_AUDIT, 'Wit_bot audit pass'),
        (SOURCE_APP_USAGE, 'App usage'),
        (SOURCE_INTERVIEW_SIGNUP, 'Interview signup'),
        (SOURCE_RESEARCHER_ADJUSTMENT, 'Researcher adjustment'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='point_awards',
    )
    source_kind = models.CharField(max_length=32, choices=SOURCE_KIND_CHOICES)
    source_slug = models.CharField(max_length=64)
    scheduled_survey = models.ForeignKey(
        ScheduledSurvey,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='point_awards',
    )
    response = models.ForeignKey(
        SurveyResponse,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='point_awards',
    )
    awarded_points = models.PositiveIntegerField()
    adjusted_points = models.PositiveIntegerField(null=True, blank=True)
    note = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'response'],
                condition=models.Q(source_kind='survey', response__isnull=False),
                name='unique_award_per_user_per_response',
            ),
            models.UniqueConstraint(
                fields=['user', 'scheduled_survey'],
                condition=models.Q(
                    source_kind='survey',
                    scheduled_survey__isnull=False,
                ),
                name='unique_award_per_user_per_scheduled_survey',
            ),
            models.UniqueConstraint(
                fields=['user', 'source_kind', 'source_slug'],
                condition=models.Q(
                    response__isnull=True,
                    scheduled_survey__isnull=True,
                ),
                name='unique_award_per_user_per_non_survey_source',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'source_kind']),
            models.Index(fields=['source_kind', 'source_slug']),
        ]

    @property
    def effective_points(self):
        return self.adjusted_points if self.adjusted_points is not None else self.awarded_points

    def __str__(self):
        return f'PointAward<{self.user_id}:{self.source_kind}:{self.source_slug}>'


class SurveyAnswer(AdoorTimestampedModel):
    response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(SurveyQuestion, on_delete=models.PROTECT, related_name='answers')
    # Nullable so likert_5_na N/A picks can be stored as the NA_SENTINEL (None).
    # All other types must persist a non-null value — submission validation
    # enforces that. The DB null constraint is the storage layer for "N/A",
    # which is semantically distinct from "did not answer" (the latter would
    # be a missing SurveyAnswer row, not a present-with-null one).
    value = models.JSONField(
        null=True,
        blank=True,
        help_text=(
            'Shape depends on question.type: int for likert/single, list[int] for multi, '
            'str for free_text. NULL (NA_SENTINEL) on likert_5_na means "N/A".'
        ),
    )
    # For per-friend question types (PER_FRIEND_TYPES): the friend this row's
    # answer is *about*. NULL for every other question type. Set ON DELETE
    # SET_NULL so unfriending / account deletion doesn't erase research data;
    # the row keeps its value with a dangling target so analysis can detect
    # post-hoc unfriends.
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='survey_answers_targeting',
        help_text=(
            'Only populated for per-friend question types. NULL for all '
            'other types. Indicates the friend that the answer\'s value '
            'is about.'
        ),
    )

    class Meta:
        # Two partial constraints because PostgreSQL treats NULL as distinct
        # from NULL in unique indexes, which would otherwise let the same
        # non-per-friend question be answered twice in one response:
        #   - non per-friend (target_user IS NULL): one answer per question
        #   - per-friend (target_user IS NOT NULL): one answer per (question,
        #     target_user) pair
        constraints = [
            models.UniqueConstraint(
                fields=['response', 'question'],
                condition=models.Q(target_user__isnull=True),
                name='unique_answer_per_response_per_question',
            ),
            models.UniqueConstraint(
                fields=['response', 'question', 'target_user'],
                condition=models.Q(target_user__isnull=False),
                name='unique_answer_per_response_per_question_per_target',
            ),
        ]
        indexes = [
            # Analysis queries join SurveyAnswer ↔ FriendEvaluation on
            # (evaluator → response.user, evaluated_user → target_user).
            # An index on target_user keeps that join cheap.
            models.Index(fields=['target_user']),
        ]


class SurveyDraft(AdoorTimestampedModel):
    """Best-effort backup of an in-progress client-side survey draft.

    The frontend remains the instant save path. This row mirrors the latest
    draft only when the WebView backgrounds or the user leaves the route, so
    progress can be recovered after reinstall without adding per-question API
    traffic.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='survey_drafts',
    )
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='drafts')
    answers = models.JSONField(default=dict, blank=True)
    current_page_index = models.PositiveIntegerField(default=0)
    total_pages = models.PositiveIntegerField(default=0)
    answered_pages = models.PositiveIntegerField(default=0)
    progress_pct = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'survey'], name='unique_survey_draft_per_user'),
        ]
        indexes = [
            models.Index(fields=['user', 'survey']),
        ]

    def __str__(self):
        return f'SurveyDraft<{self.user_id}:{self.survey.slug}>'


class UserSurveyEmbeddedData(AdoorTimestampedModel):
    """Per-user key/value store populated by `embedded_data: true` questions.

    Each key is the question.slug from a prior survey response. Values are
    the raw JSON answer (matching SurveyAnswer.value semantics). Subsequent
    surveys can reference these in:
      - prompt / description / placeholder / content via {{<key>}} tokens
      - serving_condition.skip_if_user_embedded_data rules

    `source_question` is informational — exports + admin debugging only. The
    real lookup key is (user, key).
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='survey_embedded_data',
    )
    key = models.CharField(max_length=80)
    value = models.JSONField()
    source_question = models.ForeignKey(
        SurveyQuestion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'key'], name='unique_embedded_data_per_user_key'),
        ]
        indexes = [
            models.Index(fields=['user', 'key']),
        ]

    def __str__(self):
        return f'EmbeddedData<{self.user_id}:{self.key}>'
