# Final Reimbursement Ledger Design

**Date:** 2026-08-19

**Status:** Approved design, pending implementation

**Owner:** Research team

## Goal

Make the production reimbursement ledger the single source of truth for every
participant's final points. The participant page, researcher dashboard, and
final CSV must use the same materialized `PointAward` rows and reconcile to the
same total.

## Scope

This work finalizes five reimbursement sources:

1. audited survey responses;
2. phase-specific app usage;
3. phase-specific WIT bot work, including the boss quiz;
4. friend invitations; and
5. completed interviews.

It also replaces participant-facing preview language, preserves a Calendly
action for participants without a completed interview, produces one current
researcher CSV, and removes only obsolete reimbursement-related artifacts.
Unrelated historical analysis in `WhoamI-Today-data-analysis/deprecated/`
must remain untouched.

## Authoritative Data Model

`surveys_pointaward` is the authoritative final ledger. Each row retains the
original `awarded_points` and may use `adjusted_points` as the audited final
value. All totals use:

```text
effective_points = adjusted_points when present, otherwise awarded_points
```

The reimbursement API, participant page, admin dashboard, and final CSV must
sum the same materialized rows. No reimbursement source may exist only as a
frontend constant, browser-local preview, or compute-on-read synthetic award.

Non-survey sources use the existing uniqueness rule on
`(user, source_kind, source_slug)`. Reconciliation is idempotent: rerunning it
updates the intended award rather than inserting duplicates.

## Participant Cohort

The reimbursement cohort is account IDs 8 through 87, excluding the replaced
account 64, plus replacement account 114. Related invitees may fall outside
this range; a non-staff invitee still counts when its `invited_from_id` points
to a cohort participant.

## Final Scoring Rules

### Surveys

- Start from every materialized survey award's effective points.
- Preserve researcher adjustments and their audit notes.
- A survey determined not to have been answered in good faith receives zero
  points even if it was submitted or marked complete.
- Preserve the approved exclusions:
  - all survey credit is zero for `mango`;
  - all survey credit is zero for `Mower23`;
  - LivelyOlive7's responses 352, 398, 401, 405, and 544 receive zero,
    producing 338 effective survey points.
- LivelyEagle5 remains credited because its proposed exclusion was not
  approved.
- Legacy positive-point responses must be materialized or explicitly matched
  to an already-awarded scheduled opportunity before the ledger is declared
  complete. No synthetic survey points may be added only during API reads.

### App Usage

App usage remains a separate source from WIT bot/boss-quiz credit.

- Full phase engagement: 50 points.
- Partial phase engagement: 20 points.
- No qualifying engagement: 0 points.
- Phase 1 must be evaluated from the restored Phase-1 database where the live
  database no longer has complete Phase-1 behavior.
- Phase 2 must be evaluated from the current production database.
- Every participant receives a materialized Phase-1 and Phase-2 outcome,
  including zero-point rows with an explanatory note.

The existing engagement criteria remain the scoring definition; this work
does not redesign those behavioral thresholds.

### WIT Bot and Boss Quiz

The boss quiz is part of the phase-specific WIT bot award, not a separate
source and not part of app-usage points.

For each phase:

- determine the version from the participant's crossover group;
- read the highest recorded boss-quiz score for that version, considering the
  attempt history and final score;
- award 50 points when the best score is strictly greater than 85%;
- award 10 points when the best score is strictly greater than 60% and not
  greater than 85%;
- award 0 points otherwise or when no boss-quiz attempt exists.

Audit engagement and missing-feature counts are stored in the award note for
transparency but do not add a second award. Every participant receives one
materialized WIT-bot row per phase. Existing compute-on-read WIT awards based
only on `last_missing_count == 0` are removed so the API cannot disagree with
the ledger or CSV.

### Friend Invitations

- Count each non-staff account whose `invited_from_id` identifies a cohort
  participant.
- Award 100 points per invited account.
- Cap the aggregate friend-invite award at 500 points.
- Store one materialized `friend_invite` award per participant.
- The note records the eligible invite count and the IDs/usernames used for
  the calculation so the result is auditable.
- Reciprocal invitation records count independently when each account's
  `invited_from_id` identifies the other account; no unsupported inference is
  added beyond the stored relationship.

### Interviews

Award 100 points to the participants matching these confirmed interview
emails:

- `jennylninh@gmail.com`
- `siddhub2001@gmail.com`
- `yixin7@uw.edu`
- `pinkchloeko@gmail.com`
- `ole2@uw.edu`
- `sai.yakumo770@gmail.com`
- `superlegos113@gmail.com`
- `anh.n.personal@gmail.com`
- `sklein3@uw.edu`
- `aishani.rao22@gmail.com`

Award 125 points to `rebecca.laba@gmail.com`.

Email matching is case-insensitive after trimming whitespace. A completed
interview has one materialized `interview_signup` award and no signup action.
A participant without the award sees a 100-point interview opportunity linked
to `https://calendly.com/jaewonkim/60min`.

### Conversion

Ten points equal one US dollar. The API returns the exact dollar amount in
cents from the final effective-point total.

## Reconciliation Workflow

Add one backend management command that calculates the intended final ledger
and supports two modes:

- default dry run: show proposed creates, updates, unchanged rows, and totals;
- `--apply`: write all changes in one database transaction.

The command must:

1. resolve the cohort and validate that expected accounts and interview emails
   match exactly one account;
2. verify or materialize missing survey awards without overriding approved
   researcher adjustments;
3. calculate Phase-1 and Phase-2 app-usage outcomes from their correct data
   sources;
4. calculate WIT/boss-quiz awards from stored version-specific state;
5. calculate friend-invite awards from `invited_from_id`;
6. calculate interview awards from the approved email list;
7. upsert all non-survey source rows, including zero-point outcomes;
8. print source and cohort reconciliation totals; and
9. abort the transaction on missing required data, ambiguous account matches,
   or a failed reconciliation invariant.

The production run is followed by a fresh read that verifies persisted rows,
per-source totals, per-participant totals, and the approved survey exclusions.

## Reimbursement API

`reimbursement_state_for_user` returns only materialized ledger rows plus
currently available actions. It must not synthesize legacy survey or WIT-bot
points at read time after finalization.

The response keeps `provisional_total` only if required for backward
compatibility, but its value equals the final adjusted total. New copy and code
must refer to the amount as the participant's reimbursement total, not a
preview, draft, provisional amount, or estimate.

The API must provide enough interview state for the frontend to distinguish:

- interview completed and credited; or
- interview incomplete, with a 100-point opportunity and Calendly URL.

## Participant Page

The production `/reimbursement` route is the only participant-facing
reimbursement experience. Browser-local allocation previews and preview-only
fallbacks are removed from the production path.

The page contains:

1. final point total and dollar total;
2. a concise data-quality policy;
3. credited items, grouped or labeled by source;
4. zero-point/not-credited items with their audit note when useful; and
5. the interview signup action for participants without interview credit.

Required policy copy:

> Surveys determined not to have been answered in good faith were not
> credited, even when the survey was completed.

Remove all copy containing “preview,” “draft,” “provisional,” “rough
estimate,” or “may change after study review.” The page must not imply that
the research team is still allocating completed-study points.

The interview action uses the exact Calendly URL and opens as a normal
external link. Completed interview participants do not see the action.

English and Korean translation files must remain structurally aligned. Korean
copy conveys the same finalized meaning rather than retaining preview text.

## Researcher Dashboard

The reimbursement tab reads the same materialized ledger as the API. Remove
claims that WIT, interview, or invite sources are “awarded later,” and remove
the warning that the dashboard does not represent a full earned audit.

The dashboard shows and exports every source kind, including zero outcomes
where relevant. Its cohort total must match the final CSV and the sum of all
participant API totals.

## Final CSV

Create one current CSV in
`WhoamI-Today-data-analysis/reimbursement-audit/` named with the finalization
date. It contains one row per cohort participant and these fields:

- participant/account ID;
- username;
- email;
- user group;
- survey awarded and effective points;
- survey points excluded by audit;
- app-usage Phase 1 and Phase 2 points;
- WIT/boss-quiz Phase 1 and Phase 2 best scores and points;
- eligible friend count and friend-invite points;
- interview completion and interview points;
- other researcher-adjustment points;
- total final points;
- reimbursement dollars;
- compact audit notes.

Derived totals reconcile to ledger rows and use the 10-points-per-dollar
conversion. The export is sorted by account ID and includes all cohort
participants, including zero-total participants.

## Obsolete Artifact Removal

Delete only reimbursement-related historical artifacts:

- reimbursement CSVs and reimbursement notebooks under
  `WhoamI-Today-data-analysis/deprecated/`, including their reimbursement
  checkpoint;
- every dated CSV/JSON currently under
  `WhoamI-Today-data-analysis/reimbursement-audit/` that the final CSV
  replaces.

Preserve all unrelated files in the broader `deprecated/` directory. Do not
delete behavioral notebooks, schemas, survey exports, credentials, tracking
files, or other historical research material.

## Tests

Backend tests cover:

- strict boss-score thresholds and highest-attempt selection;
- crossover group-to-phase/version mapping;
- WIT audit details without extra points;
- invite counting, cap behavior, and non-staff filtering;
- interview matching, Rebecca's exception, and idempotent upsert;
- preservation of survey `adjusted_points` and notes;
- zero-point materialization;
- API totals using materialized rows only;
- dry-run versus transactional apply behavior; and
- reconciliation failures.

Frontend tests cover:

- finalized copy with no preview/provisional language;
- good-faith policy copy;
- final point and dollar totals;
- completed interview hiding the Calendly action;
- incomplete interview showing the exact Calendly link;
- adjusted survey awards displaying zero and the audit note; and
- English/Korean translation-key parity.

Data/export tests cover:

- exactly one cohort row per participant;
- source-column sums matching ledger source totals;
- row totals matching source columns;
- dollar conversion;
- approved exclusion spot checks; and
- no obsolete reimbursement artifact remaining.

## Verification and Release

Before production mutation:

1. run focused backend and frontend tests;
2. run the full backend checks and migration check;
3. run the frontend production build;
4. run the reconciliation command in dry-run mode against production and the
   Phase-1 restore database;
5. review proposed per-source totals and representative participants.

After approval to apply the production mutation:

1. run reconciliation with `--apply` in a transaction;
2. query the ledger again to verify persistence;
3. generate the final CSV from the persisted ledger;
4. reconcile CSV, dashboard, and API totals;
5. deploy backend and frontend only with explicit push/deployment approval;
6. open the real participant page at 375 px, 393 px, and 320 px;
7. verify there is no error overlay and that the Calendly action works; and
8. spot-check accounts covering each special rule.

No push, deployment, merge, or production-server code rollout occurs without
explicit user approval. The database reconciliation itself is a separate
production mutation and is performed only after a successful dry run.

## User Responsibilities

After implementation and verified reconciliation, the research owner needs to:

- review the dry-run summary before the production apply;
- approve the production database apply;
- approve backend/frontend push or deployment;
- monitor or close Calendly availability if no further interviews should be
  accepted; and
- use the generated final CSV as the payout working file.
