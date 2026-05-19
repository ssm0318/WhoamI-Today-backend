# Participant points & reimbursement — design

**Date authored:** 2026-05-18
**Last reviewed against code:** 2026-05-19
**Status:** design only — sidebar placeholder exists; points system not implemented
**Owner:** to be picked up in a separate session

---

## Why

Participants currently have no in-app signal about their reimbursement
progress. Researchers know which surveys carry the most analytic
weight (mid/post, feature_eval, goal_comparison) and which compliance
behaviors are required (notifications on, friends added, posts +
comments made, all features tried), but participants only see "this
survey is available now." That asymmetry leads to:

- **Important surveys getting completed late or skipped** because they
  look the same as the daily diary in the index.
- **No incentive structure** beyond a flat reimbursement at study end,
  which won't surface mid-study which participants are at risk of
  under-rewarded.
- **No standing channel** for the researcher to explain *why* a
  particular response was downgraded at audit time. Today an audit
  happens silently between the team and the participant's payment.

The points system makes the incentive structure visible: every survey
shows what it's worth, prereq chains are visible, the running total is
on the sidebar, and the dedicated `/reimbursement` page explains the
points → money mapping plus the data-quality audit policy.

## Current-code alignment notes

This spec was rechecked against the current `release/final-research`
codebase on 2026-05-19. The implementation below intentionally differs
from the first draft in these ways:

- Survey presentation is now schedule-driven. The backend returns
  `ScheduledSurvey` rows, with `sidebar_order`, `target_user_group`,
  `window_start/window_end`, `allow_late`, drafts, and
  `results_unlocked`. The frontend combines `available_now` and
  `late_but_accepted` into one "To-do" section rather than rendering
  three separate buckets.
- `SurveyResponse` is not tied to a `ScheduledSurvey` row. Because the
  same `Survey` can have multiple scheduled opportunities (for example
  `daily_base` over many study days, and `feature_eval_w` for different
  user groups), point awards must record the resolved schedule row on
  the ledger entry.
- Editable and repeatable surveys already have special submit
  semantics. `feature_eval_w` and `goal_comparison_p1/p2` edit an
  existing response; `anytime_reflection` can create multiple response
  rows. Points must be awarded once per scheduled opportunity, not once
  per arbitrary response row.
- There are multiple participant entry points: `/surveys`,
  `/share`'s Survey-of-the-Day card, `/surveys/past` daily archive rows,
  survey result edit links, and the existing `/reimbursement`
  placeholder page. Points copy and cache invalidation need to account
  for these surfaces.
- The existing token-prereq redirect/hide behavior is a content-safety
  mechanism. `point_prereq_slug` is separate and must not reuse that
  filtering path; point-locked surveys remain answerable.

## Anti-gaming guardrails

Three constraints anchor the rest of the design:

1. **Don't reward fake data.** A participant who clicks through a
   survey without reading should not earn full points just because they
   submitted.
2. **Don't reward skipping.** A participant who answers only the
   required minimum should not earn the same as one who engages with
   the optional / freetext follow-ups.
3. **Make it clear that displayed points are provisional.** Final
   reimbursement happens after a data-quality audit at study end.
   Bad-faith responses can be downgraded.

The mechanism: first awarded submit for a scheduled survey opportunity
credits the survey's full `point_value` provisionally. A `PointAward`
ledger row carries the resolved `ScheduledSurvey`, the `SurveyResponse`,
and an `adjusted_points` override that the researcher can fill in at
audit time (e.g., 0 for a garbage response). The UI shows the adjusted
value when present, with the original struck through for transparency.
Every points display carries a disclaimer linking to `/reimbursement`
for the full policy.

## What earns points

| Source kind        | How it's awarded                                                | Slug                |
|--------------------|-----------------------------------------------------------------|---------------------|
| Survey             | Submit-view helper on first awarded scheduled opportunity       | `<survey.slug>`     |
| Wit_bot audit      | Researcher / wit_bot manual credit for Phase 1                  | `wit_bot_audit_phase_1` |
| Wit_bot audit      | Researcher / wit_bot manual credit for Phase 2                  | `wit_bot_audit_phase_2` |
| Interview signup   | Researcher manual credit                                        | `interview_signup`  |

**Per-survey point values are variable** and declared per-survey in
YAML. The researcher tunes them as incentives — end-of-phase and
feature-evaluation surveys carry the largest values; SOTD entries vary
by analytic priority; daily entries carry small per-day amounts so the
daily habit is rewarded without overshadowing higher-stakes endpoints.

The award unit for surveys is the **scheduled opportunity**, resolved
at submit time from the current `ScheduledSurvey` row. This matters
because a survey slug is no longer a unique participant opportunity:

- `daily_base` can be scheduled repeatedly across the study window.
- `feature_eval_w` is the same survey content scheduled at different
  times for W-first and Q-first participants.
- Repeatable surveys can create more than one `SurveyResponse` row.

In v1, one scheduled opportunity can produce at most one survey
`PointAward` per user. Repeatable follow-up submissions do not create
additional point awards unless a future version adds an explicit
per-repeat point policy.

**Wit_bot audit criteria (researcher checks at audit time):**

- Push notifications enabled for the study window
- Has added at least N friends (N TBD; matches existing wit_bot copy
  threshold)
- Has posted and commented (engagement signal)
- Has tried each of the in-app features (browse mode, check-ins,
  reactions, etc.)

v1 awards this as two phase-specific line items on the reimbursement
page. The displayed version depends on the participant's group:
`group_w_first` earns Phase 1 for Ver.W and Phase 2 for Ver.Q;
`group_q_first` earns Phase 1 for Ver.Q and Phase 2 for Ver.W.
Per-criterion automation can be layered in later without changing the
participant-visible UX.

**Interview signup** is a single discrete event keyed by the user
clicking through the signup flow. v1 credits manually via admin
action.

## Prerequisite mechanic

A survey can declare a prereq via `point_prereq_slug`. When the prereq
is not yet completed by the viewer:

- The survey is **still answerable** — the prereq is a *points* gate,
  not a *content* gate. (The prereq-token-redirect mechanism from
  commit `8b93bec` is a separate, *content* gate for surveys with
  unresolved tokens; the two systems coexist.)
- The badge renders in the locked style (lock icon + grayed value).
- Tapping the badge opens a modal explaining the prereq, naming the
  gating survey, and offering a "Do prereq now" action.
- Submitting the survey with prereq unmet still creates a `PointAward`
  row but with `awarded_points = 0` and a note explaining why. Once
  the prereq is later completed, the row stays at 0 — there is no
  retroactive backfill in v1. (Rationale: incentive to do the prereq
  *first*, not as a side effect.)

Prereq completion is checked by `SurveyResponse` existence for
`point_prereq_slug` and the same user. It is independent of whether the
prereq survey is currently visible in the index.

## Partial credit

Surveys credit the **full** `point_value` on submit. There is no
per-question proportional model in v1. Anti-gaming is enforced through
the researcher audit, not through automatic skip-detection.

Editable surveys (`feature_eval_w`, `goal_comparison_p1/p2`) credit on
**first** awarded submit for that user's scheduled opportunity only.
Subsequent edits update the `SurveyResponse` answers and `submitted_at`
but do not change the existing `PointAward`. The participant is
informed of this in the survey description and on the reimbursement
policy page so they do not try to game it by toggling answers.

Surveys with `point_value = 0` do not create participant-visible award
rows. The only zero-point survey award row v1 creates is a nonzero
survey submitted while its point prereq was unmet; that row is kept so
the reimbursement page can explain why the participant received 0 for
that attempt.

## Data model

### Survey (existing model — two new fields)

```python
# adoorback/surveys/models.py
class Survey(...):
    # ... existing fields ...

    point_value = models.PositiveIntegerField(
        default=0,
        help_text=(
            'Provisional max points credited on first submit. 0 = no '
            'points (use for display-only fixtures, etc.). Researcher '
            'audit at study end may downgrade individual awards.'
        ),
    )
    point_prereq_slug = models.CharField(
        max_length=64, blank=True, default='',
        help_text=(
            'Slug of a survey that must be completed before this one '
            'credits its full point_value. Blank = no prereq. Submission '
            'with prereq unmet still creates a PointAward row but with '
            'awarded_points=0 and an explanatory note.'
        ),
    )
```

These are authored in YAML alongside everything else:

```yaml
- slug: mid_study_w
  point_value: 50
  point_prereq_slug: ""
  # ... rest of survey ...

- slug: sotd_d15_shi
  point_value: 10
  point_prereq_slug: pre_study_catchup
  # ...
```

### PointAward (new model)

Lives in `adoorback/surveys/models.py` alongside Survey rather than in
a new app — every award traces back to a survey or a survey-adjacent
research event, and keeping it co-located simplifies the join queries
the reimbursement page does.

```python
# adoorback/surveys/models.py
class PointAward(AdoorTimestampedModel):
    SOURCE_KIND_CHOICES = (
        ('survey', 'Survey response'),
        ('wit_bot_audit', 'Wit_bot audit pass'),
        ('interview_signup', 'Interview signup'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name='point_awards')
    source_kind = models.CharField(max_length=32, choices=SOURCE_KIND_CHOICES)
    source_slug = models.CharField(max_length=64)

    # Only set for source_kind='survey'. The resolved ScheduledSurvey row
    # is the award unit. ON DELETE SET_NULL preserves the audit trail if
    # schedule cleanup happens later.
    scheduled_survey = models.ForeignKey(
        ScheduledSurvey, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='point_awards',
    )
    # Also only set for source_kind='survey'. ON DELETE SET_NULL so a
    # SurveyResponse cleanup doesn't erase the audit trail.
    response = models.ForeignKey(
        SurveyResponse, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='point_awards',
    )
    awarded_points = models.PositiveIntegerField()
    # Researcher adjustment at audit time. NULL = no adjustment, use
    # awarded_points as final. Non-null = use this value as final;
    # show the original (awarded_points) struck through for
    # transparency.
    adjusted_points = models.PositiveIntegerField(null=True, blank=True)
    note = models.TextField(blank=True, default='')

    class Meta:
        constraints = [
            # One survey-source award per (user, response) — captures the
            # normal non-repeatable / editable "credit on first submit"
            # rule.
            models.UniqueConstraint(
                fields=['user', 'response'],
                condition=models.Q(source_kind='survey', response__isnull=False),
                name='unique_award_per_user_per_response',
            ),
            # One survey-source award per (user, scheduled opportunity).
            # This prevents repeatable submissions from earning duplicate
            # points for the same schedule row.
            models.UniqueConstraint(
                fields=['user', 'scheduled_survey'],
                condition=models.Q(
                    source_kind='survey',
                    scheduled_survey__isnull=False,
                ),
                name='unique_award_per_user_per_scheduled_survey',
            ),
            # One non-survey award per (user, source_kind, source_slug).
            # Researcher can re-credit by editing the row (adjusted_points),
            # not by creating a second one.
            models.UniqueConstraint(
                fields=['user', 'source_kind', 'source_slug'],
                condition=models.Q(
                    response__isnull=True,
                    scheduled_survey__isnull=True,
                ),
                name='unique_award_per_user_per_non_survey_source',
            ),
        ]
```

### Award triggers

- **Survey:** call a small award helper from
  `SurveyResponseSubmitView.post()` inside the same transaction that
  creates or edits the `SurveyResponse`. Do **not** use a bare
  `post_save` signal for v1: the submit view already knows whether the
  operation is a repeatable create, editable update, duplicate submit,
  or expired-window rejection.
  - Resolve the current `ScheduledSurvey` context using the same window
    and routing rules as the submit view: visible to the user, currently
    open or late-accepted, not retired, and routed by
    `target_user_group` / `_w` / `_q`.
  - If `point_value = 0`, return without creating a row.
  - If `point_prereq_slug` is blank or the user already has a
    `SurveyResponse` for that prereq survey, create/get the award with
    `awarded_points = survey.point_value`.
  - If the point prereq is unmet, create/get the award with
    `awarded_points = 0` and a note such as
    `"Prereq pre_study_catchup not completed at submit time."`
  - Use `get_or_create` keyed primarily on `(user, scheduled_survey)`
    for scheduled survey rows, with `(user, response)` as the fallback
    for any unscheduled survey response. This keeps editable resubmits
    and repeatable same-opportunity submissions idempotent.
- **Wit_bot audit:** Django admin action on a custom list-page button,
  or `python manage.py credit_wit_bot_audit --user <username> --phase <1|2> --pts <n>`
  management command. Idempotent via `get_or_create` on (user,
  source_kind='wit_bot_audit', source_slug=`wit_bot_audit_phase_1` or
  `wit_bot_audit_phase_2`).
- **Interview signup:** Same pattern as wit_bot audit. Admin action
  or management command.

### Conversion rate

A single per-study constant lives in `surveys/reimbursement_config.py`
(or settings) — `POINTS_PER_DOLLAR = 8` (giving `1 pt ≈ $0.125`). The
participant page reads this constant. v1 does not store per-user
rates.

## API

### GET /api/surveys/reimbursement/

Auth required. Returns the requesting user's full reimbursement state:
In `surveys/urls.py`, this route must be registered before
`path('<slug:slug>/')` so `reimbursement` is not interpreted as a
survey slug.

```json
{
  "provisional_total": 145,
  "adjusted_total": 145,
  "available_max": 800,
  "dollar_estimate_cents": 1800,
  "points_per_dollar": 8,
  "awards": [
    {
      "source_kind": "survey",
      "source_slug": "mid_study_w",
      "scheduled_survey_id": 42,
      "title_en": "Looking back: Phase 1",
      "cadence": "biweekly",
      "window_start": "2026-05-18",
      "window_end": "2026-05-19",
      "awarded_points": 50,
      "adjusted_points": null,
      "effective_points": 50,
      "note": "",
      "submitted_at": "2026-05-17T10:23:00Z"
    },
    {
      "source_kind": "survey",
      "source_slug": "sotd_d15_shi",
      "scheduled_survey_id": 115,
      "title_en": "How automatic is Instagram?",
      "cadence": "daily",
      "window_start": "2026-05-18",
      "window_end": "2026-05-18",
      "awarded_points": 0,
      "adjusted_points": null,
      "effective_points": 0,
      "note": "Prereq pre_study_catchup not completed at submit time.",
      "submitted_at": "2026-05-18T09:00:00Z"
    },
    {
      "source_kind": "wit_bot_audit",
      "source_slug": "wit_bot_audit_phase_1",
      "title_en": "Wit_bot audit pass - Phase 1 (Ver.W)",
      "awarded_points": 10,
      "adjusted_points": null,
      "effective_points": 10,
      "note": "",
      "submitted_at": "2026-05-12T15:00:00Z"
    }
  ],
  "pending_prereqs": [
    {
      "survey_slug": "sotd_d15_shi",
      "scheduled_survey_id": 115,
      "title_en": "How automatic is Instagram?",
      "potential_points": 10,
      "prereq_slug": "pre_study_catchup",
      "prereq_title_en": "One quick question we missed at the start"
    }
  ]
}
```

`available_max` is the sum of `point_value` over every visible
scheduled opportunity for the viewer plus the configured wit_bot +
interview signup max values. It should be schedule-row based, not
unique-survey based:

- Include only rows that route to this viewer (`target_user_group`,
  `_w` / `_q`, retired survey filtering).
- Count repeated scheduled opportunities separately when they are real
  participant opportunities.
- Count repeatable surveys at most once per scheduled row in v1.
- Do not subtract a row just because its point prereq is currently
  unmet; the denominator represents what was available if done in the
  intended order.

This gives the "X / 800 pts" denominator on the summary card while
matching the current schedule model.

### Existing endpoints get point state

`GET /api/surveys/index/` entry — add point state at the scheduled
entry level:

```json
{
  "point_value": 10,
  "point_locked_by_prereq_slug": null,
  "point_locked_by_prereq_title_en": null,
  "point_locked_by_prereq_title_ko": null,
  "point_award": {
    "awarded_points": 10,
    "adjusted_points": null,
    "effective_points": 10,
    "note": ""
  }
}
```

`point_award` is `null` when no award row exists yet. The prereq fields
are `null` when there is no prereq or when the prereq is already met for
the viewer.

`GET /api/surveys/<slug>/` survey — add `point_value`,
`point_prereq_slug`, `point_locked_by_prereq_slug`,
`point_locked_by_prereq_title_en`, `point_locked_by_prereq_title_ko`,
and `point_award`. `GET /api/surveys/today/` inherits this because it
uses `SurveyDetailSerializer`.

`POST /api/surveys/<slug>/responses/` remains backwards compatible by
returning the existing `id`, but may also include `point_award` so the
frontend can show immediate feedback and refresh cached reimbursement
state without a second blocking request:

```json
{
  "id": 1234,
  "point_award": {
    "awarded_points": 10,
    "adjusted_points": null,
    "effective_points": 10,
    "note": ""
  }
}
```

## Frontend

### SurveysIndex (`/surveys`)

The current page renders:

- a `SubHeader`
- optional pause banner
- one combined **To-do** section made from `available_now +
  late_but_accepted`
- a **Completed** section
- row-header badges for high priority, deadline, late state, and draft
  progress

Points should fit this structure rather than reintroducing separate
available/late/completed sections.

Top of the page gets a compact provisional-total summary band, below
the pause banner when present, showing "Provisional points so far:
145 pts" with a "See how this works ›" link to `/reimbursement`.

Per-row badge rendering:

| State                  | Badge style                                                         |
|------------------------|---------------------------------------------------------------------|
| Earnable, no prereq    | Purple chip "+10 pts" (matches existing chip style, F3E8FF / 8700FF)|
| Earnable, prereq unmet | Gray chip with dashed border and lock icon "🔒 +10 pts" (Style A)   |
| Completed              | Green chip "✓ +3 pts"                                               |
| Completed, downgraded  | Green chip "+1 pts" with original 3 struck through                  |

Placement:

- Render the points chip inside the existing `RowHeader`, after the
  survey title and before deadline/draft chips.
- Once real points exist, suppress the hardcoded red "High priority"
  badge for rows with `point_value > 0`; the points chip becomes the
  incentive signal. Keep the high-priority badge only as a fallback for
  rows that still have no point value during rollout.
- Completed rows are currently non-clickable cards with an optional
  Results button. Their points chip should render on the card even when
  no Results button is shown.

Tapping a locked badge opens a modal (reusing `CommonDialog` for
consistency) that:

- Names the gating survey
- States "You'll earn N pts when you complete `<gating survey>` first"
- Notes that submitting this survey now credits 0 pts
- Offers a primary "Do prereq now" button (navigates to the prereq's
  `/surveys/<slug>/answer` page) + a secondary "Close" button

### Other survey entry points

Points must appear anywhere a participant can start or review a
rewarded survey:

- `/share` `SurveyOfTheDay` card: show the same points chip near the
  survey title. If the survey is answered, show earned/adjusted state.
  If the card is a token-prereq redirect, use the returned survey's own
  point state; do not conflate token prereqs with `point_prereq_slug`.
- `/surveys/past` daily archive: rows that are answerable late should
  show the earnable/locked chip; answered rows should show earned or
  adjusted chip.
- `/surveys/<slug>/done`: if `POST /responses/` returned a
  `point_award`, show a small provisional-credit line on the thank-you
  card. This is informational only; the reimbursement page remains the
  source of truth.
- `/surveys/<slug>/results` edit links for editable surveys should not
  imply additional points. Copy should say edits do not create another
  point award.

### Sidebar (`SideMenu.tsx`)

The sidebar entry already exists:

```ts
{ key: 'reimbursement', emoji: '💰', path: '/reimbursement' }
```

Keep that entry and add the Style B treatment — label + small purple
chip on the right showing the running provisional total ("145 pts").
The chip matches the canonical chip style (`#F3E8FF` bg, `#8700FF`
text, 8px radius). The total is fetched once when the sidebar opens
via `/api/surveys/reimbursement/`, or from a zustand/SWR cache shared
with the reimbursement page. When the user has 0 points, the chip is
omitted.

Do not remove the existing survey due-count chip. The sidebar can show
the survey due-count chip on the Surveys row and the point-total chip
on the Reimbursement row.

### Reimbursement page (`/reimbursement`)

The route, header integration, and placeholder page already exist.
Replace the placeholder content with the full reimbursement page. It
reads `GET /api/surveys/reimbursement/`. Layout:

1. **Top summary card** (purple-tinted) with "X / Y pts" big number,
   "~$N estimated reimbursement", and the audit disclaimer ("Points
   are provisional. Your final reimbursement depends on a data-quality
   review at study end. Responses filled in bad faith may be
   downgraded.").
2. **"What earns points"** section — short legend explaining the
   point-value tiers (high = endpoint surveys, etc.) and the conversion
   rate.
3. **"Your awards"** section — grouped by source kind:
   - SURVEYS — table of survey title × points (with downgrade
     strikethrough if applicable)
   - OTHER ACTIVITIES — wit_bot audit + interview signup rows
4. **"Pending"** section (only when non-empty) — surveys with unmet
   prereqs, showing "+N pts available — complete `<gating survey>`
   first."

### i18n

Current translations already have `home.header.side_menu.reimbursement`
and `header.reimbursement`. Add a new `reimbursement.*` namespace
(en + ko) for the page and point UI:

- `summary_title`, `provisional_total_label`, `dollar_estimate_label`
- `audit_disclaimer_short` (for index summary card) and
  `audit_disclaimer_long` (for the dedicated page)
- `locked_badge_modal_title`, `locked_badge_modal_body`,
  `locked_badge_do_prereq_button`, `locked_badge_close_button`
- `section_surveys`, `section_other_activities`, `section_pending`
- `wit_bot_audit_label`, `interview_signup_label`
- `downgraded_label` (small caption on adjusted rows)
- `points_badge_earnable`, `points_badge_locked`,
  `points_badge_earned`, `points_badge_adjusted`
- `done_points_awarded`, `done_points_locked`

## Verification

Before declaring v1 done:

1. **Schema:** from `WhoamI-Today-backend/adoorback`, run
   `DB_HOST=localhost python manage.py makemigrations --check` after
   adding `point_value` + `point_prereq_slug` to Survey and adding the
   `PointAward` model with `scheduled_survey`.
2. **Award trigger:**
   - First survey submit creates one `PointAward` row with the survey's
     full `point_value` and the resolved `scheduled_survey`.
   - Second (edit) submit on an editable survey does NOT create a new
     row.
   - Second repeatable submit against the same scheduled opportunity
     does NOT create a second point award.
   - Submit with unmet prereq creates a row with `awarded_points=0`
     and a clear note.
   - Submit with `point_value=0` creates no participant-visible award.
3. **API:** `GET /api/surveys/reimbursement/` returns the expected
   shape; `provisional_total` matches manual `SUM(awarded_points)`
   from the shell; `adjusted_total` reflects any test downgrade;
   `available_max` counts scheduled opportunities, not unique survey
   slugs.
4. **Survey index payload:** entries carry `point_value` and
   `point_locked_by_prereq_slug` correctly per viewer, plus
   `point_award` when the current user has an award for that scheduled
   row.
5. **Frontend e2e:**
   - Earnable badges render purple on currently-available surveys.
   - Locked badges render gray-with-lock on prereq-blocked surveys.
   - Tapping a locked badge opens the modal naming the right gating
     survey.
   - Sidebar chip shows the right total; updates after a submit.
   - `/reimbursement` page loads, groups awards correctly, shows
     dollar estimate, shows disclaimer.
   - `/share` Survey-of-the-Day card shows point state and still chains
     to the next SOTD after submit.
   - `/surveys/past` rows show point state for answerable/answered
     daily rows.
6. **Mobile-responsive:** all surfaces verified at 320px, 375px, and
   393px.
7. **Researcher admin:** Django admin allows editing
   `PointAward.adjusted_points` + `note`; the page reflects the
   downgraded total on next load.
8. **Build/check commands:**
   - Backend: `DB_HOST=localhost python manage.py check`
   - Backend: `DB_HOST=localhost python manage.py makemigrations --check`
   - Frontend: `source ~/.nvm/nvm.sh && nvm use 18 && npx craco build`
   - Frontend dev server: start/watch the app, load the relevant pages,
     and confirm there is no webpack overlay.

## Open decisions deferred to next session

- **Wit_bot per-criterion automation** — for v1 the audit is a single
  manual line item. Automating "notifications enabled," "≥N friends,"
  etc. is a follow-up that doesn't change the participant-visible
  flow.
- **Push notifications about points earned** — should the participant
  get a push when a survey credit lands? Probably yes for high-value
  surveys (mid/post) but the UX hasn't been designed.
- **Audit-time researcher tooling** — beyond Django admin, is there a
  bulk-downgrade workflow needed? Likely not for v1's cohort size but
  worth flagging.
- **Per-question proportional credit** — explicitly out of v1. If
  manual audit proves too slow, this is the obvious next iteration.
- **Group-specific point ceilings** — `available_max` currently sums
  over the viewer's routed scheduled opportunities, so w_first and
  q_first participants may see different denominators. If the research
  team wants a single fixed ceiling instead, swap the `available_max`
  formula.
- **Daily/repeatable response semantics** — the points ledger will be
  schedule-opportunity aware, but the existing `SurveyResponse` model
  still does not store `scheduled_survey`. If the research team later
  wants response analytics grouped directly by schedule row, that is a
  separate model change outside this participant-visible points v1.

## What NOT to do

- **Don't automate audit downgrades.** Researcher review is the
  anti-gaming guardrail. Adding automatic skip detection in v1 risks
  false positives that erode trust in the points display.
- **Don't implement survey awards as a model-level `post_save` signal.**
  The submit view has the context needed to distinguish first submit,
  edit, repeatable create, and valid schedule row.
- **Don't key survey awards by `source_slug` alone.** The current
  schedule can reuse a survey slug across multiple participant
  opportunities.
- **Don't backfill points when a prereq is completed after the gated
  survey.** That weakens the "do prereqs first" incentive — see the
  Prerequisite mechanic section.
- **Don't expose `adjusted_points` editing to the participant.** Only
  Django admin / management command writes this column.
- **Don't roll the dollar estimate into per-card badges.** The
  conversion display is intentionally consolidated on the
  `/reimbursement` page so the participant sees the audit policy
  every time they look at a dollar figure.
- **Don't show negative points anywhere in the participant UI.** A
  downgrade renders as a strikethrough of the original plus the
  smaller new value — never "-3 pts" as a delta.
- **Don't show both "High priority" and a nonzero points chip for the
  same survey row.** Points become the participant-facing incentive
  signal once configured.

## Files this will likely touch

| File | Change |
|---|---|
| `adoorback/surveys/models.py` | Add `point_value` + `point_prereq_slug` to Survey; add `PointAward` model with `scheduled_survey`, `response`, nonnegative adjustment, and Meta constraints |
| `adoorback/surveys/migrations/00XX_points_system.py` | One schema migration covering both Survey fields + PointAward |
| `adoorback/surveys/points.py` (new) | Resolve scheduled opportunity, prereq state, idempotent award creation, totals, `available_max`, and display helpers |
| `adoorback/surveys/management/commands/load_surveys.py` | Read `point_value` + `point_prereq_slug` from YAML during upsert |
| `adoorback/surveys/fixtures/{daily,pre,endpoint,weekly_anytime,sotd,closeness_reeval,habit_platform}.yaml` | Add `point_value` (+ `point_prereq_slug` where applicable) to every served survey |
| `adoorback/surveys/management/commands/credit_wit_bot_audit.py` (new) | Admin command to create a wit_bot_audit PointAward |
| `adoorback/surveys/management/commands/credit_interview_signup.py` (new) | Admin command for interview signup credit |
| `adoorback/surveys/admin.py` | Register PointAward with admin actions for adjustment + manual credit |
| `adoorback/surveys/views.py` | Call points helper inside `SurveyResponseSubmitView`; add `ReimbursementView` returning the JSON shape above |
| `adoorback/surveys/serializers.py` | `point_value`, prereq lock fields, and `point_award` on SurveyDetailSerializer + index entry serializer; preserve existing `results_unlocked` / draft fields |
| `adoorback/surveys/urls.py` | Route `/api/surveys/reimbursement/`; place it before `<slug:slug>/` so `reimbursement` is not captured as a survey slug |
| `adoorback/surveys/reimbursement_config.py` (new) | `POINTS_PER_DOLLAR` constant + helpers |
| `adoorback/surveys/audit.py` | Include point values in schedule/user audit output and warn about served surveys missing intentional point values |
| `adoorback/surveys/tests_*.py` | Add points model/helper/API tests; extend existing scheduling/round-trip tests for schedule-aware awards |
| `WhoamI-Today-frontend/src/routes/reimbursement/Reimbursement.tsx` | Replace placeholder with full page |
| `WhoamI-Today-frontend/src/routes/surveys/SurveysIndex.tsx` | Top summary card + per-row badge |
| `WhoamI-Today-frontend/src/components/share/SurveyOfTheDay.tsx` | Show point state on SOTD card |
| `WhoamI-Today-frontend/src/routes/surveys/DailyArchive.tsx` | Show point state on answerable/answered daily archive rows |
| `WhoamI-Today-frontend/src/routes/surveys/SurveyDone.tsx` | Show optional provisional-credit line from submit response |
| `WhoamI-Today-frontend/src/routes/surveys/SurveyResults.tsx` | Ensure editable-survey copy/actions do not imply additional points |
| `WhoamI-Today-frontend/src/components/survey/PointsBadge.tsx` (new) | Badge component (earnable / locked / earned / downgraded variants) |
| `WhoamI-Today-frontend/src/components/survey/LockedBadgeModal.tsx` (new) | Tap-to-explain modal |
| `WhoamI-Today-frontend/src/components/header/side-menu/SideMenu.tsx` | Keep existing reimbursement entry; add point-total chip |
| `WhoamI-Today-frontend/src/utils/apis/reimbursement.ts` (new) | Typed client for the new endpoint |
| `WhoamI-Today-frontend/src/models/reimbursement.ts` (new) | TypeScript types |
| `WhoamI-Today-frontend/src/models/survey.ts` | Add point fields to survey detail/index/daily archive shapes |
| `WhoamI-Today-frontend/src/utils/apis/survey.ts` | Widen submit response to include optional `point_award`; cache invalidation hooks can use it |
| `WhoamI-Today-frontend/src/index.tsx` | No new route needed; keep existing `/reimbursement` registration |
| `WhoamI-Today-frontend/src/i18n/locales/{en,ko}/translation.json` | New `reimbursement.*` namespace |
