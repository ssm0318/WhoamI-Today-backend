# wit_bot Onboarding — Design Spec

**Date:** 2026-05-03
**Status:** Pending design review (do not start implementation)
**Branch:** `feat/wit-bot-onboarding` off `origin/release/final-research`
**Scope:** WhoamI-Today-backend (primary), WhoamI-Today-frontend (chat UI extensions)

---

## TL;DR

`WITty` (the persona of `wit_bot`) onboards each participant through every feature in their *current* version, twice per participant — once at study start (May 4 00:00 PST) and again after the auto-swap (May 18 00:00 PST). Onboarding has three phases:

1. **Kickoff** — linear, button-triggered, ~6 turns. Includes 3 quizzes + setup checks (push notif, friend ≥1, widget screenshot).
2. **Audit loop** — user-triggered. Bot queries DB + analytics-mirror events to compute a feature engagement report, and offers walkthrough / list / "audit me later" branches.
3. **End-of-version final quiz** — multi-select identification of in-version features (with absurd decoys). 80% to pass. Unlimited retries.

Outside these phases the bot is silent. Verification is mostly automatic; one screenshot (home-screen widgets) is reviewed async by admin via a Django admin extension. Push notif and friend-≥1 are auto-checked from existing models.

**New backend pieces:** `OnboardingScreenshot` model, `OnboardingEvent` model, `WitBotConversationState.progress` JSON field, predicate registry, engine rewrite of `wit_bot_engine.py` from beta loop into intent state machine, Django admin extension for screenshot review.

**New frontend pieces:** `bot_payload` schema additions (multi-select, deep-link card, screenshot-request), parallel `POST /api/onboarding-events/` whenever frontend logs to Firebase Analytics for a tracked feature, button rendering for new payload kinds.

---

## Goals

- Communicate study mechanics (window, swap, mandatory periods, survey schedule) interactively, not as a wall of text.
- Drive feature exploration without being annoying. The bot is silent unless asked.
- Maintain a per-participant audit trail for reimbursement eligibility.
- Re-onboard cleanly after the version swap, preserving prior progress.
- Personality: full-weird, sincerely-cringy, charmingly self-aware.

## Non-goals

- Auto-verify screenshots via OCR or vision models. Admin reviews.
- Replace pre-study/daily surveys (the existing `surveys/` app handles them).
- Notification-mute UX (tabled — TBD later).
- Push WITty messages outside FCM's existing chat delivery.

---

## Personality — WITty 🦉

WITty is the bot's persona. Voice is **deadpan-cringe-dad-joke**: sincerely awkward, references its own awkwardness, says *"ha. ha. ha."* after its own bad jokes, never breaks character, never sarcastic. Mascot emoji: 🦉.

Voice samples:
- *"Hi there! I'm WITty ha. ha. ha. that was a joke. \*adjusts non-existent tie\*"*
- *"You did it. I am proud of you in a way that may or may not be measurable."*
- *"oh no — admin says the widget shot only had 2 widgets. could you redo? you can do this. i believe in you."*
- *"i would never lie to you. (unless it was a joke. but mostly never.)"*
- *"sometimes i just think about owls. is that weird?"*

WITty's full copy lives under `chat/wit_bot/copy/` and is reviewed in spec review (see Open Questions).

---

## Flow

### Phase 0 — Welcome card (lives in the chat at all times)

The existing `_post_welcome` (in `chat/wit_bot_engine.py`) is replaced by a state-aware welcome card. Card label/copy depends on participant + study state:

| Window | Visible content | CTA button | Click action |
|---|---|---|---|
| Before May 4 00:00 PST | "I'll be here when the study starts on May 4 — see you then 👋" | (none) | n/a |
| May 4 00:00 PST → kickoff not yet started for V1 | "Time to onboard." | **Start onboarding** | enter `kickoff` for `current_ver` |
| Kickoff started, not finished | "We were in the middle of something." | **Resume onboarding** | resume from `current_intent` |
| Kickoff finished, audit not 100% | "Feature audit time." | **Run audit** | enter `audit` |
| Audit 100% but final quiz not passed | "Boss quiz time." | **Take the boss quiz** | enter `final_quiz` |
| V1 fully complete, before May 18 | "see you May 18 for the swap" | (none) | n/a |
| May 18 00:00 PST → V2 swap, V2 onboarding not started | "version Q (or W) is live." | **Start version Q (or W) onboarding** | enter `kickoff` for new version |
| All done | "you survived. proud of you." | (none) | n/a |

The card refreshes:
- on every user message into the bot's room
- on the bot's room being opened (frontend tells the backend via room-open beacon)

No proactive push notifications from WITty itself. Existing FCM delivery handles message-level pushes.

### Phase 1 — Kickoff (linear, ~6 turns)

Triggered by tapping **Start onboarding** on the welcome card. Sequence:

1. **Welcome turn.** WITty intro voice line + "ok let's go" button.
2. **Quiz 1** — *Study Requirements* (multi-select). See full text below.
3. **Quiz 2** — *Version swap timing* (single-select). See full text below.
4. **Quiz 3** — *Where surveys live* (single-select). See full text below.
5. **Setup checks**, in order:
   - **Push notif**: `CustomFCMDevice.objects.filter(user=user, active=True).exists()`. If False → earnest enable-asks (see voice block below). Re-checks on next user message in the bot's room.
   - **Friend ≥1**: count from `Connection`-derived `User.friends`. If 0 → "go add one, tap **Done** when ready" → re-checks on tap; loops.
   - **Widget screenshot**: bot prompts for one image with all 3 widgets visible. Submission unblocks immediately. `OnboardingScreenshot(status='pending')` row created. Admin reviews via Django admin extension; signal triggers DM to participant on approve/reject.
6. **Wrap turn.** "kickoff complete. tap **Run audit** anytime. `faq` for frequently asked things. `wit?` if you're bored."

#### Setup-check voice (push-notif-off path)

> "ok so. your push notifications are off. that's a problem because i need to send you survey reminders and study alerts. without those, your data isn't complete and you can't get reimbursed for the part of the study that depended on them. it's not personal. \*adjusts nothing\* could you turn them on for the duration of the study? if a specific notification gets too annoying, dm me — admin will sort something out. thank you for understanding. truly. screenshot when on."

#### Friend-min voice (count = 0)

> "you don't have a friend yet on the app. add at least one — they don't have to be a study participant — and tap **Done**. i'll keep watching."

### Phase 2 — Audit loop (user-triggered)

User taps **Run audit**. Bot:

1. Reads `current_ver` from User.
2. Iterates predicate registry filtered by version.
3. Returns a card showing ✓ engaged list + ⏳ not-yet list + counts.
4. Asks: *"how do you want to play this?"* with three buttons:
   - **Walk me through them** → `walkthrough` intent. Bot iterates ⏳ list one at a time. For each, sends a `deep_link_card` with a brief description + 3 buttons: **Take me there** (deep-link) · **Mark as done** (self-report → creates `OnboardingEvent`) · **Skip for now**.
   - **Just give me the list** → bot sends the ⏳ list as a flat list of `deep_link_card`s with **Take me there** buttons. Returns to idle.
   - **I'll explore more, audit me later** → bot returns to idle.

User can re-trigger audit any time by tapping the welcome card's **Run audit** button or typing `audit`. Bot never re-prompts on its own.

### Phase 3 — End-of-version final quiz

When audit shows 100% engagement on the current version's required set, the welcome card flips its CTA to **Take the boss quiz** the next time the user opens the chat. Tapping enters `final_quiz` intent. (Bot does not push a chat message on its own — silence rule preserved.)

**Quiz 4** (multi-select, see full text below) — Identify all features in YOUR version. Each option falls into one of three buckets:

- **Correct to select:** real features present in the participant's *current* version. This includes both version-only features (e.g. `checkin_battery` for W) AND cross-version features that exist in both (e.g. `daily_question_answer`).
- **Correct to omit (distractor):** real features present *only* in the *other* version (e.g. `checkin_post_create` is W's distractor, `friend_list_view` is Q's distractor).
- **Correct to omit (absurd):** features that don't exist anywhere (`Reels`, `video filters`, `2-minute timer`, `voice channel`, `karaoke mode`).

Quiz options are generated dynamically from the predicate registry: select-real-in-version + omit-real-in-other-version + omit-from-the-shared-absurd-bank.

Pass = ≥80% accuracy across all options (each option scored individually: correct-select counts +1, correct-omit counts +1, wrong counts 0). Fail → bot reveals which were wrong with a one-line explanation per error, allows retry. **Unlimited retries.**

On pass: WITty congrats + "you officially survived version W" + sticker. State `version_w.completed = True`. Bot returns to idle.

### Phase 4 — Version swap (May 18 00:00 PST)

Existing management command `swap_versions.py` runs at 00:00 PST May 18 (admin-triggered cron). Each participant's `current_ver` flips. WITty is silent until participant opens chat. Welcome card now shows **Start version Q onboarding** (or W, depending on the swap direction). Tap → re-runs Phase 1.

**Skip rules in V2 kickoff:**
- Push notif setup: skipped if V1 progress shows `push_notif == 'ok'` AND a live `CustomFCMDevice.active` re-check still passes. If re-check fails, re-prompt.
- Friend ≥1 setup: skipped if user still has ≥1 friend (live re-check).
- Widget screenshot: skipped if V1 progress shows `widget_screenshot.status` in `{approved, pending}`. (`pending` is treated as "good enough" to not re-collect — admin will resolve it independently of V2 flow.)
- Quizzes 1–3: skipped if passed in V1 (`quiz_X.correct == true` for single-select; `quiz_1.score >= 0.8` for multi-select). If failed in V1 they re-run in V2 as a refresher. (Open Question: should they always re-run for reinforcement? See Open Questions.)

V2 has its own audit + final quiz scoped to V2's feature set. V1's `progress` block is preserved untouched.

---

## Quizzes (full text — copy is editable in spec review)

### Quiz 1 — Study requirements (multi-select)

**Prompt:** *"hello. quiz time. select EVERYTHING you need to do during the study. i'll tell you what you got right after."*

**Options** (in randomized order on render):

| Label | Correct? | Notes |
|---|---|---|
| Pre-study survey | ✓ | already past (May 2) — flag as already-done in reveal if user completed it |
| Daily surveys | ✓ | every day, May 4–31 |
| Weekly survey | ✓ | per `ScheduledSurvey` cadence |
| Biweekly survey | ✓ | per `ScheduledSurvey` cadence |
| Anytime / situational surveys | ✓ | optional triggers |
| Endpoint survey | ✓ | end of study |
| Daily app use May 4–7 | ✓ | mandatory window 1 |
| Daily app use May 18–21 | ✓ | mandatory window 2 (post-swap) |
| Push notifications on (whole study) | ✓ | needed for survey delivery |
| Widget added to home screen | ✓ | participation requirement |
| Add at least one friend on the app | ✓ | participation requirement |
| Win the lottery | ✗ | absurd |
| Befriend 3 pigeons | ✗ | absurd |
| Dance | ✗ | absurd |

**Reveal copy:** lists which they got right and wrong; for each missed correct one, one-line explanation. For absurd ones if selected: *"i appreciate the energy but no."*

### Quiz 2 — Version swap timing (single-select)

**Prompt:** *"when does your version swap happen?"*

| Label | Correct? |
|---|---|
| Midnight May 17 → 18 PST | ✓ |
| When we reach gemini season | ✗ |
| Tomorrow at lunch | ✗ |
| When WITty achieves enlightenment | ✗ |

**Reveal:** *"correct! you'll wake up on May 18 and the app will look different. you'll get the OTHER version. then May 18–21 is mandatory daily-use again. wild."*

### Quiz 3 — Where surveys live (single-select)

**Prompt:** *"where in the app can you find your surveys?"*

| Label | Correct? |
|---|---|
| Sidebar → "Surveys" button | ✓ |
| Pop-up that appears when one is due | ✗ |
| Settings → Surveys | ✗ |
| WITty's secret pocket dimension | ✗ |

**Reveal:** *"correct. tap the hamburger → Surveys. the list shows all available + completed surveys."* (deep-link button: **Take me there** → `/surveys`)

### Quiz 4 — Boss quiz: identify YOUR version's features (multi-select, end of audit)

**Prompt:** *"final boss. select everything that's in YOUR version (not the other one, not made up by me). need ≥80% to pass. unlimited retries."*

**Options (Version W example — populated dynamically from registry):**

Real + in W (must select):
- Mood / battery / thought / song check-ins
- Friends list with chips
- Daily Digest tab
- Subscribe bell on profiles
- Private comments
- Reactions with count visible
- Browse mode
- Close-friends filter on chat
- Pinned check-ins on profile
- Persona chips
- Daily question / question sending
- Photo of the Day / Mission of the Day / Question of the Day
- View as
- Apply privacy to past posts
- Non-public account option

Real + only-in-Q (correct to omit):
- Image+text check-in stories (horizontal scroll)
- "My" tab in bottom nav
- Q-style simplified posts (no private comments)

Absurd (correct to omit):
- Reels
- Video filters
- 2-minute timer
- Voice channel
- Karaoke mode

**Reveal on fail:** for each wrong selection, one-line explanation (e.g. "image+text stories are version Q only — you don't have those rn").

**Reveal on pass:** *"you survived. \*hands over participation gold star\* nothing else from me until \[next milestone\]."*

For Version Q the same quiz runs with the lists swapped — Q-real are correct, W-real are distractors, absurd are absurd.

---

## State model

Extend existing `WitBotConversationState` (`chat/models.py:206–220`):

```python
class WitBotConversationState(AdoorTimestampedModel):
    user = OneToOneField(User, on_delete=CASCADE)
    current_intent = CharField(max_length=32, default='idle')
    step = PositiveSmallIntegerField(default=0)
    progress = JSONField(default=dict, blank=True)  # NEW
```

Add a migration for `progress` (nullable JSON, default `{}`). No NOT NULL constraint.

`progress` shape:

```jsonc
{
  "version_w": {
    "kickoff": {
      "welcomed": true,
      "quiz_1": {"submitted": true, "selected": ["...", "..."], "score": 0.92},
      "quiz_2": {"correct": true, "attempts": 1},
      "quiz_3": {"correct": false, "attempts": 2},
      "push_notif": "ok",
      "friend_min": "ok",
      "widget_screenshot": {"status": "pending", "screenshot_id": 12}
    },
    "audit_runs": [{"timestamp": "...", "engaged_count": 8, "missing_count": 4}],
    "walkthroughs": ["check_in_battery", "private_comments"],
    "final_quiz": {"attempts": [{"score": 0.62}, {"score": 0.84}], "passed": true},
    "completed": true
  },
  "version_q": { ... }
}
```

**Intents** (`current_intent` values):
`idle`, `kickoff_welcome`, `kickoff_quiz_1`, `kickoff_quiz_2`, `kickoff_quiz_3`, `kickoff_push`, `kickoff_friend`, `kickoff_widget`, `kickoff_complete`, `audit`, `walkthrough`, `final_quiz`, `faq`, `escalated`.

`step` is per-intent. For `walkthrough`, step is the index into the missing-features list. For `kickoff_quiz_1` etc., step is the within-quiz position (presenting → reveal → done).

---

## New models

### `OnboardingScreenshot`

```python
class OnboardingScreenshot(AdoorTimestampedModel):
    user = ForeignKey(User, on_delete=CASCADE)
    version = CharField(max_length=10, choices=VERSION_CHOICES)
    kind = CharField(max_length=20, choices=[
        ('widget', 'Widgets'),
        # extensible — keep enum so admin can filter
    ])
    message = ForeignKey('chat.Message', on_delete=CASCADE)
    status = CharField(max_length=20, choices=[
        ('pending', 'Pending review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='pending')
    reviewed_by = ForeignKey(User, null=True, blank=True, on_delete=SET_NULL,
                            related_name='onboarding_reviews')
    reviewed_at = DateTimeField(null=True, blank=True)
    rejection_reason = CharField(max_length=200, blank=True, default='')

    class Meta:
        indexes = [models.Index(fields=['user', 'kind', 'status'])]
```

Follow the project's 3-step migration pattern (per `MIGRATION_GUIDELINES.md`): nullable add → backfill if needed → constrain. Initial creation = single migration since all fields are nullable or defaulted. No data backfill needed (new table).

### `OnboardingEvent`

```python
class OnboardingEvent(AdoorTimestampedModel):
    user = ForeignKey(User, on_delete=CASCADE)
    version = CharField(max_length=10, choices=VERSION_CHOICES)
    event_key = CharField(max_length=64)
    payload = JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'event_key'])]
```

Frontend POSTs to mirror Firebase Analytics events for features that don't otherwise touch the DB. Server fills `version` from `user.current_ver`.

---

## Predicate registry (strawman — needs review)

Each feature has a `FeaturePredicate` instance:

```python
@dataclass
class FeaturePredicate:
    feature_key: str
    versions: set[str]                       # {'version_w'}, {'version_q'}, or both
    kind: Literal['db', 'event', 'self_report', 'screenshot']
    is_engaged: Callable[[User], bool]
    display_name: str
    description: str                         # 1-line for walkthrough cards
    deep_link: str | None                    # frontend route
```

Registered in `chat/wit_bot/predicates/registry.py`. Audit iterates by version.

### Both versions

| feature_key | kind | predicate (sketch) | display_name | deep_link |
|---|---|---|---|---|
| `daily_question_view` | event | `OnboardingEvent` k=`daily_question_viewed` | View today's daily question | `/questions` |
| `daily_question_answer` | DB | `Response.objects.filter(author=user).exists()` | Answer a daily question | `/questions` |
| `question_send` | DB | `Question.objects.filter(creator=user).exists()` *(TBD: confirm field name)* | Send a question to a friend | `/questions` |
| `comment_create` | DB | `Comment.objects.filter(author=user).exists()` | Comment on a post | (any post) |
| `chat_message_send` | DB | `Message.objects.filter(sender=user).exclude(receiver__username='wit_bot').exists()` | Send a chat message | `/chats` |
| `mission_of_day` | DB | `Note.objects.filter(author=user, mission_mode=True).exists()` *(TBD: field)* | Post for Mission of the Day | `/notes/new?missionMode=true` |
| `photo_of_day` | DB | `Note.objects.filter(author=user, photo_kind=True).exists()` *(TBD: field)* | Post a Photo of the Day | `/share` |
| `discover_visit` | event | k=`discover_opened` | Open Discover / Daily Digest | `/discover` |
| `view_as` | event | k=`view_as_opened` | Use "View as…" on profile | profile |
| `apply_privacy_past` | event | k=`apply_past_posts_visibility` | Apply privacy change to past posts | settings |
| `non_public_account_set` | DB | `User.objects.filter(pk=user.pk, account_visibility='non_public').exists()` *(TBD: field)* | Configure non-public account | settings |
| `survey_complete_first` | DB | `SurveyResponse.objects.filter(user=user).exists()` | Complete first survey | `/surveys` |
| `subscribe_bell_use` | DB | `Subscription.objects.filter(subscriber=user).exists()` | Tap subscribe-bell on a friend | profile |
| `share_tab_visit` | event | k=`share_tab_opened` | Open Share tab | `/share` |
| `nth_degree_view` | event | k=`profile_nth_degree_seen` | See an Nth-degree connection on a profile | profile |

### Version W only

| feature_key | kind | predicate | display_name | deep_link |
|---|---|---|---|---|
| `checkin_battery` | DB | `CheckInComponentEntry.objects.filter(user=user, component='battery').exists()` | Set a battery check-in | `/check-in/edit` |
| `checkin_mood` | DB | same with `component='mood'` | Set a mood check-in | `/check-in/edit` |
| `checkin_thought` | DB | same with `component='thought'` | Set a thought check-in | `/check-in/edit` |
| `checkin_song` | DB | same with `component='song'` | Set a song check-in | `/check-in/edit` |
| `checkin_pin` | DB | `CheckInComponentEntry.objects.filter(user=user, is_pinned=True).exists()` *(TBD: field)* | Pin a check-in to profile | `/check-in/edit` |
| `friend_list_view` | event | k=`friend_list_opened` | Open Friends list | `/friends` |
| `private_comment_create` | DB | `Comment.objects.filter(author=user, is_private=True).exists()` *(TBD: field)* | Post a private comment | post page |
| `reaction_emoji` | DB | `Reaction.objects.filter(user=user).exists()` | React with an emoji | post page |
| `like_post` | DB | `Like.objects.filter(user=user).exists()` | Like a post | post page |
| `ping_checkin` | DB | TBD — locate Ping/Poke model | Ping a friend's check-in | friend profile |
| `browse_mode` | event | k=`browse_mode_toggled` | Toggle browsing mode | session-start prompt |
| `chat_close_friends_filter` | event | k=`chat_close_filter_used` | Use Close Friends filter in chat | `/chats` |
| `persona_set` | DB | TBD — Persona storage location | Set profile chips (Persona) | profile edit |
| `granular_subscription` | DB | `Subscription.objects.filter(subscriber=user, subscription_type__isnull=False).exists()` | Granularly subscribe to a friend | profile |
| `social_battery_5min` | event | k=`chat_5min_battery_prompt_handled` | 5-min chat → social battery prompt | n/a (auto) |

### Version Q only

| feature_key | kind | predicate | display_name | deep_link |
|---|---|---|---|---|
| `checkin_post_create` | DB | TBD — `CheckInPost` model location (likely under `check_in/` or `note/`) | Post an image+text check-in | `/share` |
| `stories_scroll` | event | k=`checkin_stories_scrolled` | Scroll the horizontal check-in stories | feed home |
| `feed_scroll` | event | k=`public_feed_scrolled` | Scroll the public feed | `/feed` (TBD route) |
| `posts_simplified_create` | DB | `Note.objects.filter(author=user, version_q_simplified=True).exists()` *(TBD: field)* | Post a Q-style simplified post | `/share` |
| `my_tab_visit` | event | k=`my_tab_opened` | Open My tab | `/my` (TBD route) |
| `discover_highlight_question` | event | k=`discover_highlight_question_seen` | See a Highlight Question in Discover | `/discover` |

### TBDs in this strawman (need user input or further grep)

- exact field name for mission/photo flags on `Note`
- exact field name for `is_private` on `Comment`
- exact field/flag for "is pinned" on `CheckInComponentEntry`
- account-visibility field on `User`
- ping/poke model location
- where `Persona` is stored (own model? `User` field? join table?)
- Q's `/feed` and `/my` route confirmations + the model behind Q's "scrollable public feed"

---

## Engine architecture

### Module layout

Replace existing `chat/wit_bot.py` and `chat/wit_bot_engine.py` (beta loop deleted) with:

```
chat/
  wit_bot/
    __init__.py
    persona.py              # voice helpers + sticker bank
    state.py                # state read/write + intent transitions
    engine.py               # handle_user_message dispatch
    welcome_card.py         # state-aware welcome card builder
    intents/
      __init__.py
      kickoff.py
      audit.py
      walkthrough.py
      final_quiz.py
      faq.py
      escape.py
      idle.py               # "i'm not sure what you mean" recovery
    predicates/
      __init__.py
      base.py               # FeaturePredicate dataclass
      registry.py           # PREDICATE_REGISTRY, predicates_for_version()
      common.py             # both-version predicates
      version_w.py
      version_q.py
    copy/
      __init__.py
      welcome.py
      quizzes.py            # all 4 quiz texts + reveals
      faq.py
      easter_eggs.py
      voice.py              # WITty voice fragments (jokes, transitions)
```

Existing imports of `chat.wit_bot` (mostly `is_wit_bot(user)` helper) update to import from `chat.wit_bot.persona` or similar.

### Dispatch logic

```python
def handle_user_message(message: Message) -> list[Message]:
    state = get_or_create_state(message.sender)
    handler = INTENT_HANDLERS.get(state.current_intent, idle_handler)
    return handler(state, message)
```

Each intent handler:
- accepts `(state, incoming_message) -> list[Message]`
- mutates and saves `state` (intent + step + progress)
- returns 0+ outgoing messages for the bot to post
- handles off-script input by re-prompting without advancing `step`

**Off-script handling within a flow.** During quiz / setup-check intents, if the user types a top-level command (`faq`, `audit`, `wit?`, `help`), the active handler responds with: *"i'm in the middle of \[current step name\]. tap an option please. (you can do `faq` etc. when we're done.)"* — does not exit the intent. **Exception:** typing `Call admin` always escalates immediately regardless of intent, since it's a safety hatch.

### Welcome-card refresh

`welcome_card.py:build_welcome_card(user) -> bot_payload` — pure function. Called:
- on bot-room first creation (existing `provision_wit_bot_rooms` flow)
- on every user message into the bot's room (replaces the old card if state changed)
- on bot-room open (new lightweight beacon endpoint `POST /api/chat/rooms/<id>/seen/` triggers a check)

The card is a single `Message` row with `content=''` and `bot_payload={...}`. Updates replace by deleting + re-inserting (simpler than mutating `bot_payload`). Use a sentinel `event_type='wit_welcome_card'` so the room only ever has one of these.

### `bot_payload` schema additions

Today (`chat/wit_bot_engine.py:51-61`) only renders `kind: "card"` with buttons. Add:

#### `kind: "multi_select"`

```jsonc
{
  "kind": "multi_select",
  "title": "Select all that apply",
  "options": [
    {"label": "Pre-study survey", "value": "pre_study"},
    {"label": "Daily surveys", "value": "daily_survey"}
  ],
  "submit_label": "Submit",
  "min_selection": 0,
  "max_selection": null,
  "shuffle": true
}
```

Frontend: render checkbox list + Submit button. On submit, POST a Message:

```jsonc
{
  "content": "",
  "bot_payload": {
    "kind": "multi_select_response",
    "intent": "kickoff_quiz_1",
    "selected": ["pre_study", "daily_survey"]
  }
}
```

Backend engine reads `bot_payload.selected` in the matching intent handler.

#### `kind: "deep_link_card"`

```jsonc
{
  "kind": "deep_link_card",
  "title": "Try the Daily Question",
  "subtitle": "Answer one and send one",
  "buttons": [
    {"label": "Take me there", "action": "deep_link", "route": "/questions"},
    {"label": "Mark as done", "action": "reply", "payload": "self_report:question_send"},
    {"label": "Skip", "action": "reply", "payload": "skip:question_send"}
  ]
}
```

Frontend: `deep_link` action calls `navigate(route)`. `reply` sends a Message with `bot_payload={"payload": "self_report:question_send"}` — engine creates an `OnboardingEvent` for `self_report` and proceeds.

#### `kind: "screenshot_request"`

```jsonc
{
  "kind": "screenshot_request",
  "title": "Show me your home screen",
  "subtitle": "All 3 widgets visible in one shot please",
  "kind_id": "widget"
}
```

Frontend renders an image picker. On submit, POSTs a normal `Message` with image attachment +
```jsonc
"bot_payload": {"kind": "screenshot_response", "kind_id": "widget"}
```

Backend creates `OnboardingScreenshot(message=msg, kind='widget', status='pending')`.

### `POST /api/onboarding-events/`

```
POST /api/onboarding-events/
{
  "event_key": "browse_mode_toggled",
  "payload": {"new_state": "social"}
}
```

Authed. Server fills `user`, `version` (from `user.current_ver`).

Frontend wrapper: `logOnboardingEvent(eventKey, payload?)` in `src/utils/apis/onboardingEvents.ts`. Wherever `firebase.analytics().logEvent(...)` is called for a tracked feature, mirror with `logOnboardingEvent(...)`. Fire-and-forget; swallow errors silently.

Initial mirror sites (from feature flag map):
- `BROWSE_MODE` toggle
- `CHAT_CLOSE_FRIENDS_FILTER` activate
- "View as" open on profile
- Daily Digest / Discover open
- Friends list open (W) / `/feed` open (Q)
- Stories scroll (Q only)
- "Apply privacy to past posts" save
- Profile-list-feed two-type-feed switch (TBD which UI element)

---

## Admin extension for screenshot review

`OnboardingScreenshot` registered in Django admin (`/api/secret/`) with a custom changelist:

- Thumbnail column (clickable to fullsize via inline modal or new tab)
- Username, version, kind, status, submitted_at columns
- Sidebar filter: status, version, kind
- Inline action buttons "Approve" / "Reject" — Reject opens an inline reason textarea
- Bulk approve action for fast batch review
- Pending count badge in the admin nav header (links to `?status=pending`)

State change signal:

```python
@receiver(post_save, sender=OnboardingScreenshot)
def notify_participant_on_review(sender, instance, created, **kwargs):
    if created or instance.status == 'pending':
        return
    room = instance.user.wit_bot_room  # 1-on-1 with wit_bot
    if instance.status == 'approved':
        post_witty_message(room, copy=APPROVE_COPY.format(kind=instance.kind))
    elif instance.status == 'rejected':
        post_witty_message(room, copy=REJECT_COPY.format(reason=instance.rejection_reason))
        # also bounce intent back to the relevant screenshot collection step
        state = WitBotConversationState.objects.get(user=instance.user)
        state.current_intent = f'kickoff_{instance.kind}'
        state.step = 0
        state.save(update_fields=['current_intent', 'step'])
```

DM copy:
- **Approve** → *"✓ widget shot officially logged for reimbursement. proud of you. \*pats your shoulder from afar\*"*
- **Reject** → *"oh no — admin says: \"{rejection_reason}\". could you redo the screenshot? you can do this. send when ready."* (re-enters `kickoff_widget` intent)

---

## FAQ (strawman content — confirm/edit)

WITty's FAQ menu (triggered by typing `faq`):

1. **Am I allowed to add friends not on the study?** Yes — add anyone you want. Their experience may differ since they won't be on a research version, but it's fine.
2. **What happens to the app after the study?** Data freezes after May 31. Access continues for a short tail period — admin will announce the exact date.
3. **What if I miss something during my mandatory window?** Tap **Call admin** in the welcome card. We'll figure it out together.
4. **How do I switch versions early?** You can't via me. There's a `VersionSwitchRequest` flow — talk to admin if you genuinely need it (rare).
5. **Why does WITty want a screenshot of my widgets?** Widget installation is a participation requirement. We can't auto-detect it on your phone, so the screenshot is the proof.
6. **Why do I have to keep notifications on?** Surveys + study reminders depend on push delivery. Without them you'll miss things and your data won't be complete.
7. **What does WITty actually do?** Mostly worry about you. Sometimes try to make you laugh. Run audits. Be a small confused owl. 🦉
8. **Can I delete my data?** Yes — contact admin.

(User adds/edits in spec review.)

---

## Easter eggs (strawman)

- `wit?` — random one-liner from a rotating bank of ~12. Examples:
  - *"i'm fine. why? do i look like i'm not fine. \*adjusts non-existent collar\*"*
  - *"if a participant pings a check-in in the forest and no one is around to see it, did the participant ping?"*
  - *"sometimes i think about owls. is that weird?"*
- `🐈` (cat emoji) → *"a cat. ok. i acknowledge the cat."*
- `who am i` → *"a participant in WhoamI Today, that's who. (also a person.)"*
- `help` → command list (`Run audit`, `faq`, `wit?`, `Call admin`).
- After 5 audit runs → unlock secret command `🦉` that reveals a hidden trivia line.
- After final-quiz pass → WITty acquires a small new emoji (e.g., 🦉✨) for that participant only.

---

## Implementation sequencing (high level — full plan TBD via writing-plans skill)

1. **Backend models + migrations.** `OnboardingScreenshot`, `OnboardingEvent`, `WitBotConversationState.progress`. Single migration each, follow `MIGRATION_GUIDELINES.md`.
2. **Predicate registry skeleton.** `FeaturePredicate` dataclass, `PREDICATE_REGISTRY`, common.py with DB-backed predicates (the easy ones). version_w.py / version_q.py with TBD-marked entries.
3. **Engine restructure.** Move `chat/wit_bot_engine.py` content into `chat/wit_bot/` package. Implement intent handlers one by one: `kickoff_welcome` → `kickoff_quiz_*` → `kickoff_setup_*` → `audit` → `walkthrough` → `final_quiz` → `faq` → `idle` recovery.
4. **Welcome card refresh.** State-aware builder. Hook into existing `provision_wit_bot_rooms` and add the room-open beacon.
5. **`bot_payload` schema extensions.** Document in code (typed dict / Pydantic). Backend test-data fixtures.
6. **Frontend bot_payload UI.** Render `multi_select`, `deep_link_card`, `screenshot_request`. Submit handlers for each.
7. **`POST /api/onboarding-events/`** endpoint + frontend wrapper + ~6–8 mirror sites.
8. **Admin extension.** `OnboardingScreenshot` admin with thumbnail, approve/reject inline, bulk approve. Signal-driven DM on review.
9. **Copy review pass.** Voice consistency across all WITty messages. Pull all copy into `chat/wit_bot/copy/` for review.
10. **Seed test data + dry-run.** Single test user, full flow E2E. Verify backend persistence per step.
11. **Pre-launch checklist.** Production migrations, smoke test in staging, rollback plan.

Effort estimate: TBD in writing-plans phase. Window to May 4 00:00 PST is tight (~24h from spec sign-off) — see Open Question 11 on phased launch.

---

## Open questions (resolve in spec review before plan)

1. **Predicate registry corrections** — many TBD field names; user to confirm each marked TBD.
2. **Welcome card surface** — chat-only, or also a banner somewhere on the home screen if user hasn't completed kickoff?
3. **WITty mascot/voice samples** — happy with voice samples in the Personality section? Edits welcome.
4. **FAQ list** — edits / additions / removals.
5. **Easter eggs** — additions / removals; localization (English-only or Korean too?)
6. **Final quiz visible reward** — currently nothing. Want a profile badge / sticker in chat / nothing?
7. **Escalation target** — does `Call admin` still go to the existing `wit_admin` proxy room (`is_wit_admin_proxy=True`), or somewhere new?
8. **Daily admin summary** — bot is silent if a participant stalls. Should admin get a daily email of "users behind on kickoff" or "users with pending screenshots"?
9. **Mid-study `VersionSwitchRequest` participants** — re-onboard immediately on switch approval, or wait for the May 18 swap event? (Recommendation: re-onboard immediately, since their `current_ver` changed.)
10. **Localization** — WITty in Korean? `i18n/` exists but copy is English-only in this draft. Confirm scope.
11. **Launch readiness for May 4 00:00 PST** — given today is 2026-05-03, the window is ~24h. Acceptable to ship a thinner V1 (kickoff + screenshot review only, audit loop deferred to V1.1) if needed?
12. **`/api/q/` URL split** — backend has `/api/q/` for Q endpoints, but frontend doesn't actually use them per CLAUDE.md known issue. Does this affect predicate queries? (Recommendation: predicates query the same DB tables regardless of URL prefix, so this is invisible to the audit. Confirm.)
13. **V2 kickoff quiz refresher** — currently spec'd to skip Q1–Q3 in V2 if passed in V1. Alternative: always re-run them in V2 as reinforcement (study spans 28 days, by V2 the participant might have forgotten the answers). Pick one.
14. **Final-quiz scoring transparency** — should WITty show the participant their numeric score (e.g. "you got 78%, need 80%") on a fail, or just qualitative ("close, try again — these were wrong")? Numeric is more honest, qualitative is more on-voice.
