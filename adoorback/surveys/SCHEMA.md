# Survey YAML schema

Reference for authors writing study fixtures under
`adoorback/surveys/fixtures/`.

Loaded via `python manage.py load_surveys <path>` (idempotent, upsert by
slug). All translatable fields accept `{en, ko}` mappings; `ko` is optional
on the long-form study extensions and defaults to empty string when omitted.

## Top-level structure

```yaml
- slug: <unique_survey_slug>          # required, lowercase + underscores
  type: likert_5                      # default question type for the survey
  title:
    en: "..."
    ko: "..."                         # optional
  description:                        # optional
    en: "..."
    ko: "..."
  interpretation:                     # optional, shown on results page
    en: "..."
    ko: "..."
  friend_visible: true                # default true; if false, no friend buckets
  results_hidden: false               # default false; if true, /results 404s
  result_kind: ""                     # optional survey-level renderer override
  score_formula: ""                   # optional, names a function in surveys.scoring
  score_components: []                # optional, list of question slugs to score
  tokens: {}                          # optional, {{token}} substitution map
  repeatable: false                   # default false; true allows multiple submits
  serving_condition: {}               # optional skip-rule based on embedded data
  questions: [ ... ]                  # required (or empty list for shell surveys)
```

## Question types

| `type` | Numeric range | Notes |
|---|---|---|
| `likert_3` | 1–3 | Three-point scale |
| `likert_4` | 1–4 | Four-point scale |
| `likert_5` | 1–5 | Default |
| `likert_5_na` | 1–5, plus N/A | N/A stored as `null`; excluded from scoring |
| `likert_6` | 1–6 | RSQ-Brief uses this |
| `likert_7` | 1–7 | HEXACO, Singelis, Wood AS, SHI, IUIPC |
| `single_choice` | option `value`s | One pick from `options` |
| `multi_choice` | list of `value`s | Any number of picks |
| `free_text` | string | Open response |
| `slider` | `slider_min..max` | Continuous |
| `display_only` | (no input) | Markdown banner; no value stored |

## Question fields

```yaml
- order: 1                            # required, integer
  type: likert_5                      # default = survey-level type
  slug: my_question_slug              # optional, unique within survey when set
  prompt:
    en: "..."
    ko: "..."
  description:                        # optional secondary text below prompt
    en: "..."
    ko: "..."
  placeholder:                        # free_text only — empty-input hint
    en: "..."
    ko: "..."
  low_label:  { en: "...", ko: "..." }   # likert / slider endpoints
  high_label: { en: "...", ko: "..." }
  reverse_scored: false               # likert only; inverts to (max+min-v)
  required: true                      # default true; false allows skip
  min_length: 0                       # free_text only — soft warning floor
  min_length_warning:                 # markdown shown when below min_length
    en: "..."
    ko: "..."
  na_option:                          # likert_5_na only — the 6th option's label
    en: "N/A"
    ko: "해당 없음"
  embedded_data: false                # default false; true persists answer to user store
  result_kind: ""                     # default = derived from `type`
  result_group: ""                    # questions sharing a key form one panel
  result_hidden: false                # default false; if true, no result panel
  slider_min_value: 0                 # slider only
  slider_max_value: 100               # slider only
  conditional_display: {}             # see "Conditional display" below
  content:                            # display_only only — markdown banner
    en: "..."
    ko: "..."
  options:                            # single_choice / multi_choice
    - { order: 1, value: 1, label: { en: "...", ko: "..." } }
    ...
```

## Survey-level extensions

### `tokens` — render-time variable substitution

Static string map. Substituted into prompts, descriptions, placeholders,
and `display_only.content` at render time via `{{token_name}}`.

```yaml
tokens:
  phase_label: "Phase 1"
  phase_window: "May 4 – May 17"
  phase_number: "1"
```

Resolution order at render time:
1. Survey-level `tokens`
2. User's `UserSurveyEmbeddedData` (see `embedded_data: true`)
3. Prior answers in the same submission (rare)

Unknown tokens render as the literal `{{name}}` plus a warning log.

### `embedded_data` — persist answers across surveys

Mark a question with `embedded_data: true` and a non-empty `slug`. After
submission, the answer is copied into `UserSurveyEmbeddedData` keyed by
that slug. Subsequent surveys reference it via `{{slug}}` tokens or
`serving_condition.skip_if_user_embedded_data`.

For lookup-style answers (e.g. `habit_platform: 1` → "Instagram"), a
labeling resolver in the scheduler may also store `{slug}_label` for
human-readable rendering.

### `serving_condition` — skip survey for matching users

```yaml
serving_condition:
  skip_if_user_embedded_data:
    habit_platform: "none"
```

When all key/value pairs match the user's embedded data, this survey is
not served. Default: served to all eligible users.

### `repeatable: true` — allow multiple submissions

Relaxes the per-(user, survey) uniqueness constraint. Each submission
produces an independent `SurveyResponse` row. Used for
`anytime_reflection`-style ongoing feedback.

### Survey-level `result_kind`

Overrides per-question result rendering with a single survey-level
visualization:

| `result_kind` | Renders |
|---|---|
| `scale_score_histogram` | Single summary score per response → histogram with viewer's score marked |
| `slider_histogram_paired` | Two slider questions sharing a `result_group` → 2D circumplex |

For `scale_score_histogram`:
- Default scoring: sum every `likert_*` item, with `reverse_scored: true`
  inverted via `(max + min) - v`. `likert_5_na` N/A picks are excluded
  entirely (not counted as 0).
- `score_components` (list of slugs) restricts the sum to a subset.
- `score_formula` (registry name) dispatches to a custom function.

## Conditional display

Show a question only when a prior answer satisfies a rule.

```yaml
conditional_display:
  depends_on: <slug_of_prior_question>
  show_when_value: 1                    # exact match
# or:
  show_when_value_not: 0                # not equal
# or:
  show_when_value_in: [1, 2, 3]         # any of the listed values
# or:
  show_when_value_includes: 5           # multi_choice: list contains value
```

Hidden conditional questions:
- Skip submission validation (their `required: true` doesn't apply)
- Store no value in the export

## Anchors and the `_include` directive

For shared question banks across surveys, two patterns are supported:

### Pattern A — `&anchor` / `*alias` for a single mapping

Standard YAML — works in any loader.

```yaml
- &shared_question
  order: 1
  slug: shared_q1
  type: likert_5
  prompt: { en: "...", ko: "..." }

- slug: my_survey_a
  questions:
    - *shared_question
    - { order: 2, slug: a_specific, type: free_text, ... }
```

### Pattern B — `_include: <anchor_name>` for splicing a list

Custom directive supported by `load_surveys`. Lets one anchored list be
spliced into multiple surveys' `questions:` lists.

```yaml
_shared_block: &shared_block
  - order: 1
    slug: tie_intimacy
    type: likert_5
    prompt: { en: "...", ko: "..." }
  - order: 2
    slug: tie_trust
    type: likert_5
    prompt: { en: "...", ko: "..." }

- slug: my_survey
  questions:
    - { order: 1, slug: header, type: display_only, content: { en: "..." } }
    - _include: shared_block               # splices in the two questions above
    - { order: 99, slug: my_specific_q, type: likert_5, ... }
```

Two rules:
- The anchored value must be a **list** (not a single mapping).
- The top-level entry holding the anchor (`_shared_block` above) is treated
  as anchor-only and **not persisted** as a Survey, because its slug
  starts with `_`.

### Order numbering after composition

Authors set `order` relative to their block. After `_include` expansion,
the loader **re-numbers `order` absolutely by list position** within each
survey, so anchor reuse never produces duplicate `order` values.

## Validation rules enforced by `load_surveys`

| Rule | Failure mode |
|---|---|
| Top-level must be a list of surveys | `CommandError` |
| Slugs starting with `_` are skipped | (silent skip; counted in summary) |
| Question slugs must be unique within a survey when non-empty | `CommandError` |
| `_include` must reference a known anchor whose value is a list | `CommandError` |
| Anchored sequences may not include themselves cyclically | `CommandError` |
| `display_only` questions cannot be `required: true` | model `clean()` raises `ValidationError` |
| `embedded_data: true` requires a non-empty slug | model `clean()` raises `ValidationError` |
| Slider questions need both `slider_min_value` and `slider_max_value` | model `clean()` raises `ValidationError` |

## Quick reference — when to use each feature

- Authoring a new survey from scratch → start from
  `study_2026q2.example.yaml`.
- Sharing question blocks across multiple surveys → Pattern B
  (`_include`) — lower duplication, single source of truth.
- Asking the same question in different phrasings per phase → use
  `tokens` to interpolate phase-specific labels.
- Asking the same question only of users who match a prior answer →
  `conditional_display`.
- Computing a single summary score → `result_kind: scale_score_histogram`,
  optionally with `score_formula` if the math is non-trivial.
- Allowing repeat submissions (e.g. ongoing feedback) → `repeatable: true`.
