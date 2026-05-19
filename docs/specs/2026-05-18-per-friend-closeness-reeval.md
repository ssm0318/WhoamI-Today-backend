# Per-friend closeness re-evaluation as end-of-phase surveys

**Date authored:** 2026-05-18
**Target windows:** end of Phase 1 (Day 14 = May 17), end of Phase 2 (Day 28 = May 31)
**Owner:** to be picked up in a separate session
**Status:** spec only — no implementation yet

---

## Why

The mid_study and post_study evaluations (authored in
`adoorback/surveys/fixtures/pre.yaml`) measure tie-level outcomes as
*aggregate* Likerts:

> "My interactions on WIT during {{phase_label}} made me feel closer
> to my friends."

That gives an aggregate within-WIT phase-1-vs-phase-2 comparison but
no per-friend resolution and no pre-WIT anchor.

We *do* have a per-friend closeness baseline: when a user sends or
accepts a friend request, we collect a 1–5 closeness rating via
`FriendEvaluation.closeness` (see `adoorback/account/models.py:778`).
That data is sitting unused as a research instrument.

This spec adds **two new end-of-phase surveys** that re-ask the same
1–5 closeness question per friend, then write the results to
SurveyAnswer rows. Analysis joins SurveyAnswer (per friend, per phase)
against FriendEvaluation (per friend, baseline) for the longitudinal
delta.

**These are surveys, not a custom UI flow.** They live in the surveys
fixture set. They appear in the surveys index like every other
survey. The user starts them from the index. The mid/post/feature-eval
infrastructure already handles scheduling, locking, late behavior, and
result rendering.

## What exists today

### Baseline data — already collected

`FriendEvaluation` model — `adoorback/account/models.py:778`:

| Field | Type | Notes |
|---|---|---|
| `evaluator` | FK → User | Who rated |
| `evaluated_user` | FK → User | Who was rated |
| `friend_request` | FK → FriendRequest | Tied to the request that triggered the rating |
| `context` | CharField | `'request'` or `'accept'` |
| `closeness` | IntegerField | 1–5 |
| `relationship_type` | CharField | family / close_friend / friend / acquaintance / etc. |
| `relationship_type_detail` | CharField | Free text |
| `skipped` | BooleanField | True if user dismissed the rating prompt |

UI primitive: `FriendEvaluationModal.tsx`. Copy is already
internationalized (`closeness_label`, `closeness_1`–`closeness_5` in
en + ko).

This spec does NOT modify FriendEvaluation. The baseline data stays
where it is, untouched.

### Surveys schema — what we extend

Question types today (`adoorback/surveys/models.py:27`):
`likert_3`, `likert_4`, `likert_5`, `likert_5_na`, `likert_6`,
`likert_7`, `single_choice`, `multi_choice`, `free_text`, `slider`,
`display_only`.

All are static — one row in `SurveyQuestion`, one row in
`SurveyAnswer` per (user, question). **There is no existing question
type that loops over the user's friend list and emits one Likert per
friend.** This spec adds that.

## What to build

### 1. New question type: `per_friend_likert_5`

Add to `TYPE_CHOICES` in `adoorback/surveys/models.py`:

```python
PER_FRIEND_LIKERT_5 = 'per_friend_likert_5'
TYPE_CHOICES = (
    ...existing entries...
    (PER_FRIEND_LIKERT_5, 'Likert 5-point asked once per friend'),
)
LIKERT_RANGES[PER_FRIEND_LIKERT_5] = (1, 5)  # treat as Likert for range/aggregation purposes
DEFAULT_RESULT_KIND_FOR_TYPE[PER_FRIEND_LIKERT_5] = RESULT_AGGREGATED_LIKERT
```

Semantics:
- At render time, the API expands one virtual question per friend the
  user currently has. Each virtual question is a Likert-5 with prompt
  `{{friend_name}}` substituted from the friend's display name.
- At submit time, the frontend sends a list of `{friend_id,
  closeness}` pairs. The backend writes one `SurveyAnswer` row per
  pair.
- `SurveyAnswer.value` stores the Likert value (1–5) as today.
- We need a way to associate each answer with its friend. Two options:
  - **A.** Add a `target_user_id` nullable column to `SurveyAnswer`.
    Migration: nullable add → no backfill needed (existing answers
    keep NULL) → no NOT NULL ever needed.
  - **B.** Encode `{friend_id, closeness}` as JSON in
    `SurveyAnswer.value`. `value` is already JSON-typed (check
    `SurveyAnswer` definition). No schema migration, but it makes
    per-friend aggregation queries clunkier.

  **Recommend A.** Self-joining SurveyAnswer ↔ FriendEvaluation by
  `target_user_id = evaluated_user` is far cleaner than parsing JSON.

### 2. Two new surveys in fixtures

Author in a new file `adoorback/surveys/fixtures/closeness_reeval.yaml`
(keeps the file focused; loaded after pre.yaml per the existing
`setup_survey_state` ordering convention).

```yaml
- slug: phase1_friend_closeness
  type: likert_5  # default for non-per-friend items in this survey
  title:
    en: "Rate your closeness with each friend (Phase 1)"
    ko: "친구 한 명 한 명에 대해 친밀감을 평가해 주세요 (Phase 1)"
  description:
    en: "You rated each friend on a 1–5 scale when you added them.
      Now that Phase 1 is wrapping up, please rate them again on the
      same scale. Same scale, same friends — only the timing changes."
  friend_visible: false
  results_hidden: true
  priority: 50  # below daily (80) and SOTD (similar), above weekly (40)
  questions:
    - order: 1
      slug: friend_closeness_intro
      type: display_only
      content:
        en: "**1 = Not at all close**, **5 = Extremely close**.
          You'll see one row per friend currently on your friend list.
          Skip any you'd rather not rate."

    - order: 2
      slug: friend_closeness_p1
      type: per_friend_likert_5
      prompt:
        en: "How close do you feel to {{friend_name}} right now?"
        ko: "지금 {{friend_name}} 님과 얼마나 가깝다고 느끼나요?"
      low_label:  { en: "Not at all close", ko: "전혀 가깝지 않음" }
      high_label: { en: "Extremely close",  ko: "매우 가까움" }
      reverse_scored: false
      result_hidden: true

- slug: phase2_friend_closeness
  # Identical structure to phase1, change only:
  #   - slug
  #   - title / description copy referring to Phase 2
  #   - friend_closeness_p2 instead of _p1
```

`{{friend_name}}` is a new per-question token resolved at render time
against each expanded friend (NOT a static survey-level token like
`{{phase_label}}`). The token resolver in `surveys/tokens.py` needs a
hook for per-question dynamic tokens — see step 4.

### 3. Schedule them

Add a migration `0020_seed_closeness_reeval_schedule.py` that creates
two `ScheduledSurvey` rows (idempotent on `update_or_create`):

```python
SCHEDULE = [
    ('biweekly', 4, 'phase1_friend_closeness',
     date(2026, 5, 17), date(2026, 5, 17), True),   # Day 14, allow_late
    ('biweekly', 5, 'phase2_friend_closeness',
     date(2026, 5, 31), date(2026, 5, 31), True),   # Day 28, allow_late
]
```

`allow_late=True` so the slot stays completable through end of study.

Sequence indices 4 and 5 stay clear of the existing biweekly rows (1,
2, 3 are pre/mid/post — see `0004_seed_study_schedule.py:69–73`).

**Day 14 has already passed (today is May 18).** Decide with research
lead whether to:
1. Ship now with `window_start=2026-05-17` and let `allow_late` carry
   them — participants who open it on May 18+ get the Phase 1 version
   late.
2. Move `phase1_friend_closeness` to a later date that hasn't passed.
3. Skip Phase 1 entirely and only ship `phase2_friend_closeness`.

Spec defaults to option 1 (ship with retroactive open) unless told
otherwise — the data is still valuable as a "approximately end of
Phase 1" measurement.

### 4. Backend implementation

#### a) Serializer expansion at render time

`SurveyDetailSerializer` (in `adoorback/surveys/serializers.py`)
already substitutes static tokens via `tokens.py`. Add a hook in
`to_representation` so that for each question of type
`per_friend_likert_5`:

1. Look up the requesting user's friends list (use the existing
   `User.connected_users` property in `account/models.py` —
   already excludes blocked / self).
2. For each friend, emit a virtual question dict with the same fields
   as the source question but `{{friend_name}}` substituted with
   `friend.username` (or `friend.profile.nickname` if that's the
   conventional display name — confirm with frontend).
3. Attach a synthetic `target_user_id` field on each virtual question
   so the frontend can include it in the answer payload.

The original `per_friend_likert_5` question row stays in the response
as a template (frontend skips rendering it directly — see step 5).
Alternative: omit the template from the response entirely and emit
only the expanded virtuals.

#### b) Answer write at submit time

`SurveyAnswer` model: add `target_user = models.ForeignKey(User,
null=True, blank=True, on_delete=models.SET_NULL,
related_name='survey_answers_targeting')`.

Migration: nullable column add. One-step migration is safe because
all existing rows stay NULL.

Submit serializer in `surveys/views.py` (or wherever
`SurveyResponse.create` lives):
- If the question is `per_friend_likert_5`, expect a list of
  `{target_user_id, value}` pairs. Validate each `target_user_id` is
  in the submitter's friend list (defense against tampering).
- Write one SurveyAnswer row per pair, with `target_user` and `value`
  set.
- All other question types behave exactly as today.

#### c) Token resolver

`surveys/tokens.py` currently handles static tokens from the
survey-level `tokens` block. Add a per-question dynamic-token path:

```python
PER_QUESTION_TOKENS = {'friend_name'}

def apply_to_question_for_friend(question_dict, friend):
    """Substitute per-friend tokens in a question's text fields."""
    tokens = {'friend_name': _display_name(friend)}
    return apply_to_question(question_dict, tokens)
```

`_display_name(friend)` returns nickname if set, else username.
Confirm with the frontend which they want.

#### d) Aggregation / results

`phase1_friend_closeness` and `phase2_friend_closeness` have
`results_hidden: true` so participants don't see aggregate result
panels. No new aggregation strategy needed.

For analysis: a one-shot management command
`python manage.py dump_friend_closeness_panel` joins SurveyAnswer
(per phase, per target_user) with FriendEvaluation (baseline) and
emits a CSV with columns `evaluator_id, evaluated_user_id,
baseline_closeness, baseline_at, phase1_closeness, phase2_closeness`.
Build this in the same session as the surveys themselves — without it
there's no way to verify the join works.

### 5. Frontend implementation

`SurveyAnswerForm.tsx` today is **one-question-per-screen** with
`index` / `setIndex` pagination (see lines 138, 178, 218 — `Next` /
`Back` buttons move through one question at a time). The
`per_friend_likert_5` question type cannot use that pattern — the
user explicitly asked for all per-friend rows on a single scrollable
page. Two changes:

#### a) Single-page rendering for `per_friend_likert_5`

When the dispatcher hits a `per_friend_likert_5` question, render
**all expanded virtual questions on one screen** as a vertical
scrollable list. Each row is `[friend_name as link] [Likert 1–5
picker]`. The `Next` button advances past the entire block once every
row has a value (or the user explicitly chooses to skip remaining
rows — TBD with research lead).

Other question types in the same survey (e.g. the `display_only`
intro before the per-friend block) keep the one-per-screen behavior.
So this survey's flow looks like:

```
Page 1: display_only intro (one screen, Next button)
Page 2: per_friend_likert_5 expanded (N rows on one screen, scroll, Next button)
Page 3 (if added later): any subsequent question, back to one-per-screen
```

Implementation: a new branch in the question renderer that loops the
expanded virtual questions instead of indexing into them. Submit
state for the block is a `Map<target_user_id, value>` that the
dispatcher serializes into the answer payload when the user advances.

#### b) Clickable friend name → profile

Each row's friend name renders as a `<Link to={`/users/${username}`}>`
(matching the convention used in `FriendsTimelineFeed.tsx:204`,
`FavoriteFriendItem.tsx:28`, `FriendProfileAccordionItem.tsx:130`).

**State preservation when the user navigates away:** tapping a
profile link unmounts `SurveyAnswerForm`. Any unsaved Likert values
in local component state would be lost on `Back` button return. Two
mitigations, pick one:

- **Autosave to draft.** After each Likert selection, POST to a new
  `/api/surveys/responses/draft/` endpoint that creates / updates a
  draft response. On `SurveyAnswerForm` mount, hydrate state from
  the draft. Clean approach; requires backend support.
- **Survive via URL state or session storage.** Cheaper: stash
  `answers` in `sessionStorage` keyed by survey slug + user id;
  rehydrate on mount. No backend changes. Fragile if the user closes
  the tab.

Recommend **autosave to draft** if a draft endpoint exists or is
cheap to add — drafts are useful for long surveys generally. Confirm
with backend before starting. If draft endpoint doesn't exist and
we're not building one this session, fall back to sessionStorage and
flag in the post-merge TODO list.

i18n strings to add (en + ko):
- `friend_closeness_p1_title` / `friend_closeness_p2_title`
- `friend_closeness_p1_description` / `friend_closeness_p2_description`
- `friend_closeness_intro_content`
- `friend_closeness_prompt_template` (the `{{friend_name}}` source)
- `friend_closeness_view_profile_hint` (optional helper text near
  the first row: "tap a name to view their profile")
- Reuse existing `closeness_1`–`closeness_5` labels — already in
  `src/i18n/locales/{en,ko}/translation.json:1042+`.

## Verification

Before declaring done:

1. **Schema:** `python manage.py makemigrations --check` clean after
   the SurveyAnswer.target_user migration.
2. **Question type registered:** `python manage.py shell` →
   `SurveyQuestion.objects.create(type='per_friend_likert_5', ...)`
   should not raise a choices ValidationError.
3. **Serializer expansion:**
   - Create test user with 3 friends.
   - Hit `GET /api/surveys/phase1_friend_closeness/` as that user.
   - Verify the response contains exactly 3 expanded virtual questions
     (one per friend), each with `target_user_id` set, each with
     `{{friend_name}}` substituted in `prompt_en` and `prompt_ko`.
   - Verify a user with 0 friends still gets a valid (empty)
     question list and the survey is submittable as 0-item.
4. **Answer write:**
   - Submit with `[{target_user_id: X, value: 4}, {target_user_id: Y,
     value: 2}, {target_user_id: Z, value: 5}]`.
   - Query DB: 3 SurveyAnswer rows for that response, each with
     `target_user_id` populated correctly.
5. **Tamper protection:**
   - Submit with `target_user_id` of a non-friend → 400 error.
6. **Analysis dump:**
   - Run `python manage.py dump_friend_closeness_panel
     --user <test-user>`.
   - Confirm CSV has expected rows joining baseline + phase1 + phase2
     when all three exist; confirm the dump correctly handles missing
     rows on any axis (friend added after baseline window, friend
     skipped at p1, etc.).
7. **End-to-end:**
   - Open the survey on the surveys index in dev.
   - Complete it.
   - Reload — survey appears as completed.
   - Hit `late_but_accepted` path after window close: still
     submittable.

## Open questions

1. **Display name source.** `friend.username` (Adoor handle) or
   `friend.profile.nickname`? Frontend convention will tell us — pick
   whichever is shown on the friend list UI today so the survey
   matches.
2. **Privacy preview.** Should we show the user how many friends
   will appear in the list before they open the survey? "Rate 12
   friends" vs "Rate your friends" — the former sets expectations,
   the latter is friendlier.
3. **Maximum friends per response.** A user with 200 friends gets a
   200-item Likert form. Cap at top-N most-recently-interacted? Or
   trust that participants self-throttle?
4. **Reverse direction.** This rates how I feel about my friend. Do
   we also want the friend to rate me? Symmetric dyadic data would be
   ideal for tie-strength papers. Not in scope for this spec — flag
   as future work.
5. **Anchor display.** Should the per-friend row show "you rated
   them 3/5 at baseline" alongside the 1–5 picker? Reduces drift in
   scale interpretation but primes the response. Recommend showing it
   by default; confirm with research lead.
6. **What if friend list changes between survey open and submit?**
   - User adds a friend after opening but before submitting → friend
     doesn't appear in this submission. Acceptable.
   - User removes a friend after opening but before submitting →
     answer for that friend rejected on submit. Need a clear error
     message in the frontend.

7. **Profile navigation round-trip.** Tap username → go to profile →
   `Back` → return to survey. What's the expected behavior?
   - **Answers preserved:** required, otherwise the feature is a
     trap. See the autosave-to-draft vs sessionStorage decision in
     Section 5b.
   - **Scroll position preserved:** ideally yes — if the user tapped
     friend #14 to check who they are, returning should put them
     back at friend #14, not at the top of the list. Standard
     browser back behavior may or may not handle this depending on
     whether the survey route re-mounts.
   - **Profile page itself opens in-place vs new tab?** Spec assumes
     in-place navigation matching the existing `navigate('/users/...')`
     convention used throughout the app. Could be revisited as a
     `target='_blank'` link if state preservation turns out hard.

8. **Likert layout on small screens.** A row with [Link to friend] +
   [5 Likert dots] needs to fit on 320px (iPhone SE 1st gen) per
   project conventions. Probably stacks: name on top, dots below.
   Confirm at design time.

## What NOT to do

- **Don't modify FriendEvaluation.** No new fields, no new
  constraints, no migrations on that table. The baseline data is
  fine as-is; this spec only adds new SurveyAnswer rows.
- **Don't build a custom route or paginated UI.** The whole point of
  authoring this as surveys is to reuse the existing surveys index +
  SurveyAnswerForm machinery. Building a parallel flow defeats the
  purpose.
- **Don't write to FriendEvaluation from the survey submission
  pipeline.** Keep the two storage layers separate. Baseline stays in
  FriendEvaluation; longitudinal re-eval data stays in SurveyAnswer.
  The analysis-time join is the source of truth.
- **Don't make the per-friend question type generic to "any list of
  users".** Scope it to friends for now. If we later want
  `per_close_friend_likert_5` or `per_blocked_user_likert_5` those
  become separate types.
- **Don't ship without the analysis dump command.** A survey that
  collects per-friend data but has no validated read path is
  unfalsifiable until paper-writing time. Build the CSV dump in the
  same PR so you know the join works.
- **Don't auto-prompt re-eval at app open.** Surface it through the
  surveys index. Notifications can go out on day 14 / day 28
  morning, but the trigger to take the survey is user-initiated.

## Files likely to touch

| File | Change |
|---|---|
| `adoorback/surveys/models.py` | Add `PER_FRIEND_LIKERT_5` constant + TYPE_CHOICES entry + LIKERT_RANGES + DEFAULT_RESULT_KIND_FOR_TYPE |
| `adoorback/surveys/models.py` | Add `target_user` FK to `SurveyAnswer` |
| `adoorback/surveys/migrations/0020_per_friend_likert_5_schema.py` | One-step nullable add on SurveyAnswer.target_user |
| `adoorback/surveys/fixtures/closeness_reeval.yaml` | New file: `phase1_friend_closeness` + `phase2_friend_closeness` surveys |
| `adoorback/surveys/management/commands/setup_survey_state.py` | Add `closeness_reeval.yaml` to `LONG_FORM_FIXTURES` (load order: after `pre.yaml`) |
| `adoorback/surveys/migrations/0021_seed_closeness_reeval_schedule.py` | Schedule biweekly #4 + #5 |
| `adoorback/surveys/serializers.py` | `SurveyDetailSerializer.to_representation`: expand `per_friend_likert_5` questions per friend |
| `adoorback/surveys/serializers.py` | Submit serializer: accept list of `{target_user_id, value}` for `per_friend_likert_5`; validate friend-list membership; write one SurveyAnswer per pair |
| `adoorback/surveys/tokens.py` | Add per-question dynamic-token path for `friend_name` |
| `adoorback/surveys/management/commands/dump_friend_closeness_panel.py` | New: analysis CSV dump joining FriendEvaluation + SurveyAnswer |
| `WhoamI-Today-frontend/src/components/survey/SurveyAnswerForm.tsx` | Add `per_friend_likert_5` renderer; single-page list of expanded virtual questions; package answers as `[{target_user_id, value}]`; bypass the index/setIndex paging for this question type only |
| `WhoamI-Today-frontend/src/components/survey/<new>/PerFriendLikertBlock.tsx` | New: vertical scrollable list of `[Link to /users/${username}] [Likert 1–5]` rows |
| `WhoamI-Today-frontend/src/components/survey/<new>/PerFriendLikertRow.tsx` | New: single row primitive |
| `WhoamI-Today-frontend/src/i18n/locales/{en,ko}/translation.json` | Survey copy + intro content + prompt template + view-profile hint |
| Draft persistence (one of, per Section 5b decision): |  |
| `adoorback/surveys/views.py` + new endpoint | `/api/surveys/responses/draft/` — POST creates / updates a draft response keyed by (user, survey) |
| or `WhoamI-Today-frontend/src/components/survey/useSurveyDraft.ts` | sessionStorage-based fallback if backend draft endpoint not built this session |

## Migration order summary

```
0019_sotd_allow_late_true.py                          (current head)
0020_per_friend_likert_5_schema.py                    (add target_user FK, add type to choices)
0021_seed_closeness_reeval_schedule.py                (schedule phase1 + phase2)
```

Run `python manage.py setup_survey_state` after deploy to load
`closeness_reeval.yaml`.

## Dependencies

- This spec assumes `SurveyAnswer.value` is JSON-typed (Likert ints
  fit fine either way). Verify the column type before adding
  `target_user`.
- This spec assumes `User.connected_users` returns the correct friend
  list for survey purposes (excludes blocked, self). Verify by reading
  `account/models.py`.
- The `display_name` decision affects copy in two places (survey
  prompt + i18n bundle). Lock the decision before writing code.
