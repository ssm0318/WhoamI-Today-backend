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

# ---------- Audit / walkthrough ----------

AUDIT_HEADER = "audit time. *summons the spreadsheet of your participation*"

AUDIT_RESULT_TEMPLATE = (
    "engaged ({engaged_count}):\n{engaged_list}\n\n"
    "not yet ({missing_count}):\n{missing_list}\n\n"
    "how do you want to play this?"
)

AUDIT_NOTHING_MISSING = (
    "you've tried EVERYTHING. you legend. *single-owl standing ovation*\n"
    "the boss quiz is coming soon. for now, idle."
)

WALKTHROUGH_INTRO = (
    "ok let's walk through what's left. one at a time. "
    "tap **Take me there** to try, **Mark as done** if you already have, "
    "or **Skip for now**."
)

WALKTHROUGH_FEATURE_TEMPLATE = (
    "{index}/{total}  •  {display_name}\n{description}"
)

WALKTHROUGH_COMPLETE = (
    "that's the list done. nice. "
    "use **Run audit** anytime to re-check yourself."
)

JUST_LIST_INTRO = (
    "here's the missing list with deep-links. "
    "explore on your own time and **Run audit** when you want me to re-check."
)

EXPLORE_LATER = (
    "ok — i'll be silent. "
    "use **Run audit** when you want me to re-check."
)

# ---------- Boss quiz (end-of-version final) ----------

BOSS_QUIZ_INTRO = (
    "final boss quiz time. *cracks non-existent knuckles*\n"
    "select EVERY feature that's actually in YOUR version. "
    "some are decoys from the OTHER version. some are completely made up. "
    "need ≥80% to pass. unlimited retries. you've got this."
)

BOSS_QUIZ_PASS_TEMPLATE = (
    "🦉✨  YOU SURVIVED. {score}% — passed.\n"
    "*hands over participation gold star*\n"
    "nothing else from me until the next milestone. enjoy the silence."
)

BOSS_QUIZ_FAIL_TEMPLATE = (
    "{score}%. need 80%. close, but no participation gold star yet.\n"
    "here's what went wrong:\n{wrong_lines}\n\n"
    "*adjusts non-existent monocle*\nlet's go again."
)

# Made-up features that don't exist in either version. Used as the absurd
# decoy bank for the boss quiz.
ABSURD_FEATURES = [
    'Reels',
    'Video filters',
    '2-minute timer',
    'Voice channel',
    'Karaoke mode',
]

# ---------- FAQ ----------

FAQ_MENU_INTRO = (
    "what do you want to know? tap one. (or type `wit?` if you're bored.)"
)

FAQ_ENTRIES = [
    {
        'key': 'add_friends',
        'question': 'Can I add friends not in the study?',
        'answer': (
            "yes. add anyone. their experience may differ since they won't "
            "be on a research version, but it's totally fine."
        ),
    },
    {
        'key': 'after_study',
        'question': 'What happens to the app after the study?',
        'answer': (
            "data freezes after May 31. there's a short tail period for "
            "access — admin will announce the exact date."
        ),
    },
    {
        'key': 'missed_window',
        'question': 'What if I miss something during my mandatory window?',
        'answer': (
            "tap **Call admin** in the welcome card up top. "
            "we'll figure it out together."
        ),
    },
    {
        'key': 'switch_version',
        'question': 'How do I switch versions early?',
        'answer': (
            "you can't via me. there's a separate VersionSwitchRequest flow — "
            "talk to admin if you genuinely need it (rare)."
        ),
    },
    {
        'key': 'why_widget',
        'question': 'Why does WITty want a screenshot of my widgets?',
        'answer': (
            "widget installation is a participation requirement. "
            "we can't auto-detect widgets on your phone, "
            "so the screenshot is the proof."
        ),
    },
    {
        'key': 'why_notifs',
        'question': 'Why do I have to keep notifications on?',
        'answer': (
            "surveys + study reminders depend on push delivery. "
            "without them you'll miss things and your data won't be complete."
        ),
    },
    {
        'key': 'what_witty_does',
        'question': 'What does WITty actually do?',
        'answer': (
            "mostly worry about you. sometimes try to make you laugh. "
            "run audits. be a small confused owl. 🦉"
        ),
    },
    {
        'key': 'delete_data',
        'question': 'Can I delete my data?',
        'answer': "yes — contact admin.",
    },
]

# ---------- Easter eggs / playful ----------

WIT_REPLIES = [
    "i'm fine. why? do i look like i'm not fine. *adjusts non-existent collar*",
    "if a participant pings a check-in in the forest and no one is around to see it, did the participant ping?",
    "sometimes i think about owls. is that weird?",
    "i ate a math problem for breakfast. it didn't agree with me.",
    "*makes a small owl noise* (i don't actually know what owls sound like)",
    "the secret is there is no secret. the second secret is that one's free.",
    "*adjusts non-existent tie* status: trying my best.",
    "i would tell you a joke about UDP but you might not get it. ha. ha. ha.",
    "i could be doing anything right now. but i'm here. *looks meaningfully into middle distance*",
    "wit? me? *blushes*",
    "today's vibe: cautious optimism with a side of confused.",
    "i just learned what a treadmill is. seems unkind.",
]

CAT_REPLY = "a cat. ok. i acknowledge the cat. *bows respectfully*"
WHO_AM_I_REPLY = "a participant in WhoamI Today, that's who. (also a person.)"
HELP_REPLY = (
    "things you can do:\n"
    "  • **Run audit** — see your feature progress\n"
    "  • `faq` — frequently asked things\n"
    "  • `wit?` — talk to me\n"
    "  • **Call admin** (button) — escalate to a real human\n"
    "i'll be silent otherwise."
)
