# Deadline-badge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render an orange `⏰ Xh left` / `⏰ Closes <weekday>` chip on `allow_late=False` survey rows so participants see the deadline at a glance; add a count chip on the sidebar Surveys entry.

**Architecture:** One new backend serializer field (`allow_late` on `SurveyIndexEntrySerializer`), one pure TypeScript utility (`formatRemainingDeadline`), one React component (`DeadlineBadge`), two integration points (`SurveysIndex` row, `SideMenu` entry). Zero interval timers, zero focus-refresh hooks — compute at render only; SWR's existing revalidate cycle is the freshness mechanism.

**Tech Stack:** Django REST Framework + DRF serializer (backend), React 18 + TypeScript 4.9 + styled-components 5.3 + SWR (frontend), Jest + Testing Library (test runner present, used by other components).

**Design spec:** `WhoamI-Today-backend/docs/specs/2026-05-18-deadline-badge-design.md`

**Scope check:** Discover and Share pages don't currently surface `daily_base`; they only show SOTD (which is `allow_late=True` and gets no badge). So no work is required on those pages today — the spec mentioned them but the existing components don't host the relevant survey card. Noted in Task 6 for confirmation during implementation; skip if confirmed.

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `WhoamI-Today-backend/adoorback/surveys/serializers.py` | modify | Add `allow_late` field to `SurveyIndexEntrySerializer.Meta.fields` |
| `WhoamI-Today-backend/adoorback/surveys/tests_views_index.py` | modify (or create if missing) | New test verifying entry payload contains `allow_late` |
| `WhoamI-Today-frontend/src/models/survey.ts` | modify | Add `allow_late: boolean` to `SurveyIndexEntry` |
| `WhoamI-Today-frontend/src/utils/surveyDeadline.ts` | create | Pure `formatRemainingDeadline(windowEnd, cadence, allowLate, now?)` function |
| `WhoamI-Today-frontend/src/utils/surveyDeadline.test.ts` | create | Unit tests for the pure function |
| `WhoamI-Today-frontend/src/components/survey/DeadlineBadge.tsx` | create | Chip component that calls the util and renders orange chip |
| `WhoamI-Today-frontend/src/components/survey/DeadlineBadge.styled.ts` | create | Styled chip definition |
| `WhoamI-Today-frontend/src/routes/surveys/SurveysIndex.tsx` | modify | Render `DeadlineBadge` inside the available-now row |
| `WhoamI-Today-frontend/src/components/header/side-menu/SideMenu.tsx` | modify | Render `⏰ N due` count chip on the Surveys entry |
| `WhoamI-Today-frontend/src/i18n/locales/en/translation.json` | modify | New `deadline_badge.*` keys |
| `WhoamI-Today-frontend/src/i18n/locales/ko/translation.json` | modify | Korean translations of same keys |

---

## Task 1: Backend — expose `allow_late` on the survey-index entry payload

**Files:**
- Modify: `adoorback/surveys/serializers.py` — `SurveyIndexEntrySerializer.Meta.fields`
- Test: `adoorback/surveys/tests_views_index.py` (create if missing, otherwise extend)

- [ ] **Step 1: Locate the current serializer and confirm field surface**

```bash
grep -n "class SurveyIndexEntrySerializer" /Users/jaewonk/Documents/active/whoami-code/WhoamI-Today-backend/adoorback/surveys/serializers.py
```

Expected: one match. Read the surrounding `class Meta: fields = [...]` block.

- [ ] **Step 2: Write the failing test**

Create or open `adoorback/surveys/tests_views_index.py`. Add this test (adapt existing imports / setup helpers if a test file already exists):

```python
from datetime import date
from django.test import TestCase
from rest_framework.test import APIClient

from account.models import User
from surveys.models import (
    ScheduledSurvey, Survey,
)


class SurveyIndexAllowLateFieldTest(TestCase):
    """Survey index entry payload must include allow_late so the frontend
    can decide whether to render the deadline badge without an extra
    round-trip."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='deadline_badge_test', email='dbt@x.x', password='x',
        )
        self.survey = Survey.objects.create(
            slug='_deadline_test_daily',
            title='Deadline test daily',
            friend_visible=False,
        )
        ScheduledSurvey.objects.create(
            cadence='daily', sequence_index=9001,
            survey=self.survey,
            window_start=date.today(),
            window_end=date.today(),
            allow_late=False,
        )

    def test_entry_payload_contains_allow_late(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        resp = client.get('/api/surveys/index/')
        self.assertEqual(resp.status_code, 200)
        # Pull every entry across buckets so the test doesn't depend on
        # which bucket the row landed in.
        all_entries = (
            resp.data['available_now']
            + resp.data['late_but_accepted']
            + resp.data['completed']
        )
        match = next(
            (e for e in all_entries if e['survey']['slug'] == '_deadline_test_daily'),
            None,
        )
        self.assertIsNotNone(match, 'test scheduled row missing from index')
        self.assertIn('allow_late', match)
        self.assertEqual(match['allow_late'], False)
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /Users/jaewonk/Documents/active/whoami-code/WhoamI-Today-backend/adoorback
source ~/.zshrc 2>/dev/null
DB_HOST=localhost python manage.py test surveys.tests_views_index.SurveyIndexAllowLateFieldTest -v 2
```

Expected: `FAIL` with `KeyError: 'allow_late'` or `AssertionError: 'allow_late' not found`.

- [ ] **Step 4: Add the field**

Open `adoorback/surveys/serializers.py`. Find the `SurveyIndexEntrySerializer.Meta.fields` list and add `'allow_late'` (the field already exists on the `ScheduledSurvey` model; this is purely a serializer-surface addition):

```python
class SurveyIndexEntrySerializer(serializers.ModelSerializer):
    # ... existing field declarations ...

    class Meta:
        model = ScheduledSurvey
        fields = [
            'id', 'cadence', 'sequence_index',
            'window_start', 'window_end',
            'allow_late',  # NEW — needed by frontend DeadlineBadge
            'survey', 'bucket',
            'user_answered', 'submitted_at',
            'redirect_url',
        ]
```

- [ ] **Step 5: Run test to verify it passes**

```bash
DB_HOST=localhost python manage.py test surveys.tests_views_index.SurveyIndexAllowLateFieldTest -v 2
```

Expected: `OK`. Also run `python manage.py check` — must be clean.

- [ ] **Step 6: Commit**

```bash
cd /Users/jaewonk/Documents/active/whoami-code/WhoamI-Today-backend
git add adoorback/surveys/serializers.py adoorback/surveys/tests_views_index.py
PATH="/Users/jaewonk/.nvm/versions/node/v18.20.5/bin:$PATH" git commit -m "feat(surveys): expose allow_late on survey-index entry payload

Adds the allow_late field to SurveyIndexEntrySerializer so the
frontend can render the DeadlineBadge (\"⏰ Xh left\" / \"Closes Sun\")
on rows where late submissions aren't accepted, without a separate
fetch per row."
```

---

## Task 2: Frontend — extend the `SurveyIndexEntry` type

**Files:**
- Modify: `src/models/survey.ts`

- [ ] **Step 1: Read the current type**

```bash
grep -n "interface SurveyIndexEntry" /Users/jaewonk/Documents/active/whoami-code/WhoamI-Today-frontend/src/models/survey.ts
```

Expected: one match around line 221.

- [ ] **Step 2: Add the field**

Open `src/models/survey.ts`. Find `interface SurveyIndexEntry { ... }` and add `allow_late: boolean;` alongside the other top-level fields (next to `window_end` keeps it logically grouped):

```typescript
export interface SurveyIndexEntry {
  id: number;
  cadence: Cadence;
  sequence_index: number;
  window_start: string;        // ISO date
  window_end: string | null;   // null = open-ended (anytime, endpoint)
  allow_late: boolean;         // NEW — drives DeadlineBadge rendering
  survey: { slug: string; title_en: string; title_ko: string };
  bucket: Bucket;
  user_answered: boolean;
  submitted_at: string | null;
  redirect_url: string;
}
```

- [ ] **Step 3: Type-check**

```bash
cd /Users/jaewonk/Documents/active/whoami-code/WhoamI-Today-frontend
source ~/.nvm/nvm.sh && nvm use 18
npx tsc --noEmit 2>&1 | grep -v node_modules | head -10
```

Expected: no errors in our files. (Spotify SDK type errors are pre-existing and ignored.)

- [ ] **Step 4: Commit**

```bash
git add src/models/survey.ts
PATH="/Users/jaewonk/.nvm/versions/node/v18.20.5/bin:$PATH" git commit -m "feat(surveys): add allow_late to SurveyIndexEntry type

Matches the new field exposed by the backend in SurveyIndexEntrySerializer."
```

---

## Task 3: Frontend — `formatRemainingDeadline` pure utility (TDD)

**Files:**
- Create: `src/utils/surveyDeadline.ts`
- Test: `src/utils/surveyDeadline.test.ts`

- [ ] **Step 1: Write the failing test file**

Create `src/utils/surveyDeadline.test.ts`:

```typescript
import { formatRemainingDeadline } from './surveyDeadline';

// Fixed reference moment for all tests: 2026-05-18 22:00:00 UTC.
// Daily windows in this app close at 7am Pacific the *next* morning per
// the scheduling layer. For test simplicity we treat the day boundary as
// midnight UTC of `window_end + 1` (matches what ScheduledSurvey.window_end
// stores: a date, not a datetime). The util receives window_end as an
// ISO date string and the caller's `now` (so tests can pin it).
const NOW = new Date('2026-05-18T22:00:00Z');

describe('formatRemainingDeadline', () => {
  describe('returns null (no badge)', () => {
    test('when allowLate is true', () => {
      expect(
        formatRemainingDeadline('2026-05-18', 'daily', true, NOW),
      ).toBeNull();
    });

    test('when windowEnd is null', () => {
      expect(
        formatRemainingDeadline(null, 'anytime', false, NOW),
      ).toBeNull();
    });

    test('when cadence is anytime / biweekly / endpoint', () => {
      expect(formatRemainingDeadline('2026-05-31', 'biweekly', false, NOW)).toBeNull();
      expect(formatRemainingDeadline('2026-05-31', 'anytime', false, NOW)).toBeNull();
      expect(formatRemainingDeadline('2026-05-31', 'endpoint', false, NOW)).toBeNull();
    });
  });

  describe('daily cadence', () => {
    test('shows whole hours remaining when far from expiry', () => {
      // window_end = today; expiry = end-of-day. ~2h remaining as a
      // sanity baseline (UTC midnight is the reference; downstream
      // localization can shift this — we accept stale-by-minutes).
      const label = formatRemainingDeadline('2026-05-18', 'daily', false, NOW);
      expect(label).toMatch(/^\d+h left$/);
    });

    test('clamps minimum to 1h', () => {
      // 10 minutes before midnight UTC of window_end → still renders "1h left"
      const tenMinBeforeBoundary = new Date('2026-05-18T23:50:00Z');
      const label = formatRemainingDeadline(
        '2026-05-18', 'daily', false, tenMinBeforeBoundary,
      );
      expect(label).toBe('1h left');
    });

    test('rounds up partial hours', () => {
      // 3h 15m before boundary → ceil → 4h left
      const partial = new Date('2026-05-18T20:45:00Z');
      const label = formatRemainingDeadline(
        '2026-05-18', 'daily', false, partial,
      );
      expect(label).toBe('4h left');
    });

    test('returns null after expiry', () => {
      // 1 hour past the boundary — the row should have dropped out of
      // available_now anyway, but the util must not crash with negative
      // hours.
      const past = new Date('2026-05-20T00:00:00Z');
      expect(
        formatRemainingDeadline('2026-05-18', 'daily', false, past),
      ).toBeNull();
    });
  });

  describe('weekly cadence', () => {
    test('shows closing weekday name', () => {
      // window_end = Sunday May 24, 2026 → "Closes Sun"
      const label = formatRemainingDeadline(
        '2026-05-24', 'weekly', false, NOW,
      );
      expect(label).toBe('Closes Sun');
    });

    test('keeps weekday label even on final day', () => {
      // Same-day expiry → still "Closes Sun" (spec: never switch to hours
      // for weekly).
      const sundayMorning = new Date('2026-05-24T10:00:00Z');
      const label = formatRemainingDeadline(
        '2026-05-24', 'weekly', false, sundayMorning,
      );
      expect(label).toBe('Closes Sun');
    });

    test('returns null after weekly window closes', () => {
      const monday = new Date('2026-05-25T10:00:00Z');
      expect(
        formatRemainingDeadline('2026-05-24', 'weekly', false, monday),
      ).toBeNull();
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/jaewonk/Documents/active/whoami-code/WhoamI-Today-frontend
source ~/.nvm/nvm.sh && nvm use 18
CI=true npx craco test --watchAll=false src/utils/surveyDeadline.test.ts 2>&1 | tail -20
```

Expected: all tests fail with `Cannot find module './surveyDeadline'` or similar.

- [ ] **Step 3: Implement the utility**

Create `src/utils/surveyDeadline.ts`:

```typescript
import { Cadence } from '@models/survey';

// Returns the label that goes inside the DeadlineBadge chip, or null when
// no badge should be rendered. Pure function — no DOM, no timers, no
// network. Caller supplies `now` for testability; defaults to wall clock.
//
// Rules (mirrors docs/specs/2026-05-18-deadline-badge-design.md):
//   - allowLate=true  → null (the badge only signals hard deadlines)
//   - windowEnd=null  → null (no deadline to display)
//   - cadence not in {daily, weekly} → null
//   - daily : "Xh left" where X = max(1, ceil((expiry - now) / 3600s)).
//             expiry = 00:00:00 UTC of (windowEnd + 1 day).
//   - weekly: "Closes <weekday>" using a short English weekday (Sun/Mon/…).
//             Same label even on the final day.
//   - past expiry → null (defensive; the row should have dropped out of
//                          available-now upstream).
//
// The localization layer applies its own translation via the i18n key
// `deadline_badge.hours_left` / `deadline_badge.closes_weekday`; this
// function returns the raw English form for tests / fallbacks.
export function formatRemainingDeadline(
  windowEnd: string | null,
  cadence: Cadence,
  allowLate: boolean,
  now: Date = new Date(),
): string | null {
  if (allowLate) return null;
  if (!windowEnd) return null;
  if (cadence !== 'daily' && cadence !== 'weekly') return null;

  // ScheduledSurvey.window_end is a DATE (no time) — the window closes
  // at the start of the *next* calendar day. Convert to the expiry
  // instant by adding one day to the window_end midnight.
  const endDate = new Date(`${windowEnd}T00:00:00Z`);
  const expiry = new Date(endDate.getTime() + 24 * 60 * 60 * 1000);
  if (expiry.getTime() <= now.getTime()) return null;

  if (cadence === 'weekly') {
    return `Closes ${WEEKDAY_SHORT[endDate.getUTCDay()]}`;
  }

  // daily
  const hoursLeft = Math.max(
    1,
    Math.ceil((expiry.getTime() - now.getTime()) / (60 * 60 * 1000)),
  );
  return `${hoursLeft}h left`;
}

const WEEKDAY_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
CI=true npx craco test --watchAll=false src/utils/surveyDeadline.test.ts 2>&1 | tail -10
```

Expected: `Tests: <N> passed, <N> total`.

- [ ] **Step 5: Commit**

```bash
git add src/utils/surveyDeadline.ts src/utils/surveyDeadline.test.ts
PATH="/Users/jaewonk/.nvm/versions/node/v18.20.5/bin:$PATH" git commit -m "feat(surveys): formatRemainingDeadline pure util for deadline badge

Returns the badge label (\"Xh left\" daily, \"Closes <weekday>\" weekly)
or null when no badge should render. Computed at render only — no
timers, no focus refresh, accepted to be stale-by-minutes between SWR
revalidates per the design constraint."
```

---

## Task 4: Frontend — `DeadlineBadge` component

**Files:**
- Create: `src/components/survey/DeadlineBadge.tsx`
- Create: `src/components/survey/DeadlineBadge.styled.ts`

- [ ] **Step 1: Create the styled chip**

Create `src/components/survey/DeadlineBadge.styled.ts`:

```typescript
import styled from 'styled-components';

// Warm-orange chip used to flag surveys with allow_late=False. Color
// palette is intentionally NOT pulled from the design-system Colors
// object because these tokens (#FFE8D5 / #FFCBA0 / #C76A1F) don't yet
// exist there; if more usages land we should centralize. See the
// deadline-badge design spec for rationale.
export const Chip = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #ffe8d5;
  color: #c76a1f;
  border: 1px solid #ffcba0;
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 13px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
`;
```

- [ ] **Step 2: Create the component**

Create `src/components/survey/DeadlineBadge.tsx`:

```typescript
import { useTranslation } from 'react-i18next';

import { Cadence } from '@models/survey';
import { formatRemainingDeadline } from '@utils/surveyDeadline';

import { Chip } from './DeadlineBadge.styled';

interface Props {
  windowEnd: string | null;
  cadence: Cadence;
  allowLate: boolean;
}

// Localized renderer of the deadline label. Returns null when there is
// no deadline to display, so callers can include it unconditionally:
//
//   <DeadlineBadge
//     windowEnd={entry.window_end}
//     cadence={entry.cadence}
//     allowLate={entry.allow_late}
//   />
//
// The util returns an English label like "5h left" or "Closes Sun";
// we translate it via deadline_badge.hours_left / .closes_weekday so
// Korean reads as e.g. "5시간 남음" / "일요일에 마감".
export function DeadlineBadge({ windowEnd, cadence, allowLate }: Props) {
  const { t } = useTranslation('translation', { keyPrefix: 'deadline_badge' });
  const raw = formatRemainingDeadline(windowEnd, cadence, allowLate);
  if (!raw) return null;

  const hoursMatch = raw.match(/^(\d+)h left$/);
  if (hoursMatch) {
    return <Chip>⏰ {t('hours_left', { hours: Number(hoursMatch[1]) })}</Chip>;
  }
  const weekdayMatch = raw.match(/^Closes (\w+)$/);
  if (weekdayMatch) {
    return (
      <Chip>
        ⏰ {t('closes_weekday', { weekday: t(`weekday_short.${weekdayMatch[1]}`) })}
      </Chip>
    );
  }
  // Fallback — should not happen given the util's contract, but render
  // the raw English so we don't silently swallow.
  return <Chip>⏰ {raw}</Chip>;
}
```

- [ ] **Step 3: Type-check**

```bash
npx tsc --noEmit 2>&1 | grep -v node_modules | head -10
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add src/components/survey/DeadlineBadge.tsx src/components/survey/DeadlineBadge.styled.ts
PATH="/Users/jaewonk/.nvm/versions/node/v18.20.5/bin:$PATH" git commit -m "feat(surveys): DeadlineBadge component

Localized chip used to mark allow_late=False surveys. Wraps the
formatRemainingDeadline util + the i18n bundle keys; returns null
when no badge should render so callers can include it unconditionally."
```

---

## Task 5: Frontend — i18n bundle keys

**Files:**
- Modify: `src/i18n/locales/en/translation.json`
- Modify: `src/i18n/locales/ko/translation.json`

- [ ] **Step 1: Find the `surveys` block in each translation file**

```bash
grep -n '"surveys": {' /Users/jaewonk/Documents/active/whoami-code/WhoamI-Today-frontend/src/i18n/locales/en/translation.json
grep -n '"surveys": {' /Users/jaewonk/Documents/active/whoami-code/WhoamI-Today-frontend/src/i18n/locales/ko/translation.json
```

We add `deadline_badge` as a sibling to `surveys` (top-level namespace), not nested under it, so the `keyPrefix: 'deadline_badge'` lookup in the component works.

- [ ] **Step 2: Add the en bundle**

Open `src/i18n/locales/en/translation.json`. Add a top-level `deadline_badge` block. A natural location is just before or after the `surveys` block:

```json
    "deadline_badge": {
        "hours_left": "{{hours}}h left",
        "closes_weekday": "Closes {{weekday}}",
        "weekday_short": {
            "Sun": "Sun",
            "Mon": "Mon",
            "Tue": "Tue",
            "Wed": "Wed",
            "Thu": "Thu",
            "Fri": "Fri",
            "Sat": "Sat"
        },
        "sidebar_count_one": "{{count}} due",
        "sidebar_count_other": "{{count}} due"
    },
```

- [ ] **Step 3: Add the ko bundle**

Open `src/i18n/locales/ko/translation.json`. Mirror the same structure:

```json
    "deadline_badge": {
      "hours_left": "{{hours}}시간 남음",
      "closes_weekday": "{{weekday}} 마감",
      "weekday_short": {
        "Sun": "일",
        "Mon": "월",
        "Tue": "화",
        "Wed": "수",
        "Thu": "목",
        "Fri": "금",
        "Sat": "토"
      },
      "sidebar_count_one": "마감 임박 {{count}}건",
      "sidebar_count_other": "마감 임박 {{count}}건"
    },
```

- [ ] **Step 4: Validate the JSON parses**

```bash
node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/en/translation.json'))" && echo "en OK"
node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/ko/translation.json'))" && echo "ko OK"
```

Both must print `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/i18n/locales/en/translation.json src/i18n/locales/ko/translation.json
PATH="/Users/jaewonk/.nvm/versions/node/v18.20.5/bin:$PATH" git commit -m "feat(surveys): i18n keys for deadline badge

en + ko strings for the \"Xh left\" / \"Closes <weekday>\" chip and the
sidebar count chip."
```

---

## Task 6: Frontend — render `DeadlineBadge` in `SurveysIndex` rows

**Files:**
- Modify: `src/routes/surveys/SurveysIndex.tsx`

- [ ] **Step 1: Re-read `renderEntry`**

```bash
grep -n "renderEntry\|RowHeader\|CadenceChip" /Users/jaewonk/Documents/active/whoami-code/WhoamI-Today-frontend/src/routes/surveys/SurveysIndex.tsx | head -10
```

Look at the existing `renderEntry` function to plan the insertion. The chip should live inside `RowHeader` next to `CadenceChip`, so the row keeps its current shape.

- [ ] **Step 2: Add the import**

At the top of `src/routes/surveys/SurveysIndex.tsx`, add (kept alphabetical with existing component imports):

```typescript
import { DeadlineBadge } from '@components/survey/DeadlineBadge';
```

- [ ] **Step 3: Render the badge in `renderEntry`**

In the `renderEntry` body, inside the `<RowHeader>` JSX, insert the badge right after the existing `<CadenceChip>`. Only render in the `available_now` bucket — the badge has no meaning for late or completed entries.

```tsx
<RowHeader>
  <Typo type="title-medium" color="BLACK">
    {pickLocalized(entry.survey.title_en, entry.survey.title_ko)}
  </Typo>
  <CadenceChip>{t(`cadence.${entry.cadence}`)}</CadenceChip>
  {bucket === 'available_now' && (
    <DeadlineBadge
      windowEnd={entry.window_end}
      cadence={entry.cadence}
      allowLate={entry.allow_late}
    />
  )}
</RowHeader>
```

- [ ] **Step 4: Run the dev build**

```bash
npx craco build 2>&1 | grep -E "Failed|error TS|Compiled" | head -10
```

Expected: `Compiled successfully.` Any TS / ESLint errors must be addressed before commit.

- [ ] **Step 5: Visual verification at 393px and 320px**

```bash
# Dev server should already be running per the launch.json config.
# If not, start it; preview-list will show it.
```

Hit `/surveys` in the running preview. Verify:
- daily_base row shows `⏰ Xh left`
- weekly_*_reflection row shows `⏰ Closes <weekday>`
- biweekly / anytime rows show no badge
- The chip wraps onto the next line gracefully at 320px (no clipping)

Take screenshots at 393 and 320; attach to the commit description if convenient.

- [ ] **Step 6: Commit**

```bash
git add src/routes/surveys/SurveysIndex.tsx
PATH="/Users/jaewonk/.nvm/versions/node/v18.20.5/bin:$PATH" git commit -m "feat(surveys): DeadlineBadge in /surveys available-now rows

Renders the orange \"⏰ Xh left\" / \"Closes <weekday>\" chip alongside
the cadence chip on currently-available rows where allow_late=False.
The component returns null on rows that don't need a badge (allow_late=
True, or in the late/completed buckets), so the row layout stays the
same for every other survey."
```

---

## Task 7: Frontend — sidebar count chip

**Files:**
- Modify: `src/components/header/side-menu/SideMenu.tsx`

- [ ] **Step 1: Re-read the sidebar's existing data fetches**

```bash
grep -n "useSWR\|SIDE_MENU_LIST\|surveys" /Users/jaewonk/Documents/active/whoami-code/WhoamI-Today-frontend/src/components/header/side-menu/SideMenu.tsx | head -10
```

The sidebar already does one SWR call (`/user/version-switch-request/me/`). Adding `/surveys/index/` here is fine; SWR will dedupe with the SurveysIndex page when the user just visited it.

- [ ] **Step 2: Add imports**

At the top of `src/components/header/side-menu/SideMenu.tsx`, add the styled chip (the full `DeadlineBadge` component is for per-row cards; the sidebar needs the chip shape alone) plus the survey-index fetcher:

```typescript
import useSWR from 'swr';

import { Chip as DeadlineChip } from '@components/survey/DeadlineBadge.styled';
import { getSurveyIndex } from '@utils/apis/survey';
```

(`useSWR` may already be imported in `SideMenu.tsx` for the version-switch fetch — if so, don't add a duplicate. `getSurveyIndex` matches the existing usage in `SurveysIndex.tsx`; verify path with `grep -n "getSurveyIndex" src/utils/apis/survey.ts`.)

- [ ] **Step 3: Add the SWR fetch + count derivation + a second translation hook**

The existing `t` in `SideMenu` is bound to `keyPrefix: 'home.header.side_menu'`, so we can't use it for the `deadline_badge.*` keys. Add a second `useTranslation` call alongside. Then add the SWR fetch + count derivation, alongside the existing `useSWR('/user/version-switch-request/me/', ...)` call:

```typescript
// Existing `t` stays as-is (for menu item labels). Add a second
// translation hook keyed to the deadline_badge namespace so the
// sidebar count chip can localize without leaking the prefix.
const { t: tDeadline } = useTranslation('translation', {
  keyPrefix: 'deadline_badge',
});

// Count of currently-available rows with allow_late=False — drives the
// "X due" chip on the Surveys entry. Shared SWR key with SurveysIndex
// so opening the sidebar shortly after visiting /surveys does not
// trigger an extra fetch (revalidate-on-focus is the freshness
// mechanism, not a sidebar-specific call).
const { data: surveyIndex } = useSWR('/surveys/index/', getSurveyIndex);
const dueCount = surveyIndex
  ? surveyIndex.available_now.filter((e) => !e.allow_late).length
  : 0;
```

- [ ] **Step 4: Render the chip on the Surveys row**

Find the `visibleItems.map((menu) => ...)` block. Wrap the inner `Layout.FlexRow` so the Surveys entry includes the chip on the right when `dueCount > 0`:

```tsx
{visibleItems.map((menu) => (
  <button type="button" key={menu.key} onClick={handleClickMenu(menu)}>
    <Layout.FlexRow
      gap={6}
      alignItems="center"
      style={{ justifyContent: 'space-between', width: '100%' }}
    >
      <Layout.FlexRow gap={6} alignItems="center">
        <EmojiItem
          emojiString={menu.emoji}
          size={20}
          bgColor="TRANSPARENT"
          outline="TRANSPARENT"
        />
        <Typo type="head-line">{t(menu.key)}</Typo>
      </Layout.FlexRow>
      {menu.key === 'surveys' && dueCount > 0 && (
        <DeadlineChip>
          ⏰ {tDeadline('sidebar_count', { count: dueCount })}
        </DeadlineChip>
      )}
    </Layout.FlexRow>
  </button>
))}
```

- [ ] **Step 5: Run the dev build**

```bash
npx craco build 2>&1 | grep -E "Failed|error TS|Compiled" | head -10
```

Expected: `Compiled successfully.`

- [ ] **Step 6: Visual verification**

Open the sidebar in the running preview (hamburger menu). Verify:
- Surveys entry shows `⏰ N due` on the right when N > 0
- Chip is absent when N === 0 (verify by completing all daily/weekly entries or by inspecting the SWR cache)
- Other entries (My profile, Settings) render unchanged

- [ ] **Step 7: Commit**

```bash
git add src/components/header/side-menu/SideMenu.tsx
PATH="/Users/jaewonk/.nvm/versions/node/v18.20.5/bin:$PATH" git commit -m "feat(surveys): sidebar count chip for due surveys

Adds \"⏰ N due\" to the Surveys sidebar entry when at least one
currently-available row has allow_late=False. Shares the existing
SWR cache so opening the sidebar after visiting /surveys doesn't
trigger an extra fetch."
```

---

## Task 8: Confirm Discover / Share daily-checkin surfaces (likely no-op)

**Files:**
- Read: `src/routes/discover/Discover.tsx`, `src/routes/discover/DiscoverW.tsx`
- Read: `src/components/share/SurveyOfTheDay.tsx`
- Read: `src/routes/share/Share.tsx` (or whichever file hosts the Share page)

- [ ] **Step 1: Grep for any direct daily_base reference**

```bash
cd /Users/jaewonk/Documents/active/whoami-code/WhoamI-Today-frontend
grep -rn "daily_base\|daily-checkin\|daily_checkin" src/ 2>&1 | grep -v node_modules
```

- [ ] **Step 2: Decide**

- If a component renders `daily_base` directly (i.e. a card whose data is a `SurveyIndexEntry` with `cadence==='daily'` and `allow_late===false`), add `<DeadlineBadge ... />` to that card the same way Task 6 did for the index row, then commit.
- If no such component exists (the expected outcome based on the current code — SOTD is the only featured-survey card and it's `allow_late=True`), document the no-op and skip:

```bash
git commit --allow-empty -m "chore(surveys): no Discover/Share work needed for deadline badge

Verified: Discover renders the SOTD hero only, Share renders the SOTD
card only. Both source from /api/surveys/sotd/ which is allow_late=
True, so neither surface hosts an allow_late=False card. The /surveys
index + sidebar count chip (shipped in earlier commits) are the only
surfaces needed."
```

---

## Task 9: End-to-end verification

**Files:** none

- [ ] **Step 1: Full backend check**

```bash
cd /Users/jaewonk/Documents/active/whoami-code/WhoamI-Today-backend/adoorback
source ~/.zshrc 2>/dev/null
DB_HOST=localhost python manage.py check 2>&1 | tail -3
DB_HOST=localhost python manage.py test surveys -v 1 2>&1 | tail -5
```

Expected: `System check identified no issues (0 silenced).` and `OK` from the test run.

- [ ] **Step 2: Full frontend build**

```bash
cd /Users/jaewonk/Documents/active/whoami-code/WhoamI-Today-frontend
source ~/.nvm/nvm.sh && nvm use 18
npx craco build 2>&1 | tail -10
```

Expected: `Compiled successfully.`

- [ ] **Step 3: Dev server compile check**

Verify the dev server has no error overlay. If a preview server is registered:

```bash
# In the running dev server's webpack output (preview_logs or similar)
# look for "webpack compiled successfully"; no TS / ESLint errors.
```

- [ ] **Step 4: Live verification @ 393px**

In the preview viewport, visit `/surveys` as a test user. Verify:
- daily_base row shows `⏰ Xh left`
- weekly_*_reflection row (if scheduled this week) shows `⏰ Closes <weekday>`
- biweekly / anytime / endpoint rows show no badge
- Late-but-accepted bucket: no badges
- Completed bucket: no badges

Open the sidebar — verify the `⏰ N due` chip appears next to Surveys.

- [ ] **Step 5: Live verification @ 320px**

Resize to 320px. Verify:
- The badge doesn't overflow or clip
- The row title doesn't get pushed to two lines unnecessarily
- The sidebar entry remains readable

- [ ] **Step 6: Console / network sanity**

In the running browser preview, check:
- No new console errors / warnings related to the badge
- No new failed network requests
- One `GET /api/surveys/index/` fetch on `/surveys` (and one on sidebar open, deduped by SWR cache if recent)

- [ ] **Step 7: Final summary commit (optional)**

If you'd like a clean trailer commit summarizing the feature, you can do:

```bash
git commit --allow-empty -m "chore(surveys): deadline badge feature complete

Surfaces:
  - /surveys index: per-row orange \"⏰ Xh left\" / \"Closes <weekday>\" chip
  - Sidebar Surveys entry: \"⏰ N due\" count chip
Design: docs/specs/2026-05-18-deadline-badge-design.md
Implementation plan: docs/plans/2026-05-18-deadline-badge-implementation.md"
```

This is optional — the task-by-task commits above are sufficient.

---

## Notes on commit hygiene

- Every commit message in this plan omits the `Co-Authored-By: Claude` trailer per the project-wide `CLAUDE.md` rule.
- The husky pre-commit hook spawns `sh` with node-10 in PATH; the explicit `PATH="/Users/jaewonk/.nvm/versions/node/v18.20.5/bin:$PATH"` prefix on `git commit` is required so lint-staged picks up the node-18 prettier binary.
- All commits land on `release/final-research`; no push is done as part of this plan — the user runs `git push` themselves when ready.
