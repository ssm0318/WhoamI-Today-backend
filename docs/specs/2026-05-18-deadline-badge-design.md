# Deadline badge for "no late submissions" surveys — design

**Date authored:** 2026-05-18
**Status:** design only — no implementation yet
**Owner:** to be picked up in a separate session
**Scope:** UX-only change. No new backend fields. No new endpoints.

---

## Why

Some surveys have `allow_late=False` — once their window passes they
drop out of the index entirely with no recovery. Today there's no
visual signal that distinguishes these from late-acceptable surveys
in the available-now bucket. Result: participants who scroll past
`daily_base` or `week3_reflection` on a busy day don't realize the
window is finite, and we lose data we could have collected with a
nudge.

Today's `allow_late=False` inventory (per the live DB):

- `daily_base` × 28 scheduled rows (one per study day, 24-hour window)
- `weekly_*_reflection` × 4 (week 1–4, ~7-day windows)

SOTD entries are all `allow_late=True` after migration 0019, so the
SOTD hero on Discover doesn't need a deadline badge.

## Constraints (from the design conversation)

1. **No "today" wording.** The daily window rolls at 7am PT, so
   "today only" is ambiguous to a participant looking at the card at
   11pm — they actually have ~8 hours, not "until midnight." Every
   label uses concrete remaining-time or day-of-week.
2. **Zero perf cost.** No interval timers. No focus-refresh hooks.
   Compute remaining-time once at render. SWR's existing revalidate
   cycle handles staleness; if a participant keeps the page open for
   hours, the badge will be stale by however long — that's accepted.
3. **Coarse granularity is fine.** Hours, not minutes. Day-name for
   weekly, not "Xd Yh." Small errors are acceptable; participants
   figure it out from context.

## Badge

One orange chip across all surfaces:

- Background: `#FFE8D5`
- Text + border: `#C76A1F` (text), `#FFCBA0` (border)
- Border-radius 8px, padding `4px 10px`, font-weight 600, font-size 13px
- Leading clock emoji `⏰` (or `~/components/_common/icon` equivalent if
  we already have a clock SvgIcon)

Single color across all states — no red escalation under 1h, no
border-tinting on the parent card. Keeps the render rules trivial.

### Label format

```
formatRemainingDeadline(window_end, cadence, allow_late) → string | null
```

Returns `null` (caller renders nothing) when `allow_late === true`
**or** when the survey is not in the available-now bucket (no
deadline to display).

Otherwise:

| Cadence       | Label rule                                                   |
|---------------|--------------------------------------------------------------|
| `daily`       | `⏰ Xh left` where X = `max(1, ceil((expiry_ts - now_ts) / 3600))`. Min clamp to 1 so we never render `⏰ 0h left`. Once the survey window closes, the row drops out of available-now and the badge stops rendering anyway. |
| `weekly`      | `⏰ Closes <weekday>` — weekday from `window_end` (e.g. `Sun`, `Sat`). Same day-name even on the final day; we don't switch to hours. Localized to the viewer's `i18n.language`. |
| other cadences | `null` (don't render badge — biweekly/anytime/endpoint all `allow_late=True` today) |

The function lives in `WhoamI-Today-frontend/src/utils/surveyDeadline.ts`
(new file). Pure function, easily unit-testable.

## Surface map

### Surveys index (`/surveys`)

Each `SurveyIndexEntry` row in the available-now bucket calls
`formatRemainingDeadline(entry.window_end, entry.cadence,
allow_late)` and renders the badge inline next to the existing
cadence chip (or replaces the cadence chip when the deadline badge is
present — TBD by frontend implementer, both work).

Late-but-accepted and completed buckets never show the deadline
badge.

### Sidebar (`SideMenu.tsx`)

Surveys entry gets a small chip on the right showing the *count* of
currently-available `allow_late=False` rows: `⏰ 2 due` (or just `⏰
1` when N=1). When N=0, omit the chip entirely.

The count comes from one of:

- The existing `/api/surveys/index/` payload that the index page
  already fetches (compute count client-side after the fetch lands).
- A new field on the sidebar's existing endpoint if there is one
  (`/user/me/`? `/notifications/summary/`?) — implementer decides.

No timer. Recomputed when the sidebar mounts. SWR's revalidate cycle
keeps it fresh between mounts.

### Discover (`/discover`) and Share (`/share`)

Both pages render a "Today on WIT" / daily-check-in card sourced from
the same scheduled `daily_base` row. Same chip in the card header.

For Discover the SOTD hero **does not** get the badge (SOTD is
`allow_late=True`).

If either page renders the weekly reflection inline at some point,
the same chip applies.

## Component implementation

```tsx
// src/components/survey/DeadlineBadge.tsx (new)
import { Cadence } from '@models/survey';
import { formatRemainingDeadline } from '@utils/surveyDeadline';

interface Props {
  windowEnd: string | null; // ISO string from SurveyIndexEntry
  cadence: Cadence;
  allowLate: boolean;
}

export function DeadlineBadge({ windowEnd, cadence, allowLate }: Props) {
  const label = formatRemainingDeadline(windowEnd, cadence, allowLate);
  if (!label) return null;
  return <BadgeChip>⏰ {label}</BadgeChip>;
}
```

`BadgeChip` is the standard orange chip described above; lives in
`src/components/survey/DeadlineBadge.styled.ts` for consistency with
the project's `.styled.ts` convention.

## What the existing API needs to expose

Looking at `SurveyIndexEntrySerializer` today, the entry payload
already carries `window_end` and `cadence`. It does **not** carry
`allow_late`. Add it:

```python
# adoorback/surveys/serializers.py — SurveyIndexEntrySerializer
class Meta:
    fields = [
        ..., 'allow_late',  # new
    ]
```

That's the only backend change. Pure read-only field surface on an
existing model. No migration required.

## Verification

1. **Inventory:** confirm `daily_base` and `week*_reflection` are the
   only `allow_late=False` rows the participant sees, and SOTD rows
   are all `allow_late=True`.
2. **Stale rendering:** open `/surveys` at 11:55pm PT, leave open
   past 7am. The badge stays at "1h left" / "0h left" (clamped) until
   the SWR revalidate fires. Acceptable — confirms zero-timer design.
3. **Cross-surface:** chip renders consistently on `/surveys`,
   sidebar, `/discover` daily-checkin card, `/share` daily-checkin
   card.
4. **Localization:** `Closes Sun` vs `Closes 일` (Korean) — make sure
   `Intl.DateTimeFormat` or i18n weekday list is wired correctly.
5. **320px responsive:** chip fits on the right of a card at 320px
   without wrapping the title to two lines.

## What NOT to do

- **Don't add an interval timer.** Stated explicitly: zero perf cost.
- **Don't escalate colors / borders by remaining time.** Single chip,
  one color, one rule. Keeps the render rules trivial.
- **Don't render the badge on `allow_late=True` rows** — defeats the
  signal. The whole point is that `allow_late=False` is meaningfully
  different.
- **Don't say "today" anywhere in the label.** 7am PT rollover makes
  it ambiguous.
- **Don't surface the badge on completed / late-but-accepted
  buckets.** The deadline only matters for currently-available rows.

## Files this will likely touch

| File | Change |
|---|---|
| `adoorback/surveys/serializers.py` | Add `allow_late` to `SurveyIndexEntrySerializer` |
| `WhoamI-Today-frontend/src/models/survey.ts` | Add `allow_late: boolean` to `SurveyIndexEntry` |
| `WhoamI-Today-frontend/src/utils/surveyDeadline.ts` | New: `formatRemainingDeadline` pure function + tests |
| `WhoamI-Today-frontend/src/components/survey/DeadlineBadge.tsx` | New: chip component |
| `WhoamI-Today-frontend/src/components/survey/DeadlineBadge.styled.ts` | New: chip styled |
| `WhoamI-Today-frontend/src/routes/surveys/SurveysIndex.tsx` | Render `DeadlineBadge` in available-now rows |
| `WhoamI-Today-frontend/src/components/header/side-menu/SideMenu.tsx` | Render `⏰ N due` chip on the Surveys entry when N > 0 |
| `WhoamI-Today-frontend/src/components/share/SurveyOfTheDay.tsx` *(or whichever component hosts the daily-checkin card on Share / Discover)* | Render `DeadlineBadge` in the card header |
| `WhoamI-Today-frontend/src/i18n/locales/{en,ko}/translation.json` | `deadline_badge.hours_left`, `deadline_badge.closes_weekday`, `deadline_badge.sidebar_count` |
