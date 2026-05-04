"""Static copy + content for the wit_bot onboarding flow.

All WITty-voice strings live here in dual-keyed dicts ({'en': ..., 'ko': ...}).
Use the `t(value, user)` helper to resolve to the user's language.

Quizzes are dicts with 'options' lists; each option has 'value' (stable
language-agnostic ID), 'correct' (bool), and per-language 'label'/'explanation'.
"""
from __future__ import annotations

from typing import Any, Mapping

DEFAULT_LANG = 'en'
SUPPORTED_LANGS = ('en', 'ko')


def t(value, user_or_lang):
    """Resolve a {'en': ..., 'ko': ...} dict to the user's language. Falls back
    to 'en'. If `value` isn't a dict, returns it unchanged. Accepts either a
    user instance or a language string ('en' / 'ko')."""
    if hasattr(user_or_lang, 'language'):
        lang = getattr(user_or_lang, 'language', None) or DEFAULT_LANG
    else:
        lang = user_or_lang or DEFAULT_LANG

    if isinstance(value, Mapping) and any(k in value for k in SUPPORTED_LANGS):
        return value.get(lang, value.get(DEFAULT_LANG, ''))
    return value


# ---------- Welcome / wrap voice ----------

WELCOME_INTRO = {
    'en': (
        "Hi there! I'm WITty ha. ha. ha.\n"
        "I'm here to walk you through everything for the study.\n"
        "Ready?"
    ),
    'ko': (
        "안녕! 나는 WITty야 하. 하. 하.\n"
        "연구 관련된 거 다 같이 살펴보려고 왔어.\n"
        "준비됐어?"
    ),
}

WRAP_KICKOFF = {
    'en': (
        "Kickoff complete. You survived. *small applause from a single owl*\n"
        "Tap **Run audit** in the welcome card up top whenever you've explored "
        "the app a bit. I'll check what features you've actually tried."
    ),
    'ko': (
        "킥오프 끝! 잘 견뎠어. *부엉이 한 마리의 작은 박수*\n"
        "앱을 좀 둘러본 뒤 위쪽 환영 카드의 **Run audit** 눌러. "
        "어떤 기능을 실제로 사용했는지 확인해 줄게."
    ),
}

LETS_GO = {'en': "Let's go", 'ko': '시작!'}

# ---------- Quiz 1 — multi-select study requirements ----------

QUIZ_1_STUDY_REQUIREMENTS = {
    'prompt': {
        'en': (
            "Quiz time. Select EVERYTHING you need to do during the study. "
            "Need ≥80% to move on — I'll show you what you got right after."
        ),
        'ko': (
            "퀴즈 시간이야. 연구 기간 동안 해야 할 거 모두 선택해 봐. "
            "80% 이상 맞아야 다음으로 — 끝나고 정답 알려줄게."
        ),
    },
    'options': [
        {
            'value': 'pre_study', 'correct': True,
            'label': {'en': 'Pre-study survey', 'ko': '사전 설문조사'},
            'explanation': {'en': "Yep — that was on May 2.", 'ko': "맞아 — 5월 2일에 있었어."},
        },
        {
            'value': 'daily_survey', 'correct': True,
            'label': {'en': 'Daily surveys', 'ko': '일일 설문'},
            'explanation': {'en': "Every day, May 4–31.", 'ko': "5월 4일~31일 매일."},
        },
        {
            'value': 'weekly_survey', 'correct': True,
            'label': {'en': 'Weekly survey', 'ko': '주간 설문'},
            'explanation': {'en': "Once a week per the schedule.", 'ko': "일정대로 매주 한 번."},
        },
        {
            'value': 'biweekly_survey', 'correct': True,
            'label': {'en': 'Biweekly survey', 'ko': '격주 설문'},
            'explanation': {'en': "Every two weeks.", 'ko': "2주마다."},
        },
        {
            'value': 'anytime_survey', 'correct': True,
            'label': {'en': 'Anytime / situational surveys', 'ko': '수시 / 상황 설문'},
            'explanation': {'en': "Show up when triggered.", 'ko': "특정 상황에 뜨는 거."},
        },
        {
            'value': 'endpoint_survey', 'correct': True,
            'label': {'en': 'Endpoint survey', 'ko': '엔드포인트 설문'},
            'explanation': {'en': "At the end of the study.", 'ko': "연구 끝날 때."},
        },
        {
            'value': 'mandatory_4_7', 'correct': True,
            'label': {'en': 'Daily app use May 4–7', 'ko': '5월 4-7일 매일 앱 사용'},
            'explanation': {'en': "Mandatory window 1.", 'ko': "필수 기간 1."},
        },
        {
            'value': 'mandatory_18_21', 'correct': True,
            'label': {'en': 'Daily app use May 18–21', 'ko': '5월 18-21일 매일 앱 사용'},
            'explanation': {'en': "Mandatory window 2 (post-swap).", 'ko': "필수 기간 2 (버전 전환 후)."},
        },
        {
            'value': 'push_on', 'correct': True,
            'label': {'en': 'Push notifications on (whole study)', 'ko': '연구 기간 내내 푸시 알림 켜놓기'},
            'explanation': {'en': "Needed for survey delivery.", 'ko': "설문 알림 받으려면 필요해."},
        },
        {
            'value': 'widget_added', 'correct': True,
            'label': {'en': 'Widget added to home screen', 'ko': '홈 화면에 위젯 추가'},
            'explanation': {'en': "Participation requirement.", 'ko': "참여 요건이야."},
        },
        {
            'value': 'add_friend', 'correct': True,
            'label': {'en': 'Add at least one friend on the app', 'ko': '앱에서 친구 한 명 이상 추가'},
            'explanation': {'en': "They don't need to be a study participant.", 'ko': "연구 참여자 아니어도 돼."},
        },
        {
            'value': 'lottery', 'correct': False,
            'label': {'en': 'Win the lottery', 'ko': '복권 당첨'},
            'explanation': {'en': "I appreciate the energy but no.", 'ko': "에너지는 좋지만 안 돼."},
        },
        {
            'value': 'pigeons', 'correct': False,
            'label': {'en': 'Befriend 3 pigeons', 'ko': '비둘기 세 마리와 친구되기'},
            'explanation': {'en': "Great life goal but unrelated.", 'ko': "인생 목표로는 좋지만 무관해."},
        },
        {
            'value': 'dance', 'correct': False,
            'label': {'en': 'Dance', 'ko': '춤추기'},
            'explanation': {'en': "Always optional, never required.", 'ko': "선택사항이지 필수 아니야."},
        },
    ],
}

# ---------- Quiz 2 — single-select swap timing ----------

QUIZ_2_SWAP_TIMING = {
    'prompt': {
        'en': "When does your version swap happen?",
        'ko': "버전 전환은 언제 일어나?",
    },
    'reveal_correct': {
        'en': (
            "Correct! You'll wake up on May 18 and the app will look different. "
            "You'll get the OTHER version. Then May 18–21 is mandatory daily-use "
            "again. Wild."
        ),
        'ko': (
            "맞아! 5월 18일 깨어보면 앱이 달라보일 거야. 다른 버전을 받게 돼. "
            "그리고 5월 18-21일은 다시 매일 사용 필수기간이야. 미친 일이지."
        ),
    },
    'reveal_wrong': {
        'en': (
            "Nope. Midnight May 17 → 18 PST. "
            "You'll get the OTHER version then, and May 18–21 is mandatory again."
        ),
        'ko': (
            "아니야. PST 5월 17→18 자정. "
            "그때 다른 버전 받게 되고, 5월 18-21일 다시 필수기간."
        ),
    },
    'options': [
        {
            'value': 'correct', 'correct': True,
            'label': {'en': 'Midnight May 17 → 18 PST', 'ko': 'PST 5월 17→18 자정'},
        },
        {
            'value': 'gemini', 'correct': False,
            'label': {'en': 'When we reach gemini season', 'ko': '쌍둥이자리 시즌이 올 때'},
        },
        {
            'value': 'lunch', 'correct': False,
            'label': {'en': 'Tomorrow at lunch', 'ko': '내일 점심때'},
        },
        {
            'value': 'enlightenment', 'correct': False,
            'label': {'en': 'When WITty achieves enlightenment', 'ko': 'WITty가 깨달음을 얻을 때'},
        },
    ],
}

# ---------- Quiz 3 — single-select surveys location ----------

QUIZ_3_SURVEYS_LOCATION = {
    'prompt': {
        'en': "Where in the app can you find your surveys?",
        'ko': "앱 어디에서 설문조사를 찾을 수 있어?",
    },
    'reveal_correct': {
        'en': (
            "Correct. Tap the hamburger → Surveys. The list shows all available "
            "and completed surveys."
        ),
        'ko': (
            "맞아. 햄버거 메뉴 → Surveys 탭. 가능한 설문이랑 끝낸 설문 다 보여."
        ),
    },
    'reveal_wrong': {
        'en': "Actually, it's the sidebar — tap hamburger → Surveys.",
        'ko': "사실은 사이드바야 — 햄버거 → Surveys.",
    },
    'options': [
        {
            'value': 'sidebar', 'correct': True,
            'label': {'en': 'Sidebar → "Surveys" button', 'ko': '사이드바 → "Surveys" 버튼'},
        },
        {
            'value': 'popup', 'correct': False,
            'label': {'en': 'Pop-up that appears when one is due', 'ko': '마감일 다가오면 뜨는 팝업'},
        },
        {
            'value': 'settings', 'correct': False,
            'label': {'en': 'Settings → Surveys', 'ko': '설정 → Surveys'},
        },
        {
            'value': 'pocket', 'correct': False,
            'label': {'en': "WITty's secret pocket dimension", 'ko': "WITty의 비밀 공간"},
        },
    ],
}

# ---------- Setup-check copy ----------

PUSH_NOTIF_OFF_COPY = {
    'en': (
        "Hmm — your push notifications are off. That's a problem because I need "
        "to send you survey reminders and study alerts. Without those, your data "
        "isn't complete and you can't get reimbursed for the part of the study "
        "that depended on them. It's not personal. *adjusts nothing*\n"
        "Could you turn them on for the duration of the study? If a specific "
        "notification gets too annoying, DM me — admin will sort something out. "
        "Thank you for understanding. Truly."
    ),
    'ko': (
        "음 — 푸시 알림이 꺼져있네. 이게 문제인 게, 설문 알림이랑 연구 알림을 "
        "보낼 수가 없어. 그게 없으면 데이터가 불완전해서 그 부분 보상도 못 받아. "
        "개인적인 거 아니야. *없는 거 매만지는 중*\n"
        "연구 기간 동안만 켜둘 수 있어? 특정 알림이 너무 많으면 dm 줘 — "
        "어드민이 조정해줄 거야. 정말 고마워. 진심으로."
    ),
}

PUSH_NOTIF_ON_COPY = {
    'en': "Push notifs are on ✓. Great. Moving on.",
    'ko': "푸시 알림 켜져있어 ✓. 좋아. 다음으로.",
}

PUSH_DONE_BUTTON = {
    'en': "Done — they're on now",
    'ko': '완료 — 켰어',
}

FRIEND_MIN_NEEDED_COPY = {
    'en': (
        "You don't have a friend yet on the app. Add at least one — they don't "
        "have to be a study participant — and tap **Done**. I'll keep watching."
    ),
    'ko': (
        "앱에 친구가 아직 없네. 한 명 이상 추가해 — 연구 참여자 아니어도 돼 — "
        "그리고 **Done** 눌러. 계속 지켜볼게."
    ),
}

FRIEND_MIN_OK_COPY = {
    'en': "I see at least one friend ✓. Moving on.",
    'ko': "친구 한 명 이상 보여 ✓. 다음으로.",
}

FRIEND_DONE_BUTTON = {
    'en': 'Done — added one',
    'ko': '완료 — 추가했어',
}

WIDGET_PROMPT_COPY = {
    'en': (
        "Show me your home screen with all 3 widgets visible. One screenshot. "
        "I'll log it for admin to verify. You'll be unblocked immediately; "
        "official check-off comes after admin reviews."
    ),
    'ko': (
        "홈 화면에 위젯 3개 다 보이게 스크린샷 보내줘. 한 장이면 돼. "
        "어드민 검토용으로 기록할게. 바로 진행할 수 있고, 정식 확인은 "
        "어드민 검토 끝나면 알려줄게."
    ),
}

WIDGET_RECEIVED_COPY = {
    'en': (
        "Got it ✓. Logged for admin review. "
        "I'll let you know when they confirm. You can keep going."
    ),
    'ko': (
        "받았어 ✓. 어드민 검토용으로 기록됐어. "
        "확인되면 알려줄게. 계속 진행해도 돼."
    ),
}

WIDGET_APPROVED_DM = {
    'en': "✓ Widget shot officially logged for reimbursement. *pats your shoulder from afar*",
    'ko': "✓ 위젯 스크린샷 보상용으로 정식 기록됐어. *멀리서 어깨 토닥토닥*",
}

WIDGET_REJECTED_DM_TEMPLATE = {
    'en': (
        "Oh no — admin says: \"{reason}\". "
        "Could you redo the screenshot? You can do this. Send when ready."
    ),
    'ko': (
        "이런 — 어드민이 그러는데: \"{reason}\". "
        "스크린샷 다시 보내줄 수 있어? 할 수 있어. 준비되면 보내."
    ),
}

# ---------- Audit / walkthrough ----------

AUDIT_HEADER = {
    'en': "Audit time. *summons the spreadsheet of your participation*",
    'ko': "Audit 시간이야. *참여 스프레드시트 소환*",
}

AUDIT_RESULT_TEMPLATE = {
    'en': (
        "Engaged ({engaged_count}):\n{engaged_list}\n\n"
        "Not yet ({missing_count}):\n{missing_list}\n\n"
        "How do you want to play this?"
    ),
    'ko': (
        "이미 함 ({engaged_count}):\n{engaged_list}\n\n"
        "아직 안 함 ({missing_count}):\n{missing_list}\n\n"
        "어떻게 할래?"
    ),
}

AUDIT_ALMOST_THERE = {
    'en': "✨ Almost there! You've only got {n} left to unlock the boss quiz.",
    'ko': "✨ 거의 다 왔어! 보스 퀴즈를 열려면 {n}개만 더 하면 돼.",
}

AUDIT_NOTHING_MISSING = {
    'en': (
        "🎉 You've tried EVERYTHING. You legend. *single-owl standing ovation*\n"
        "You unlocked the boss quiz. Tap **Take the boss quiz** in the welcome "
        "card up top when you're ready."
    ),
    'ko': (
        "🎉 전부 다 해봤네. 짱이야. *부엉이 한 마리 기립박수*\n"
        "보스 퀴즈가 열렸어. 준비되면 위쪽 환영 카드의 **Take the boss quiz** 눌러."
    ),
}

WALKTHROUGH_INTRO = {
    'en': (
        "OK let's walk through what's left. One at a time. "
        "Tap **Take me there** to try the feature, **Re-check** if you've already "
        "done it (I'll re-run the check), **Mark as done** to override the check "
        "(use sparingly — admin spot-checks these), or **Skip for now**."
    ),
    'ko': (
        "남은 거 하나씩 살펴보자. **Take me there** 눌러서 시도하거나, "
        "이미 했으면 **Re-check** (다시 확인할게), 검사 무시하고 완료 처리하려면 "
        "**Mark as done** (어드민이 가끔 검수해), 아니면 **Skip for now**."
    ),
}

WALKTHROUGH_COMPLETE = {
    'en': "🎉 That's the list done. Boss quiz unlocked — tap **Take the boss quiz** above when ready.",
    'ko': "🎉 리스트 다 끝났어. 보스 퀴즈가 열렸어 — 준비되면 위쪽 **Take the boss quiz** 눌러.",
}

JUST_LIST_INTRO = {
    'en': (
        "Here's the missing list with deep-links. "
        "Explore on your own time and tap **Run audit** above when you want me to re-check."
    ),
    'ko': (
        "남은 거 deep-link로 보여줄게. "
        "각자 페이스로 살펴보고 다시 확인하고 싶을 때 위쪽 **Run audit** 눌러."
    ),
}

EXPLORE_LATER = {
    'en': "OK — I'll be silent. Tap **Run audit** above when you want me to re-check.",
    'ko': "응 — 조용히 있을게. 다시 확인하고 싶을 때 위쪽 **Run audit** 눌러.",
}

WALKTHROUGH_RECHECK_OK = {
    'en': "✓ I see it now. Marking as engaged.",
    'ko': "✓ 확인됐어. 완료 처리.",
}

WALKTHROUGH_RECHECK_FAIL = {
    'en': (
        "Hmm, I still don't see it on my end. Try the action via **Take me there**, "
        "or use **Mark as done** if you're sure you completed it."
    ),
    'ko': (
        "아직 안 보여. **Take me there**로 다시 시도하거나, "
        "확실히 했다 싶으면 **Mark as done** 눌러."
    ),
}

WALKTHROUGH_TAKE_ME_THERE = {'en': 'Take me there', 'ko': '데려가줘'}
WALKTHROUGH_RECHECK = {'en': 'Re-check', 'ko': '다시 확인'}
WALKTHROUGH_MARK_DONE = {'en': 'Mark as done', 'ko': '완료 처리'}
WALKTHROUGH_SKIP = {'en': 'Skip for now', 'ko': '일단 패스'}
AUDIT_BTN_WALKTHROUGH = {'en': 'Walk me through them', 'ko': '하나씩 안내해 줘'}
AUDIT_BTN_LIST = {'en': 'Just give me the list', 'ko': '리스트만 줘'}
AUDIT_BTN_LATER = {'en': "I'll explore, audit me later", 'ko': '내가 둘러보고 나중에 다시 audit'}

# ---------- Boss quiz (end-of-version final) ----------

BOSS_QUIZ_INTRO = {
    'en': (
        "Final boss quiz time. *cracks non-existent knuckles*\n"
        "Select EVERY feature that's actually in YOUR version. "
        "Some are decoys from the OTHER version. Some are completely made up. "
        "Need ≥80% to pass. Unlimited retries. You've got this."
    ),
    'ko': (
        "최종 보스 퀴즈 시간이야. *없는 손가락 우두둑*\n"
        "네 버전에 실제로 있는 기능을 모두 골라. "
        "어떤 건 다른 버전의 함정이고, 어떤 건 완전 가짜야. "
        "80% 이상 맞아야 통과. 무한 재시도. 할 수 있어."
    ),
}

BOSS_QUIZ_PASS_TEMPLATE = {
    'en': (
        "🦉✨ YOU SURVIVED. {score}% — passed.\n"
        "*hands over participation gold star*\n"
        "Nothing else from me until the next milestone. Enjoy the silence."
    ),
    'ko': (
        "🦉✨ 살아남았어! {score}% — 통과.\n"
        "*참여 골드 스타 수여*\n"
        "다음 마일스톤 전까지 나는 잠수 탈게. 평화를 즐겨."
    ),
}

BOSS_QUIZ_FAIL_TEMPLATE = {
    'en': (
        "{score}%. Need 80%. Close, but no participation gold star yet.\n"
        "Here's what went wrong:\n{wrong_lines}\n\n"
        "*adjusts non-existent monocle*\nLet's go again."
    ),
    'ko': (
        "{score}%. 80% 필요해. 아쉽지만 골드 스타는 아직.\n"
        "뭐가 틀렸는지 알려줄게:\n{wrong_lines}\n\n"
        "*없는 외알 안경 매만지기*\n다시 가자."
    ),
}

BOSS_QUIZ_MISSED = {
    'en': "MISSED — {label}: that IS in your version, you should have selected it",
    'ko': "놓침 — {label}: 네 버전에 있어, 골랐어야 해",
}

BOSS_QUIZ_WRONG_DISTRACTOR = {
    'en': "WRONG — {label}: not in your version (from the OTHER version)",
    'ko': "오답 — {label}: 네 버전 아니야 (다른 버전 거)",
}

BOSS_QUIZ_WRONG_ABSURD = {
    'en': "WRONG — {label}: not in your version (completely made up)",
    'ko': "오답 — {label}: 네 버전 아니야 (완전 가짜)",
}

# Made-up features that don't exist in either version. Used as the absurd
# decoy bank for the boss quiz.
ABSURD_FEATURES = [
    {'value': 'reels', 'label': {'en': 'Reels', 'ko': '릴스'}},
    {'value': 'video_filters', 'label': {'en': 'Video filters', 'ko': '영상 필터'}},
    {'value': 'two_min_timer', 'label': {'en': '2-minute timer', 'ko': '2분 타이머'}},
    {'value': 'voice_channel', 'label': {'en': 'Voice channel', 'ko': '음성 채널'}},
    {'value': 'karaoke_mode', 'label': {'en': 'Karaoke mode', 'ko': '노래방 모드'}},
]

# ---------- FAQ ----------

FAQ_MENU_INTRO = {
    'en': "What do you want to know? Tap one. (Or type `wit?` if you're bored.)",
    'ko': "뭐가 궁금해? 하나 눌러봐. (심심하면 `wit?` 쳐도 돼.)",
}

FAQ_ENTRIES = [
    {
        'key': 'add_friends',
        'question': {
            'en': 'Can I add friends not in the study?',
            'ko': '연구 참여자가 아닌 친구도 추가할 수 있어?',
        },
        'answer': {
            'en': (
                "Yes. Add anyone. Their experience may differ since they won't "
                "be on a research version, but it's totally fine."
            ),
            'ko': (
                "응. 누구든 추가해도 돼. 연구 버전이 아니어서 경험은 다를 수 있지만 "
                "괜찮아."
            ),
        },
    },
    {
        'key': 'after_study',
        'question': {
            'en': 'What happens to the app after the study?',
            'ko': '연구 끝나고 앱은 어떻게 돼?',
        },
        'answer': {
            'en': (
                "Data freezes after May 31. There's a short tail period for "
                "access — admin will announce the exact date."
            ),
            'ko': (
                "5월 31일 이후 데이터는 동결돼. 짧은 정리 기간 동안 접속할 수 있고, "
                "어드민이 정확한 종료일 안내해 줄 거야."
            ),
        },
    },
    {
        'key': 'missed_window',
        'question': {
            'en': 'What if I miss something during my mandatory window?',
            'ko': '필수 기간에 뭔가 못 했으면?',
        },
        'answer': {
            'en': (
                "Tap **Call admin** in the welcome card up top. "
                "We'll figure it out together."
            ),
            'ko': (
                "위 카드의 **Call admin** 눌러. 같이 해결책 찾자."
            ),
        },
    },
    {
        'key': 'switch_version',
        'question': {
            'en': 'How do I switch versions early?',
            'ko': '버전을 미리 바꿀 수 있어?',
        },
        'answer': {
            'en': (
                "You can't via me. There's a separate VersionSwitchRequest flow — "
                "talk to admin if you genuinely need it (rare)."
            ),
            'ko': (
                "나로는 안 돼. 별도 VersionSwitchRequest 절차가 있어 — "
                "정말 필요하면 어드민에게 얘기해 (드물게)."
            ),
        },
    },
    {
        'key': 'why_widget',
        'question': {
            'en': 'Why does WITty want a screenshot of my widgets?',
            'ko': '왜 위젯 스크린샷이 필요해?',
        },
        'answer': {
            'en': (
                "Widget installation is a participation requirement. "
                "We can't auto-detect widgets on your phone, "
                "so the screenshot is the proof."
            ),
            'ko': (
                "위젯 설치는 참여 요건이야. 스마트폰에서 자동 감지가 안 되니까 "
                "스크린샷이 증빙이야."
            ),
        },
    },
    {
        'key': 'why_notifs',
        'question': {
            'en': 'Why do I have to keep notifications on?',
            'ko': '왜 알림을 켜놔야 해?',
        },
        'answer': {
            'en': (
                "Surveys + study reminders depend on push delivery. "
                "Without them you'll miss things and your data won't be complete."
            ),
            'ko': (
                "설문이랑 연구 알림이 푸시로 가. 안 켜놓으면 놓쳐서 데이터가 "
                "불완전해."
            ),
        },
    },
    {
        'key': 'what_witty_does',
        'question': {
            'en': 'What does WITty actually do?',
            'ko': 'WITty가 실제로 뭐 해?',
        },
        'answer': {
            'en': (
                "Mostly worry about you. Sometimes try to make you laugh. "
                "Run audits. Be a small confused owl. 🦉"
            ),
            'ko': (
                "주로 너 걱정하기. 가끔 웃기려고 시도. audit 돌리기. "
                "작고 약간 헷갈리는 부엉이로 살기. 🦉"
            ),
        },
    },
    {
        'key': 'delete_data',
        'question': {
            'en': 'Can I delete my data?',
            'ko': '데이터 삭제 가능해?',
        },
        'answer': {
            'en': "Yes — contact admin.",
            'ko': "응 — 어드민에게 연락해.",
        },
    },
]

# ---------- Easter eggs / playful ----------

WIT_REPLIES = [
    {
        'en': "I'm fine. Why? Do I look like I'm not fine. *adjusts non-existent collar*",
        'ko': "괜찮아. 왜? 안 괜찮아 보여? *없는 옷깃 매만지기*",
    },
    {
        'en': "If a participant pings a check-in in the forest and no one is around to see it, did the participant ping?",
        'ko': "참여자가 숲에서 체크인을 ping했는데 아무도 못 봤다면, 정말 ping한 거야?",
    },
    {
        'en': "Sometimes I think about owls. Is that weird?",
        'ko': "가끔 부엉이에 대해 생각해. 이상한가?",
    },
    {
        'en': "I ate a math problem for breakfast. It didn't agree with me.",
        'ko': "아침에 수학 문제를 먹었는데 잘 안 맞았어.",
    },
    {
        'en': "*makes a small owl noise* (I don't actually know what owls sound like)",
        'ko': "*작은 부엉이 소리 흉내* (사실 부엉이가 어떤 소리 내는지 몰라)",
    },
    {
        'en': "The secret is there is no secret. The second secret is that one's free.",
        'ko': "비밀은 비밀이 없다는 거야. 두 번째 비밀은 그건 무료라는 거.",
    },
    {
        'en': "*adjusts non-existent tie* Status: trying my best.",
        'ko': "*없는 넥타이 매만지기* 상태: 최선을 다하는 중.",
    },
    {
        'en': "I would tell you a joke about UDP but you might not get it. Ha. Ha. Ha.",
        'ko': "UDP 농담 알려줄까 했는데 안 들릴 수 있어. 하. 하. 하.",
    },
    {
        'en': "I could be doing anything right now. But I'm here. *looks meaningfully into middle distance*",
        'ko': "지금 뭐든 할 수 있는데 여기 있어. *의미심장하게 멀리 응시*",
    },
    {
        'en': "Wit? Me? *blushes*",
        'ko': "wit? 나? *얼굴 빨개짐*",
    },
    {
        'en': "Today's vibe: cautious optimism with a side of confused.",
        'ko': "오늘의 vibe: 조심스러운 낙관 + 약간의 혼란.",
    },
    {
        'en': "I just learned what a treadmill is. Seems unkind.",
        'ko': "방금 러닝머신이 뭔지 알았어. 참 잔인해 보여.",
    },
]

CAT_REPLY = {
    'en': "A cat. OK. I acknowledge the cat. *bows respectfully*",
    'ko': "고양이. 그래. 고양이를 인지함. *공손하게 인사*",
}

WHO_AM_I_REPLY = {
    'en': "A participant in WhoamI Today, that's who. (Also a person.)",
    'ko': "WhoamI Today 참여자, 그게 너야. (사람이기도 하고.)",
}

# ---------- Welcome card inlines ----------

WC_KICKOFF_DONE_PRE_AUDIT = {
    'en': "Kickoff done. Tap **Run audit** below when you've explored more.",
    'ko': "킥오프 완료. 좀 더 둘러보고 아래 **Run audit** 눌러봐.",
}

WC_AUDIT_DONE_PRE_BOSS = {
    'en': "Audit done — boss quiz unlocked. Time?",
    'ko': "Audit 완료 — 보스 퀴즈 열림. 시작할까?",
}

WC_BOSS_PASSED_PRE_SWAP = {
    'en': "You survived. See you May 18 for the swap.",
    'ko': "살아남았어. 5월 18일 버전 전환 때 보자.",
}

WC_TIME_TO_ONBOARD_W = {
    'en': "Time to onboard. You're on version W.",
    'ko': "온보딩 시작. 너는 버전 W야.",
}

WC_TIME_TO_ONBOARD_Q = {
    'en': "Time to onboard. You're on version Q.",
    'ko': "온보딩 시작. 너는 버전 Q야.",
}

WC_POST_SWAP_W = {
    'en': "The swap happened. You're now on version W.\nReady for round 2?",
    'ko': "전환 일어났어. 이제 버전 W야.\n2라운드 갈까?",
}

WC_POST_SWAP_Q = {
    'en': "The swap happened. You're now on version Q.\nReady for round 2?",
    'ko': "전환 일어났어. 이제 버전 Q야.\n2라운드 갈까?",
}

WC_MID_FLOW = {
    'en': "We were in the middle of something.",
    'ko': "하던 거 있었어.",
}

WC_AUDIT_IN_PROGRESS = {
    'en': "Audit in progress. Resume or rerun?",
    'ko': "Audit 진행 중. 이어서 할래, 다시 할래?",
}

WC_WALKTHROUGH_IN_PROGRESS = {
    'en': "Walking through features. Resume or run a fresh audit?",
    'ko': "기능 안내 중. 이어서 할래, audit 다시 돌릴래?",
}

WC_DEFAULT_SILENT = {
    'en': "All good. See you when needed.",
    'ko': "다 좋아. 필요하면 보자.",
}

WC_BTN_RESUME_ONBOARDING = {'en': 'Resume onboarding', 'ko': '이어서 진행'}
WC_BTN_RESUME = {'en': 'Resume', 'ko': '이어서'}
WC_BTN_RUN_AUDIT = {'en': 'Run audit', 'ko': 'Audit 실행'}
WC_BTN_TAKE_BOSS_QUIZ = {'en': 'Take the boss quiz', 'ko': '보스 퀴즈 도전'}
WC_BTN_START_ONBOARDING = {'en': 'Start onboarding', 'ko': '온보딩 시작'}
WC_BTN_START_VERSION_W = {'en': 'Start version W onboarding', 'ko': '버전 W 온보딩 시작'}
WC_BTN_START_VERSION_Q = {'en': 'Start version Q onboarding', 'ko': '버전 Q 온보딩 시작'}


HELP_REPLY = {
    'en': (
        "Things you can do:\n"
        "  • **Run audit** — see your feature progress\n"
        "  • `faq` — frequently asked things\n"
        "  • `wit?` — talk to me\n"
        "  • **Call admin** (button) — escalate to a real human\n"
        "I'll be silent otherwise."
    ),
    'ko': (
        "할 수 있는 것들:\n"
        "  • **Run audit** — 기능 진척도 보기\n"
        "  • `faq` — 자주 묻는 질문\n"
        "  • `wit?` — 나랑 대화\n"
        "  • **Call admin** (버튼) — 진짜 사람한테 escalate\n"
        "나머진 조용히 있을게."
    ),
}
