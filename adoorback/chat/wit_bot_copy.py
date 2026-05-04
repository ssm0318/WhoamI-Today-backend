"""Static copy + content for the wit_bot onboarding flow.

All WITty-voice strings live here so spec review can edit them without
touching engine logic. Quizzes are dicts with 'options' lists; each option has
'value' (stable ID for state), 'label' (display), and 'correct' (bool).
"""

# ---------- Welcome / wrap voice ----------

WELCOME_INTRO = (
    "Hi there! I'm WITty ha. ha. ha. that was a joke. *adjusts non-existent tie*\n"
    "I'm here to walk you through everything for the study.\n"
    "ready?"
)

WRAP_KICKOFF = (
    "kickoff complete. you survived. *small applause from a single owl*\n"
    "use the welcome card up there to come back. type `wit?` if you're bored."
)

# ---------- Quiz 1 — multi-select study requirements ----------

QUIZ_1_STUDY_REQUIREMENTS = {
    'prompt': (
        "hello. quiz time. select EVERYTHING you need to do during the study. "
        "i'll tell you what you got right after."
    ),
    'options': [
        {'value': 'pre_study', 'label': 'Pre-study survey', 'correct': True,
         'explanation': "yep — that was on May 2."},
        {'value': 'daily_survey', 'label': 'Daily surveys', 'correct': True,
         'explanation': "every day, May 4–31."},
        {'value': 'weekly_survey', 'label': 'Weekly survey', 'correct': True,
         'explanation': "once a week per the schedule."},
        {'value': 'biweekly_survey', 'label': 'Biweekly survey', 'correct': True,
         'explanation': "every two weeks."},
        {'value': 'anytime_survey', 'label': 'Anytime / situational surveys', 'correct': True,
         'explanation': "show up when triggered."},
        {'value': 'endpoint_survey', 'label': 'Endpoint survey', 'correct': True,
         'explanation': "at the end of the study."},
        {'value': 'mandatory_4_7', 'label': 'Daily app use May 4–7', 'correct': True,
         'explanation': "mandatory window 1."},
        {'value': 'mandatory_18_21', 'label': 'Daily app use May 18–21', 'correct': True,
         'explanation': "mandatory window 2 (post-swap)."},
        {'value': 'push_on', 'label': 'Push notifications on (whole study)', 'correct': True,
         'explanation': "we need them for survey delivery."},
        {'value': 'widget_added', 'label': 'Widget added to home screen', 'correct': True,
         'explanation': "participation requirement."},
        {'value': 'add_friend', 'label': 'Add at least one friend on the app', 'correct': True,
         'explanation': "they don't need to be a study participant."},
        {'value': 'lottery', 'label': 'Win the lottery', 'correct': False,
         'explanation': "i appreciate the energy but no."},
        {'value': 'pigeons', 'label': 'Befriend 3 pigeons', 'correct': False,
         'explanation': "great life goal but unrelated."},
        {'value': 'dance', 'label': 'Dance', 'correct': False,
         'explanation': "always optional, never required."},
    ],
}

# ---------- Quiz 2 — single-select swap timing ----------

QUIZ_2_SWAP_TIMING = {
    'prompt': "when does your version swap happen?",
    'reveal_correct': (
        "correct! you'll wake up on May 18 and the app will look different. "
        "you'll get the OTHER version. then May 18–21 is mandatory daily-use "
        "again. wild."
    ),
    'reveal_wrong': (
        "no. midnight May 17 → 18 PST. "
        "you'll get the OTHER version then, and May 18–21 is mandatory again."
    ),
    'options': [
        {'value': 'correct', 'label': 'Midnight May 17 → 18 PST', 'correct': True},
        {'value': 'gemini', 'label': 'When we reach gemini season', 'correct': False},
        {'value': 'lunch', 'label': 'Tomorrow at lunch', 'correct': False},
        {'value': 'enlightenment', 'label': 'When WITty achieves enlightenment', 'correct': False},
    ],
}

# ---------- Quiz 3 — single-select surveys location ----------

QUIZ_3_SURVEYS_LOCATION = {
    'prompt': "where in the app can you find your surveys?",
    'reveal_correct': (
        "correct. tap the hamburger → Surveys. the list shows all available "
        "and completed surveys."
    ),
    'reveal_wrong': (
        "actually it's the sidebar — tap hamburger → Surveys."
    ),
    'options': [
        {'value': 'sidebar', 'label': 'Sidebar → "Surveys" button', 'correct': True},
        {'value': 'popup', 'label': 'Pop-up that appears when one is due', 'correct': False},
        {'value': 'settings', 'label': 'Settings → Surveys', 'correct': False},
        {'value': 'pocket', 'label': "WITty's secret pocket dimension", 'correct': False},
    ],
}

# ---------- Setup-check copy ----------

PUSH_NOTIF_OFF_COPY = (
    "ok so. your push notifications are off. that's a problem because i need "
    "to send you survey reminders and study alerts. without those, your data "
    "isn't complete and you can't get reimbursed for the part of the study "
    "that depended on them. it's not personal. *adjusts nothing*\n"
    "could you turn them on for the duration of the study? if a specific "
    "notification gets too annoying, dm me — admin will sort something out. "
    "thank you for understanding. truly."
)

PUSH_NOTIF_ON_COPY = (
    "push notifs are on ✓. great. moving on."
)

FRIEND_MIN_NEEDED_COPY = (
    "you don't have a friend yet on the app. add at least one — they don't "
    "have to be a study participant — and tap **Done**. i'll keep watching."
)

FRIEND_MIN_OK_COPY = (
    "i see at least one friend ✓. moving on."
)

WIDGET_PROMPT_COPY = (
    "show me your home screen with all 3 widgets visible. one screenshot. "
    "i'll log it for admin to verify. you'll be unblocked immediately, "
    "official check-off comes after admin reviews."
)

WIDGET_RECEIVED_COPY = (
    "got it ✓. logged for admin review. "
    "i'll let you know when they confirm. you can keep going."
)

WIDGET_APPROVED_DM = (
    "✓ widget shot officially logged for reimbursement. "
    "*pats your shoulder from afar*"
)

WIDGET_REJECTED_DM_TEMPLATE = (
    "oh no — admin says: \"{reason}\". "
    "could you redo the screenshot? you can do this. send when ready."
)
