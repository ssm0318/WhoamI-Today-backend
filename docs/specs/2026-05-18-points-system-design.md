# Participant points & reimbursement — design

**Date authored:** 2026-05-18
**Status:** design only — no implementation yet
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

The mechanism: submit credits the survey's full `point_value`
provisionally. A `PointAward` ledger row carries an `adjusted_points`
override that the researcher can fill in at audit time (e.g., 0 for a
garbage response). The UI shows the adjusted value when present, with
the original struck through for transparency. Every points display
carries a disclaimer linking to `/reimbursement` for the full policy.

## What earns points

| Source kind        | How it's awarded                            | Slug                |
|--------------------|---------------------------------------------|---------------------|
| Survey             | `post_save` on `SurveyResponse` (first only)| `<survey.slug>`     |
| Wit_bot audit      | Researcher / wit_bot manual credit          | `wit_bot_audit`     |
| Interview signup   | Researcher manual credit                    | `interview_signup`  |

**Per-survey point values are variable** and declared per-survey in
YAML. The researcher tunes them as incentives — end-of-phase and
feature-evaluation surveys carry the largest values; SOTD entries vary
by analytic priority; daily entries carry small per-day amounts so the
daily habit is rewarded without overshadowing higher-stakes endpoints.

**Wit_bot audit criteria (researcher checks at audit time):**

- Push notifications enabled for the study window
- Has added at least N friends (N TBD; matches existing wit_bot copy
  threshold)
- Has posted and commented (engagement signal)
- Has tried each of the in-app features (browse mode, check-ins,
  reactions, etc.)

v1 awards this as a single line item ("Wit_bot audit pass: +X pts") on
the reimbursement page. Per-criterion automation can be layered in
later without changing the participant-visible UX.

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

## Partial credit

Surveys credit the **full** `point_value` on submit. There is no
per-question proportional model in v1. Anti-gaming is enforced through
the researcher audit, not through automatic skip-detection.

Editable surveys (`feature_eval_w`, `goal_comparison_p1/p2`) credit on
**first** submit only. Subsequent edits do not change the points
award; the participant is informed of this in the survey description
so they don't try to game it by toggling answers.

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
    # Only set for source_kind='survey'. ON DELETE SET_NULL so a
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
    adjusted_points = models.IntegerField(null=True, blank=True)
    note = models.TextField(blank=True, default='')

    class Meta:
        constraints = [
            # One survey-source award per (user, response) — captures the
            # "credit on first submit only" rule.
            models.UniqueConstraint(
                fields=['user', 'response'],
                condition=models.Q(source_kind='survey', response__isnull=False),
                name='unique_award_per_user_per_response',
            ),
            # One non-survey award per (user, source_kind, source_slug).
            # Researcher can re-credit by editing the row (adjusted_points),
            # not by creating a second one.
            models.UniqueConstraint(
                fields=['user', 'source_kind', 'source_slug'],
                condition=models.Q(response__isnull=True),
                name='unique_award_per_user_per_non_survey_source',
            ),
        ]
```

### Award triggers

- **Survey:** `post_save` signal on `SurveyResponse`. If the response
  is a first submit (vs. an edit on an editable survey), look up the
  survey's `point_value` and `point_prereq_slug`. If prereq is met
  (or blank), credit full; otherwise credit 0 with note. Uses
  `get_or_create` keyed on `(user, response)` so re-runs don't
  double-credit.
- **Wit_bot audit:** Django admin action on a custom list-page button,
  or `python manage.py credit_wit_bot_audit --user <username> --pts <n>`
  management command. Idempotent via `get_or_create` on (user,
  source_kind='wit_bot_audit', source_slug='wit_bot_audit').
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
      "title_en": "Looking back: Phase 1",
      "awarded_points": 50,
      "adjusted_points": null,
      "note": "",
      "submitted_at": "2026-05-17T10:23:00Z"
    },
    {
      "source_kind": "survey",
      "source_slug": "sotd_d15_shi",
      "title_en": "How automatic is Instagram?",
      "awarded_points": 0,
      "adjusted_points": null,
      "note": "Prereq pre_study_catchup not completed at submit time.",
      "submitted_at": "2026-05-18T09:00:00Z"
    },
    {
      "source_kind": "wit_bot_audit",
      "source_slug": "wit_bot_audit",
      "title_en": "Wit_bot audit pass",
      "awarded_points": 10,
      "adjusted_points": null,
      "note": "",
      "submitted_at": "2026-05-12T15:00:00Z"
    }
  ],
  "pending_prereqs": [
    {
      "survey_slug": "sotd_d15_shi",
      "title_en": "How automatic is Instagram?",
      "potential_points": 10,
      "prereq_slug": "pre_study_catchup",
      "prereq_title_en": "One quick question we missed at the start"
    }
  ]
}
```

`available_max` is the sum of `point_value` over every survey
currently scheduled for the viewer plus the configured wit_bot +
interview signup max values. It gives the "X / 800 pts" denominator
on the summary card.

### Existing endpoints get two new fields

`GET /api/surveys/index/` entry — `point_value`,
`point_locked_by_prereq_slug` (null when no prereq, or when prereq is
met for the viewer).

`GET /api/surveys/<slug>/` survey — same two fields, plus the
already-existing `point_prereq_slug`.

## Frontend

### SurveysIndex (`/surveys`)

Top of the page gets a provisional-total summary card showing
"Provisional points so far: 145 pts" with a "See how this works ›"
link to `/reimbursement`. Per-row badge rendering:

| State                  | Badge style                                                         |
|------------------------|---------------------------------------------------------------------|
| Earnable, no prereq    | Purple chip "+10 pts" (matches existing chip style, F3E8FF / 8700FF)|
| Earnable, prereq unmet | Gray chip with dashed border and lock icon "🔒 +10 pts" (Style A)   |
| Completed              | Green chip "✓ +3 pts"                                               |
| Completed, downgraded  | Green chip "+1 pts" with original 3 struck through                  |

Tapping a locked badge opens a modal (reusing `CommonDialog` for
consistency) that:

- Names the gating survey
- States "You'll earn N pts when you complete `<gating survey>` first"
- Notes that submitting this survey now credits 0 pts
- Offers a primary "Do prereq now" button (navigates to the prereq's
  `/surveys/<slug>/answer` page) + a secondary "Close" button

### Sidebar (`SideMenu.tsx`)

Add one entry:

```ts
{ key: 'reimbursement', emoji: '💰', path: '/reimbursement' }
```

Render with the Style B treatment — label + small purple chip on the
right showing the running provisional total ("145 pts"). The chip
matches the canonical chip style (`#F3E8FF` bg, `#8700FF` text, 8px
radius). The total is fetched once when the sidebar opens (via the
same `/reimbursement/` endpoint or a zustand store slice that caches
it across opens). When the user has 0 points, the chip is omitted.

### New page: `/reimbursement`

Reads `GET /api/surveys/reimbursement/`. Layout:

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

New namespace `reimbursement.*` (en + ko):
- `nav_label` — sidebar entry
- `summary_title`, `provisional_total_label`, `dollar_estimate_label`
- `audit_disclaimer_short` (for index summary card) and
  `audit_disclaimer_long` (for the dedicated page)
- `locked_badge_modal_title`, `locked_badge_modal_body`,
  `locked_badge_do_prereq_button`, `locked_badge_close_button`
- `section_surveys`, `section_other_activities`, `section_pending`
- `wit_bot_audit_label`, `interview_signup_label`
- `downgraded_label` (small caption on adjusted rows)

## Verification

Before declaring v1 done:

1. **Schema:** `python manage.py makemigrations --check` clean after
   adding `point_value` + `point_prereq_slug` to Survey and adding the
   PointAward model.
2. **Award trigger:**
   - First survey submit creates one `PointAward` row with the survey's
     full `point_value`.
   - Second (edit) submit on an editable survey does NOT create a new
     row.
   - Submit with unmet prereq creates a row with `awarded_points=0`
     and a clear note.
3. **API:** `GET /api/surveys/reimbursement/` returns the expected
   shape; `provisional_total` matches manual `SUM(awarded_points)`
   from the shell; `adjusted_total` reflects any test downgrade.
4. **Survey index payload:** entries carry `point_value` and
   `point_locked_by_prereq_slug` correctly per viewer.
5. **Frontend e2e:**
   - Earnable badges render purple on currently-available surveys.
   - Locked badges render gray-with-lock on prereq-blocked surveys.
   - Tapping a locked badge opens the modal naming the right gating
     survey.
   - Sidebar chip shows the right total; updates after a submit.
   - `/reimbursement` page loads, groups awards correctly, shows
     dollar estimate, shows disclaimer.
6. **Mobile-responsive:** all surfaces verified at 320px and 393px.
7. **Researcher admin:** Django admin allows editing
   `PointAward.adjusted_points` + `note`; the page reflects the
   downgraded total on next load.

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
  over the viewer's actual scheduled surveys, so w_first and q_first
  participants see different denominators. If the research team wants
  a single fixed ceiling instead, swap the `available_max` formula.

## What NOT to do

- **Don't automate audit downgrades.** Researcher review is the
  anti-gaming guardrail. Adding automatic skip detection in v1 risks
  false positives that erode trust in the points display.
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

## Files this will likely touch

| File | Change |
|---|---|
| `adoorback/surveys/models.py` | Add `point_value` + `point_prereq_slug` to Survey; add `PointAward` model + Meta constraints |
| `adoorback/surveys/migrations/00XX_points_system.py` | One schema migration covering both Survey fields + PointAward |
| `adoorback/surveys/signals.py` (new) or `models.py` | `post_save` on `SurveyResponse` → `PointAward` row creation with prereq check |
| `adoorback/surveys/management/commands/load_surveys.py` | Read `point_value` + `point_prereq_slug` from YAML during upsert |
| `adoorback/surveys/fixtures/*.yaml` | Add `point_value` (+ `point_prereq_slug` where applicable) to every served survey |
| `adoorback/surveys/management/commands/credit_wit_bot_audit.py` (new) | Admin command to create a wit_bot_audit PointAward |
| `adoorback/surveys/management/commands/credit_interview_signup.py` (new) | Admin command for interview signup credit |
| `adoorback/surveys/admin.py` | Register PointAward with admin actions for adjustment + manual credit |
| `adoorback/surveys/views.py` | `ReimbursementView` returning the JSON shape above |
| `adoorback/surveys/serializers.py` | `point_value` + `point_locked_by_prereq_slug` on SurveyDetailSerializer + index entry serializer |
| `adoorback/surveys/urls.py` | Route `/api/surveys/reimbursement/` |
| `adoorback/surveys/reimbursement_config.py` (new) | `POINTS_PER_DOLLAR` constant + helpers |
| `WhoamI-Today-frontend/src/routes/reimbursement/Reimbursement.tsx` (new) | New page |
| `WhoamI-Today-frontend/src/routes/surveys/SurveysIndex.tsx` | Top summary card + per-row badge |
| `WhoamI-Today-frontend/src/components/survey/PointsBadge.tsx` (new) | Badge component (earnable / locked / earned / downgraded variants) |
| `WhoamI-Today-frontend/src/components/survey/LockedBadgeModal.tsx` (new) | Tap-to-explain modal |
| `WhoamI-Today-frontend/src/components/header/side-menu/SideMenu.tsx` | Add the entry + chip |
| `WhoamI-Today-frontend/src/utils/apis/reimbursement.ts` (new) | Typed client for the new endpoint |
| `WhoamI-Today-frontend/src/models/reimbursement.ts` (new) | TypeScript types |
| `WhoamI-Today-frontend/src/index.tsx` | Register the `/reimbursement` route |
| `WhoamI-Today-frontend/src/i18n/locales/{en,ko}/translation.json` | New `reimbursement.*` namespace |
