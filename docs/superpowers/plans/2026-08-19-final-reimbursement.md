# Final Reimbursement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Materialize and verify every participant's final reimbursement source, serve the same final ledger on the participant page and researcher dashboard, and replace obsolete reimbursement artifacts with one reconciled CSV.

**Architecture:** Add deterministic backend scoring and a transactional reconciliation command that upserts all non-survey awards and preserves audited survey adjustments. Remove compute-on-read awards so the ledger, API, dashboard, and CSV all sum the same rows. Simplify the frontend to a final reimbursement view with explicit data-quality and interview-action states.

**Tech Stack:** Django 4 / Django REST Framework / PostgreSQL, pytest/Django TestCase, React 18 / TypeScript / SWR / Styled Components / Jest, Streamlit / pandas, bundled `@oai/artifact-tool` for the final CSV.

**Spec:** `docs/superpowers/specs/2026-08-19-final-reimbursement-design.md`

## Global Constraints

- Work directly on `release/final-research`; do not create feature branches.
- Preserve all unrelated dirty-worktree changes and stage only files owned by each task.
- Never include a `Co-Authored-By: Codex` trailer.
- Never push, merge, rebase, pull, or deploy without explicit user approval.
- Use account IDs 8–87 excluding 64, plus replacement account 114.
- Use 10 points per US dollar.
- Preserve all existing survey `adjusted_points` and audit notes.
- Boss-quiz thresholds are strict: best score `> 0.85` earns 50; best score `> 0.60` earns 10; otherwise 0.
- Friend invitations earn 100 per non-staff invitee, capped at 500.
- Confirmed interviews earn 100 except `rebecca.laba@gmail.com`, which earns 125.
- Participants without interview credit see `https://calendly.com/jaewonkim/60min`.
- Survey submissions and survey points are frozen; the reimbursement page must not advertise additional surveys.
- Delete only obsolete reimbursement-related files; preserve unrelated historical analysis.
- Verify frontend UI at 375 px, 393 px, and 320 px.

---

### Task 1: Final source constants and ledger model

**Files:**
- Modify: `adoorback/surveys/models.py`
- Modify: `adoorback/surveys/reimbursement_config.py`
- Create: `adoorback/surveys/migrations/0051_alter_pointaward_source_kind.py`
- Test: `adoorback/surveys/tests_final_reimbursement.py`

**Interfaces:**
- Consumes: existing `PointAward`, `WIT_BOT_AUDIT_PHASES`, `APP_USAGE_PHASES`.
- Produces: `PointAward.SOURCE_FRIEND_INVITE`, `WIT_BOT_AUDIT_PARTIAL_POINTS`, `INTERVIEW_COMPLETED_POINTS`, `INTERVIEW_REBECCA_POINTS`, `FRIEND_INVITE_POINTS_PER_FRIEND`, and final source metadata.

- [ ] **Step 1: Write failing constant/model tests**

```python
from django.test import SimpleTestCase

from surveys.models import PointAward
from surveys.reimbursement_config import (
    FRIEND_INVITE_MAX_POINTS,
    FRIEND_INVITE_POINTS_PER_FRIEND,
    INTERVIEW_COMPLETED_POINTS,
    INTERVIEW_REBECCA_POINTS,
    WIT_BOT_AUDIT_PARTIAL_POINTS,
    WIT_BOT_AUDIT_PHASES,
)


class FinalReimbursementConfigTests(SimpleTestCase):
    def test_final_source_values(self):
        self.assertEqual(PointAward.SOURCE_FRIEND_INVITE, 'friend_invite')
        self.assertEqual(WIT_BOT_AUDIT_PARTIAL_POINTS, 10)
        self.assertEqual(WIT_BOT_AUDIT_PHASES[1]['max_points'], 50)
        self.assertEqual(WIT_BOT_AUDIT_PHASES[2]['max_points'], 50)
        self.assertEqual(INTERVIEW_COMPLETED_POINTS, 100)
        self.assertEqual(INTERVIEW_REBECCA_POINTS, 125)
        self.assertEqual(FRIEND_INVITE_POINTS_PER_FRIEND, 100)
        self.assertEqual(FRIEND_INVITE_MAX_POINTS, 500)
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run from `WhoamI-Today-backend/adoorback`:

```bash
../venv/bin/python manage.py test surveys.tests_final_reimbursement.FinalReimbursementConfigTests
```

Expected: import or attribute failure for the new constants/source kind.

- [ ] **Step 3: Add final constants and source choice**

Implement these exact public values in `reimbursement_config.py`:

```python
WIT_BOT_AUDIT_PARTIAL_POINTS = 10
WIT_BOT_AUDIT_PHASE_1_MAX_POINTS = 50
WIT_BOT_AUDIT_PHASE_2_MAX_POINTS = 50
INTERVIEW_COMPLETED_POINTS = 100
INTERVIEW_REBECCA_POINTS = 125
FRIEND_INVITE_POINTS_PER_FRIEND = 100
FRIEND_INVITE_MAX_POINTS = 500
INTERVIEW_SIGNUP_URL = 'https://calendly.com/jaewonkim/60min'
```

Add the source constant and choice to `PointAward`:

```python
SOURCE_FRIEND_INVITE = 'friend_invite'

SOURCE_KIND_CHOICES = (
    # existing choices
    (SOURCE_FRIEND_INVITE, 'Friend invitations'),
)
```

Create migration `0051_alter_pointaward_source_kind.py` as an `AlterField` migration whose choices exactly match the model. The database column remains a `CharField(max_length=32)`.

- [ ] **Step 4: Run tests and migration checks**

```bash
../venv/bin/python manage.py test surveys.tests_final_reimbursement.FinalReimbursementConfigTests
../venv/bin/python manage.py makemigrations --check
```

Expected: tests pass and no uncreated migration is reported.

- [ ] **Step 5: Commit the source definitions**

```bash
git add adoorback/surveys/models.py adoorback/surveys/reimbursement_config.py adoorback/surveys/migrations/0051_alter_pointaward_source_kind.py adoorback/surveys/tests_final_reimbursement.py
git commit -m "feat(reimbursement): define final award sources"
```

### Task 2: Pure final-reimbursement scoring

**Files:**
- Create: `adoorback/surveys/final_reimbursement.py`
- Modify: `adoorback/surveys/tests_final_reimbursement.py`

**Interfaces:**
- Consumes: final constants from Task 1 and version mapping from `surveys.points.wit_bot_audit_version_for_group`.
- Produces:
  - `best_boss_quiz_score(progress: dict) -> float | None`
  - `wit_bot_points_for_score(score: float | None) -> int`
  - `wit_bot_outcome(context: dict, user_group: str, phase: int) -> WitBotOutcome`
  - `friend_invite_outcome(invitees: Iterable[InviteeRecord]) -> FriendInviteOutcome`
  - `interview_points_for_email(email: str) -> int`
  - immutable dataclasses with points and audit-note fields.

- [ ] **Step 1: Write failing WIT scoring tests**

```python
class WitBotFinalScoringTests(SimpleTestCase):
    def test_best_score_uses_attempt_history_and_final_score(self):
        progress = {
            'attempts_history': [{'score': 0.7}, {'score': 0.9}],
            'final_score': 0.8,
        }
        self.assertEqual(best_boss_quiz_score(progress), 0.9)

    def test_thresholds_are_strict(self):
        cases = [(None, 0), (0.60, 0), (0.6001, 10), (0.85, 10), (0.8501, 50)]
        self.assertEqual(
            [wit_bot_points_for_score(score) for score, _ in cases],
            [expected for _, expected in cases],
        )

    def test_phase_maps_to_crossover_version_and_records_audit_details(self):
        context = {
            'version_q': {
                'final_quiz': {'attempts_history': [{'score': 0.8}]},
                'audit': {'last_engaged_count': 9, 'last_missing_count': 1},
            }
        }
        outcome = wit_bot_outcome(context, 'group_q_first', phase=1)
        self.assertEqual(outcome.version, 'version_q')
        self.assertEqual(outcome.points, 10)
        self.assertIn('engaged=9', outcome.note)
        self.assertIn('missing=1', outcome.note)
```

- [ ] **Step 2: Write failing invite/interview tests**

```python
class ManualSourceScoringTests(SimpleTestCase):
    def test_invites_ignore_staff_and_cap_at_five(self):
        invitees = [InviteeRecord(i, f'user{i}', False) for i in range(1, 7)]
        invitees.append(InviteeRecord(99, 'staff', True))
        outcome = friend_invite_outcome(invitees)
        self.assertEqual(outcome.eligible_count, 6)
        self.assertEqual(outcome.points, 500)
        self.assertNotIn('staff', outcome.note)

    def test_interview_email_matching_and_rebecca_exception(self):
        self.assertEqual(interview_points_for_email(' JENNYLNINH@GMAIL.COM '), 100)
        self.assertEqual(interview_points_for_email('rebecca.laba@gmail.com'), 125)
        self.assertEqual(interview_points_for_email('nasiu21321@gmail.com'), 0)
```

- [ ] **Step 3: Run the tests and confirm missing interfaces fail**

```bash
../venv/bin/python manage.py test \
  surveys.tests_final_reimbursement.WitBotFinalScoringTests \
  surveys.tests_final_reimbursement.ManualSourceScoringTests
```

Expected: import/name failures for the new module interfaces.

- [ ] **Step 4: Implement immutable outcomes and pure functions**

Use these signatures:

```python
@dataclass(frozen=True)
class WitBotOutcome:
    phase: int
    version: str
    best_score: float | None
    audit_engaged_count: int | None
    audit_missing_count: int | None
    points: int
    note: str


@dataclass(frozen=True)
class InviteeRecord:
    user_id: int
    username: str
    is_staff: bool


@dataclass(frozen=True)
class FriendInviteOutcome:
    eligible_count: int
    credited_count: int
    points: int
    note: str
```

`interview_points_for_email` uses a frozen lowercase set for the ten standard emails and a direct equality check for Rebecca. `friend_invite_outcome` sorts eligible invitees by `user_id`, awards `min(count * 100, 500)`, and writes the full eligible ID/username list in the note even when the point cap applies.

- [ ] **Step 5: Run the scoring tests**

```bash
../venv/bin/python manage.py test \
  surveys.tests_final_reimbursement.WitBotFinalScoringTests \
  surveys.tests_final_reimbursement.ManualSourceScoringTests
```

Expected: all tests pass.

- [ ] **Step 6: Commit pure scoring**

```bash
git add adoorback/surveys/final_reimbursement.py adoorback/surveys/tests_final_reimbursement.py
git commit -m "feat(reimbursement): calculate final manual-source points"
```

### Task 3: Transactional ledger reconciliation command

**Files:**
- Modify: `adoorback/surveys/app_usage.py`
- Create: `adoorback/surveys/management/commands/finalize_reimbursement.py`
- Modify: `adoorback/surveys/final_reimbursement.py`
- Modify: `adoorback/surveys/tests_final_reimbursement.py`

**Interfaces:**
- Consumes: pure scoring functions from Task 2, `PointAward`, `SurveyResponse`, `WitBotConversationState`, and the existing app-usage phase classifier.
- Produces:
  - `FinalAwardSpec(source_kind, source_slug, awarded_points, adjusted_points, note)`
  - `build_final_award_specs(user, *, phase1_database='default', phase2_database='default') -> list[FinalAwardSpec]`
  - `reconcile_user_awards(user, specs, *, apply: bool) -> ReconciliationResult`
  - `finalize_reimbursement` command with dry-run default and `--apply`.

- [ ] **Step 1: Write failing reconciliation tests**

```python
class FinalLedgerReconciliationTests(TestCase):
    databases = {'default', 'phase1_restore'}

    def test_build_specs_returns_two_rows_for_each_phase_source(self):
        specs = build_final_award_specs(
            self.user,
            phase1_database='phase1_restore',
            phase2_database='default',
        )
        keys = {(spec.source_kind, spec.source_slug) for spec in specs}
        self.assertTrue({
            ('app_usage', 'app_usage_phase_1'),
            ('app_usage', 'app_usage_phase_2'),
            ('wit_bot_audit', 'wit_bot_audit_phase_1'),
            ('wit_bot_audit', 'wit_bot_audit_phase_2'),
            ('friend_invite', 'friend_invite'),
        }.issubset(keys))

    def test_dry_run_writes_nothing_and_apply_is_idempotent(self):
        specs = [FinalAwardSpec('friend_invite', 'friend_invite', 100, None, '1 invite')]
        dry = reconcile_user_awards(self.user, specs, apply=False)
        self.assertEqual(dry.created, 1)
        self.assertFalse(PointAward.objects.filter(user=self.user).exists())

        reconcile_user_awards(self.user, specs, apply=True)
        reconcile_user_awards(self.user, specs, apply=True)
        self.assertEqual(
            PointAward.objects.filter(
                user=self.user,
                source_kind='friend_invite',
                source_slug='friend_invite',
            ).count(),
            1,
        )

    def test_existing_survey_adjustments_are_never_overwritten(self):
        award = PointAward.objects.create(
            user=self.user,
            source_kind='survey',
            source_slug='post_study_q',
            awarded_points=50,
            adjusted_points=0,
            note='Good-faith survey audit exclusion.',
        )
        reconcile_user_awards(self.user, [], apply=True)
        award.refresh_from_db()
        self.assertEqual(award.adjusted_points, 0)
        self.assertEqual(award.note, 'Good-faith survey audit exclusion.')
```

- [ ] **Step 2: Write failing command-validation tests**

```python
class FinalizeReimbursementCommandTests(TestCase):
    def test_duplicate_interview_email_aborts_before_writes(self):
        User.objects.create(username='duplicate', email='jennylninh@gmail.com')
        with self.assertRaises(CommandError):
            call_command('finalize_reimbursement', '--apply')
        self.assertFalse(PointAward.objects.filter(source_kind='interview_signup').exists())

    def test_default_mode_is_dry_run(self):
        output = StringIO()
        call_command('finalize_reimbursement', stdout=output)
        self.assertIn('DRY RUN', output.getvalue())
        self.assertFalse(PointAward.objects.filter(source_kind='friend_invite').exists())
```

- [ ] **Step 3: Run the focused tests and confirm failure**

```bash
../venv/bin/python manage.py test \
  surveys.tests_final_reimbursement.FinalLedgerReconciliationTests \
  surveys.tests_final_reimbursement.FinalizeReimbursementCommandTests
```

Expected: missing interfaces/command failures.

- [ ] **Step 4: Make app-usage reads database-aware**

Add a keyword-only `using: str = 'default'` parameter to the public phase
activity/classification entry point and apply `.using(using)` to every ORM
query it performs. Accept a `user_id` or a user object but never attempt to
save a model loaded from the restore connection.

The Phase-1 command path uses a `phase1_restore` database alias assembled from
`RESTORE_DB_HOST`, `RESTORE_DB_PORT`, `RESTORE_DB_NAME`, `RESTORE_DB_USER`, and
`RESTORE_DB_PASSWORD`. Phase 2 uses `default`. Tests define the alias with
`@override_settings(DATABASES=...)` and fixtures in both test databases.

- [ ] **Step 5: Implement spec building and idempotent reconciliation**

Use these dataclasses:

```python
@dataclass(frozen=True)
class FinalAwardSpec:
    source_kind: str
    source_slug: str
    awarded_points: int
    adjusted_points: int | None
    note: str


@dataclass(frozen=True)
class ReconciliationResult:
    created: int
    updated: int
    unchanged: int
    projected_points: int
```

For interview credit, include an `interview_signup` spec only when
`interview_points_for_email(user.email) > 0`. For all app, WIT, and invitation
outcomes include a spec even when points are zero. Upsert only non-survey rows
and update `awarded_points`, `adjusted_points`, and `note` together.

- [ ] **Step 6: Implement the management command**

The command:

```text
finalize_reimbursement [--apply] [--phase1-database phase1_restore]
```

must validate the cohort count, exact interview-email matches, database
availability, and survey adjustment spot checks before entering
`transaction.atomic(using='default')`. Output one participant row and a final
source summary in both modes. When `--apply` is absent, do not call any save or
update operation.

- [ ] **Step 7: Run reconciliation and existing point tests**

```bash
../venv/bin/python manage.py test surveys.tests_final_reimbursement surveys.tests_points
```

Expected: all tests pass.

- [ ] **Step 8: Commit reconciliation**

```bash
git add adoorback/surveys/app_usage.py adoorback/surveys/final_reimbursement.py adoorback/surveys/management/commands/finalize_reimbursement.py adoorback/surveys/tests_final_reimbursement.py
git commit -m "feat(reimbursement): reconcile final participant ledger"
```

### Task 4: Materialized-only reimbursement API

**Files:**
- Modify: `adoorback/surveys/points.py`
- Modify: `adoorback/surveys/tests_points.py`
- Modify: `adoorback/surveys/tests_final_reimbursement.py`

**Interfaces:**
- Consumes: finalized `PointAward` rows.
- Produces: `reimbursement_state_for_user(user)` with final totals, materialized awards, and interview opportunity metadata.

- [ ] **Step 1: Write failing API-state tests**

```python
class FinalReimbursementStateTests(TestCase):
    def test_state_sums_only_materialized_effective_points(self):
        PointAward.objects.create(
            user=self.user,
            source_kind='survey',
            source_slug='post_study_q',
            awarded_points=50,
            adjusted_points=0,
            note='Not credited after good-faith review.',
        )
        state = reimbursement_state_for_user(self.user)
        self.assertEqual(state['adjusted_total'], 0)
        self.assertEqual(state['provisional_total'], 0)
        self.assertEqual(state['dollar_estimate_cents'], 0)
        self.assertEqual(len(state['awards']), 1)

    def test_missing_interview_award_returns_calendly_opportunity(self):
        state = reimbursement_state_for_user(self.user)
        self.assertEqual(state['interview_opportunity'], {
            'available': True,
            'points': 100,
            'url': 'https://calendly.com/jaewonkim/60min',
        })

    def test_completed_interview_hides_opportunity(self):
        PointAward.objects.create(
            user=self.user,
            source_kind='interview_signup',
            source_slug='interview_signup',
            awarded_points=100,
        )
        self.assertFalse(reimbursement_state_for_user(self.user)['interview_opportunity']['available'])
```

- [ ] **Step 2: Run the tests and confirm old synthetic behavior fails expectations**

```bash
../venv/bin/python manage.py test surveys.tests_final_reimbursement.FinalReimbursementStateTests
```

Expected: interview metadata failure and/or synthetic award total mismatch.

- [ ] **Step 3: Remove compute-on-read award extensions**

In `reimbursement_state_for_user`, remove calls to
`_computed_missing_survey_awards_for_user` and
`_computed_wit_bot_audit_awards_for_user`. Keep the helpers only if another
backfill path still imports them; otherwise delete them and update focused
tests. Set both legacy `provisional_total` and `adjusted_total` to the sum of
materialized `effective_points`.

Add:

```python
'interview_opportunity': {
    'available': not has_interview_award,
    'points': INTERVIEW_COMPLETED_POINTS,
    'url': INTERVIEW_SIGNUP_URL,
}
```

- [ ] **Step 4: Run all survey point tests**

```bash
../venv/bin/python manage.py test surveys.tests_points surveys.tests_final_reimbursement
```

Expected: all tests pass.

- [ ] **Step 5: Commit API finalization**

```bash
git add adoorback/surveys/points.py adoorback/surveys/tests_points.py adoorback/surveys/tests_final_reimbursement.py
git commit -m "fix(reimbursement): serve the materialized final ledger"
```

### Task 5: Final participant reimbursement page

**Files:**
- Modify: `WhoamI-Today-frontend/src/models/reimbursement.ts`
- Modify: `WhoamI-Today-frontend/src/utils/apis/reimbursement.ts`
- Modify: `WhoamI-Today-frontend/src/routes/reimbursement/Reimbursement.tsx`
- Modify: `WhoamI-Today-frontend/src/routes/reimbursement/Reimbursement.test.tsx`
- Modify: `WhoamI-Today-frontend/src/i18n/locales/en/translation.json`
- Modify: `WhoamI-Today-frontend/src/i18n/locales/ko/translation.json`

**Interfaces:**
- Consumes: final reimbursement API from Task 4.
- Produces: final totals, credited/not-credited ledger rows, good-faith policy, and conditional interview action.

- [ ] **Step 1: Write failing finalized-copy and interview tests**

```tsx
it('renders final reimbursement language and the good-faith policy', async () => {
  render(<Reimbursement />);
  expect(await screen.findByText('430 pts')).toBeInTheDocument();
  expect(screen.getByText('$43.00 reimbursement')).toBeInTheDocument();
  expect(
    screen.getByText(
      'Surveys determined not to have been answered in good faith were not credited, even when the survey was completed.',
    ),
  ).toBeInTheDocument();
  expect(screen.queryByText(/preview|draft|provisional|rough estimate|may change/i)).not.toBeInTheDocument();
});

it('shows the Calendly action only when the interview remains available', async () => {
  mockState.interview_opportunity = {
    available: true,
    points: 100,
    url: 'https://calendly.com/jaewonkim/60min',
  };
  render(<Reimbursement />);
  expect(await screen.findByRole('link', { name: 'Sign up' })).toHaveAttribute(
    'href',
    'https://calendly.com/jaewonkim/60min',
  );
});

it('hides the Calendly action after interview credit', async () => {
  mockState.interview_opportunity.available = false;
  render(<Reimbursement />);
  expect(await screen.findByText('Points you earned')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Sign up' })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run the focused test and confirm failure**

Run with Node 18:

```bash
source ~/.nvm/nvm.sh
nvm use 18
npx craco test --watchAll=false src/routes/reimbursement/Reimbursement.test.tsx
```

Expected: final-copy/interview-state failures.

- [ ] **Step 3: Update the API type and remove browser-preview routing**

Add to `ReimbursementState`:

```ts
interview_opportunity: {
  available: boolean;
  points: number;
  url: string;
};
```

Make `getReimbursementState` always fetch `/surveys/reimbursement/`. Remove
the survey-index fetch, survey action construction, production use of
`LOCAL_REIMBURSEMENT_PREVIEW_URL`, browser-local allocation cache, and local
preview rendering from `Reimbursement.tsx`. Do not remove point-allocation
tooling that is used outside the participant route unless no imports remain.

- [ ] **Step 4: Implement final sections and copy**

Render:

- `adjusted_total` as the final points;
- `dollar_estimate_cents` as `$0.00 reimbursement` without a tilde;
- the exact approved good-faith policy;
- positive awards under “Points you earned”;
- zero/adjusted-to-zero rows under “Not credited” with the ledger note;
- a 100-point interview action using API metadata when available.

Assert that neither “Take survey” nor survey-index loading appears on the
final page. The interview signup is the only remaining point-earning action.

Replace translation keys so English and Korean both express finalized status.
Run a key-parity assertion in the Jest test by importing both JSON objects and
comparing `Object.keys(en.reimbursement).sort()` with the Korean keys.

- [ ] **Step 5: Run frontend tests**

```bash
source ~/.nvm/nvm.sh
nvm use 18
npx craco test --watchAll=false src/routes/reimbursement/Reimbursement.test.tsx
```

Expected: all reimbursement tests pass.

- [ ] **Step 6: Commit the final participant page**

```bash
git add src/models/reimbursement.ts src/utils/apis/reimbursement.ts src/routes/reimbursement/Reimbursement.tsx src/routes/reimbursement/Reimbursement.test.tsx src/i18n/locales/en/translation.json src/i18n/locales/ko/translation.json
git commit -m "feat(reimbursement): show finalized participant totals"
```

### Task 6: Researcher dashboard reconciliation

**Files:**
- Modify: `WhoamI-Today-data-analysis/admin-dashboard/data.py`
- Modify: `WhoamI-Today-data-analysis/admin-dashboard/app.py`
- Modify: `WhoamI-Today-data-analysis/admin-dashboard/tests/test_dashboard_data.py`

**Interfaces:**
- Consumes: materialized `surveys_pointaward` rows.
- Produces: per-participant/source summary and CSV-ready table matching the API ledger.

- [ ] **Step 1: Write failing dashboard summary tests**

```python
def test_build_points_summary_includes_all_final_source_columns():
    awards = pd.DataFrame([
        {'user_id': 21, 'source_kind': 'survey', 'source_slug': 'post_study_q', 'effective_points': 0, 'awarded_points': 50, 'adjusted_points': 0, 'created_at': pd.Timestamp('2026-08-19', tz='UTC'), 'note': 'excluded'},
        {'user_id': 21, 'source_kind': 'wit_bot_audit', 'source_slug': 'wit_bot_audit_phase_1', 'effective_points': 10, 'awarded_points': 10, 'adjusted_points': None, 'created_at': pd.Timestamp('2026-08-19', tz='UTC'), 'note': 'score=0.8'},
        {'user_id': 21, 'source_kind': 'friend_invite', 'source_slug': 'friend_invite', 'effective_points': 100, 'awarded_points': 100, 'adjusted_points': None, 'created_at': pd.Timestamp('2026-08-19', tz='UTC'), 'note': '1 invite'},
    ])
    master = pd.DataFrame([{'user_id': 21, 'participant': 'P021'}])
    result = build_points_summary(awards, master).iloc[0]
    assert result['pts_survey'] == 0
    assert result['pts_wit_bot_audit'] == 10
    assert result['pts_friend_invite'] == 100
    assert result['total_points'] == 110
    assert result['reimbursement_usd'] == 11.0
```

- [ ] **Step 2: Run the dashboard test and confirm current copy/schema failure**

```bash
admin-dashboard/.venv/bin/python -m pytest admin-dashboard/tests/test_dashboard_data.py -q
```

Expected: new source/copy expectations fail before implementation.

- [ ] **Step 3: Update dashboard data and copy**

Keep `COALESCE(adjusted_points, awarded_points)` as the sole ledger value.
Ensure the displayed/exported table includes source slug and notes for audit
drill-down. Remove captions claiming `interview_signup`, `friend_invite`, or
`wit_bot_audit` are not credited yet, and remove the “separate earned audit”
warning. Label the dollar value final reimbursement.

- [ ] **Step 4: Run dashboard tests**

```bash
admin-dashboard/.venv/bin/python -m pytest admin-dashboard/tests/test_dashboard_data.py -q
admin-dashboard/.venv/bin/python -m py_compile admin-dashboard/app.py admin-dashboard/data.py
```

Expected: all tests and compilation pass.

- [ ] **Step 5: Commit dashboard reconciliation**

```bash
git add admin-dashboard/app.py admin-dashboard/data.py admin-dashboard/tests/test_dashboard_data.py
git commit -m "feat(reimbursement): finalize researcher ledger view"
```

### Task 7: Full local verification

**Files:**
- Verify only; fix failures in files owned by Tasks 1–6.

**Interfaces:**
- Consumes: completed backend, frontend, and dashboard changes.
- Produces: test/build evidence before any production mutation.

- [ ] **Step 1: Run backend verification**

From `WhoamI-Today-backend/adoorback`:

```bash
../venv/bin/python manage.py test surveys.tests_final_reimbursement surveys.tests_points
../venv/bin/python manage.py check
../venv/bin/python manage.py makemigrations --check
```

Expected: all commands exit 0 with no pending migrations.

- [ ] **Step 2: Run frontend verification**

From `WhoamI-Today-frontend`:

```bash
source ~/.nvm/nvm.sh
nvm use 18
npx craco test --watchAll=false src/routes/reimbursement/Reimbursement.test.tsx
npx craco build
```

Expected: tests and production build exit 0.

- [ ] **Step 3: Run the frontend dev server and verify no overlay**

Run the backend on port 8000 with `DB_HOST=localhost`, run the frontend dev
server, open `/reimbursement`, and inspect the browser console. Verify the page
at 375 px, 393 px, and 320 px with a representative local participant. Save
screenshots for visual inspection but do not add them to git.

- [ ] **Step 4: Run dashboard verification**

```bash
admin-dashboard/.venv/bin/python -m pytest admin-dashboard/tests/test_dashboard_data.py -q
admin-dashboard/.venv/bin/python -m py_compile admin-dashboard/app.py admin-dashboard/data.py
```

Expected: all checks exit 0.

### Task 8: Production dry run, apply, and persistence verification

**Files:**
- No source edits unless verification exposes a defect.

**Interfaces:**
- Consumes: production and Phase-1 restore database credentials from the existing gitignored admin-dashboard `.env`.
- Produces: persisted final `PointAward` ledger.

- [ ] **Step 1: Run the production dry run**

Load the existing DB and restore DB environment without printing secrets, then
run from `WhoamI-Today-backend/adoorback`:

```bash
../venv/bin/python manage.py finalize_reimbursement --phase1-database phase1_restore
```

Expected output includes cohort count, creates/updates/unchanged counts,
per-source totals, and per-participant totals, and contains `DRY RUN`.

- [ ] **Step 2: Review dry-run invariants**

Verify:

- LivelyOlive7 survey points equal 338;
- mango and Mower23 survey points equal 0;
- LivelyEagle5 survey points remain credited;
- WIT phase scores follow strict thresholds;
- ten standard interview emails match exactly once at 100 points;
- Rebecca matches once at 125 points;
- invite totals equal stored `invited_from_id` relationships;
- every cohort participant has two app-usage and two WIT rows projected;
- source totals sum to the cohort total.

- [ ] **Step 3: Apply the reconciliation transaction**

```bash
../venv/bin/python manage.py finalize_reimbursement --phase1-database phase1_restore --apply
```

Expected: one committed transaction and the same projected totals as dry run.

- [ ] **Step 4: Run a second dry run and direct ledger query**

Run the default dry run again. Expected: zero creates/updates and all intended
rows unchanged. Query `surveys_pointaward` by source and participant and verify
the persisted totals, approved adjustments, and absence of duplicate
non-survey keys.

### Task 9: Final CSV and obsolete reimbursement cleanup

**Files:**
- Create: `WhoamI-Today-data-analysis/reimbursement-audit/reimbursement_final_2026-08-19.csv`
- Delete: reimbursement CSVs/notebooks/checkpoint under `WhoamI-Today-data-analysis/deprecated/`
- Delete: all pre-final CSV/JSON files currently under `WhoamI-Today-data-analysis/reimbursement-audit/`

**Interfaces:**
- Consumes: persisted production ledger and raw WIT/invite/interview audit metadata.
- Produces: one final cohort CSV that reconciles exactly to production.

- [ ] **Step 1: Load the bundled spreadsheet runtime and required documentation**

Call the workspace dependency loader. Read `style_guidelines.md`,
`artifact_tool_docs/API_QUICK_START.md`, and
`domain_guidance/scientific_research.md` in full. Create a temporary working
directory and point its `node_modules` symlink at the loader-provided runtime.

- [ ] **Step 2: Mark the CSV authoring operation exactly once**

```bash
node container_tools/mark_artifact_operation_started.mjs --operation-kind create --expected-output-count 1 --output-format csv
```

- [ ] **Step 3: Query final export rows from production**

Read one row per cohort participant with typed fields for identity, survey
awarded/effective/excluded points, both app phases, both WIT scores/points,
invite count/points, interview status/points, researcher adjustments, total
points, dollars, and compact notes. Save the query result as a temporary JSON
input without credentials.

- [ ] **Step 4: Create and verify the final CSV with `@oai/artifact-tool`**

Build a single-sheet tabular artifact sorted by account ID. Inspect the full
header and representative rows for LivelyOlive7, mango, Mower23, Rebecca, a
friend inviter, and a zero-total participant. Scan for formula errors, render
the entire used range for visual verification, and export exactly one CSV to
the specified final path.

- [ ] **Step 5: Reconcile CSV totals**

Verify:

```text
sum(csv.total_final_points) == sum(database effective_points)
sum(csv.reimbursement_dollars) == sum(csv.total_final_points) / 10
each csv row total == sum(row source point columns)
```

Also verify exactly one row per cohort account and no unexpected email or ID
duplicates.

- [ ] **Step 6: Delete only obsolete reimbursement artifacts**

Use `apply_patch` deletion for the reimbursement-named files under
`deprecated/` and every dated artifact that the final CSV replaces under
`reimbursement-audit/`. Re-list both paths and prove unrelated deprecated files
remain.

- [ ] **Step 7: Commit the final audit artifact and cleanup**

```bash
git add reimbursement-audit/reimbursement_final_2026-08-19.csv deprecated/reimbursement.csv deprecated/reimbursement_w_email.csv deprecated/reimbursement-w-email.csv deprecated/reimbursement.ipynb deprecated/.ipynb_checkpoints/reimbursement-checkpoint.ipynb reimbursement-audit
git commit -m "data(reimbursement): publish final payout audit"
```

If ignored-path rules prevent staging the final CSV, update only the narrow
reimbursement-audit ignore rule required to track this one file; do not expose
credentials or other generated research data.

### Task 10: Final reconciliation report and deployment handoff

**Files:**
- Verify only.

**Interfaces:**
- Consumes: local commits, persisted production ledger, final CSV, and visual evidence.
- Produces: user-facing completion report and explicit deployment decision.

- [ ] **Step 1: Confirm repository state and commit scope**

Inspect `git status`, each task commit, and diffs against the pre-task state.
Verify unrelated dirty files are still present and unstaged/uncommitted by this
work.

- [ ] **Step 2: Re-run compact final checks**

Run the focused backend tests, frontend reimbursement test, frontend build,
dashboard test, final CSV reconciliation, and production no-op dry run again.
Record exact pass counts and totals.

- [ ] **Step 3: Report what the research owner must do**

Report final cohort/source totals, the final CSV location, special-case spot
checks, removed artifact scope, and any participants still eligible for an
interview. Ask for explicit permission before pushing or deploying backend and
frontend commits. Until that approval, clearly distinguish “production ledger
updated” from “participant page code deployed.”
