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
        "Hey, I'm WITty. I'll walk you through everything for the study. Ready?"
    ),
    'ko': (
        "안녕, 나는 WITty야. 연구 관련된 거 같이 살펴보자. 준비됐어?"
    ),
}

WRAP_KICKOFF = {
    'en': (
        "Kickoff done. Tap **Run audit** when you've explored the app a bit — "
        "I'll check what you've used."
    ),
    'ko': (
        "킥오프 끝. 앱을 좀 둘러본 뒤 **Run audit** 눌러. "
        "어떤 기능을 사용했는지 확인해 줄게."
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
            'explanation': {'en': "Not required.", 'ko': "필수 아님."},
        },
        {
            'value': 'pigeons', 'correct': False,
            'label': {'en': 'Befriend 3 pigeons', 'ko': '비둘기 세 마리와 친구되기'},
            'explanation': {'en': "Not required.", 'ko': "필수 아님."},
        },
        {
            'value': 'dance', 'correct': False,
            'label': {'en': 'Dance', 'ko': '춤추기'},
            'explanation': {'en': "Optional, never required.", 'ko': "선택, 필수 아님."},
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
        "Push notifs are off. Need them on for survey reminders and study "
        "alerts — otherwise your data won't be complete and the related "
        "reimbursement won't go through. Turn them on for the study window. "
        "If specific notifs get annoying, DM me and admin can adjust."
    ),
    'ko': (
        "푸시 알림이 꺼져 있어. 설문이랑 연구 알림 보내려면 켜져 있어야 해 — "
        "안 그러면 데이터가 불완전해서 관련 보상도 안 나가. "
        "연구 기간 동안 켜놔. 특정 알림이 거슬리면 dm 줘, 어드민이 조정해 줄게."
    ),
}

PUSH_NOTIF_ON_COPY = {
    'en': "Push notifs are on ✓. Moving on.",
    'ko': "푸시 알림 켜져 있어 ✓. 다음으로.",
}

PUSH_DONE_BUTTON = {
    'en': "Done — they're on now",
    'ko': '완료 — 켰어',
}

PUSH_OPEN_SETTINGS_BUTTON = {
    'en': 'Take me to notification settings',
    'ko': '알림 설정으로 데려가줘',
}

FRIEND_MIN_NEEDED_COPY = {
    'en': (
        "No friend on the app yet. Add at least one — doesn't have to be a "
        "study participant — and tap **Done**."
    ),
    'ko': (
        "앱에 친구가 아직 없어. 한 명 이상 추가하고 **Done** 눌러. "
        "연구 참여자 아니어도 돼."
    ),
}

FRIEND_MIN_OK_COPY = {
    'en': "Got at least one friend ✓. Moving on.",
    'ko': "친구 한 명 이상 있어 ✓. 다음으로.",
}

FRIEND_DONE_BUTTON = {
    'en': 'Done — added one',
    'ko': '완료 — 추가했어',
}

WIDGET_PROMPT_COPY = {
    'en': (
        "Send a screenshot of your home screen with all 3 widgets visible. "
        "I'll log it for admin to verify. You can keep going right away — "
        "official confirmation comes after admin reviews."
    ),
    'ko': (
        "홈 화면에 위젯 3개 다 보이게 스크린샷 보내줘. "
        "어드민 검토용으로 기록할게. 바로 진행 가능하고, 정식 확인은 "
        "어드민 검토 후에 알려줄게."
    ),
}

WIDGET_RECEIVED_COPY = {
    'en': "Got it ✓. Logged for admin review. I'll let you know when it's confirmed.",
    'ko': "받았어 ✓. 어드민 검토용으로 기록됐어. 확인되면 알려줄게.",
}

WIDGET_APPROVED_DM = {
    'en': "✓ Widget screenshot confirmed.",
    'ko': "✓ 위젯 스크린샷 확인됐어.",
}

WIDGET_REJECTED_DM_TEMPLATE = {
    'en': "Admin sent it back: \"{reason}\". Could you redo the screenshot?",
    'ko': "어드민이 반려했어: \"{reason}\". 스크린샷 다시 보내줄 수 있어?",
}

# ---------- Audit / walkthrough ----------

AUDIT_HEADER = {
    'en': "Audit time.",
    'ko': "Audit 시간.",
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
    'en': "Almost there — {n} left to unlock the boss quiz.",
    'ko': "거의 다 왔어 — 보스 퀴즈 열려면 {n}개 남음.",
}

AUDIT_NOTHING_MISSING = {
    'en': (
        "🎉 You've tried everything. Boss quiz unlocked — "
        "tap **Take the boss quiz** when you're ready."
    ),
    'ko': (
        "🎉 다 해봤네. 보스 퀴즈 열렸어 — "
        "준비되면 **Take the boss quiz** 눌러."
    ),
}

WALKTHROUGH_INTRO = {
    'en': (
        "OK let's walk through what's left, one at a time. "
        "**Take me there** to try the feature. **Re-check** if you already did "
        "it (I'll verify). **Mark as done** to override the check (admin "
        "spot-checks). **Skip for now** to come back later."
    ),
    'ko': (
        "남은 거 하나씩 살펴보자. **Take me there**로 시도, "
        "이미 했으면 **Re-check** (확인해 줄게), 검사 무시하고 완료 처리하려면 "
        "**Mark as done** (어드민이 가끔 검수), 나중에 하려면 **Skip for now**."
    ),
}

WALKTHROUGH_COMPLETE = {
    'en': "List done. Boss quiz unlocked — tap **Take the boss quiz** when ready.",
    'ko': "리스트 끝. 보스 퀴즈 열렸어 — 준비되면 **Take the boss quiz** 눌러.",
}

JUST_LIST_INTRO = {
    'en': "Here's the list with deep-links. Tap **Run audit** when you want me to re-check.",
    'ko': "남은 거 deep-link로 보여줄게. 다시 확인하고 싶을 때 **Run audit** 눌러.",
}

EXPLORE_LATER = {
    'en': "Cool. Tap **Run audit** when you want me to re-check.",
    'ko': "오케이. 다시 확인하고 싶을 때 **Run audit** 눌러.",
}

WALKTHROUGH_RECHECK_OK = {
    'en': "✓ Confirmed. Marking as done.",
    'ko': "✓ 확인됨. 완료 처리.",
}

WALKTHROUGH_RECHECK_FAIL = {
    'en': (
        "Still not showing on my end. Try **Take me there** again, or "
        "**Mark as done** if you're sure."
    ),
    'ko': (
        "아직 안 보여. **Take me there**로 다시 시도하거나, "
        "확실히 했으면 **Mark as done** 눌러."
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
        "Final boss quiz. Select every feature that's actually in YOUR version. "
        "Some are decoys from the other version, some are made up. "
        "Need ≥80% to pass. Unlimited retries."
    ),
    'ko': (
        "최종 보스 퀴즈. 네 버전에 실제로 있는 기능을 모두 골라. "
        "어떤 건 다른 버전 함정, 어떤 건 가짜. "
        "80% 이상 맞아야 통과. 무한 재시도."
    ),
}

BOSS_QUIZ_PASS_TEMPLATE = {
    'en': "🦉 Passed at {score}%. That's it from me until the next milestone.",
    'ko': "🦉 {score}%로 통과. 다음 마일스톤 전까지 잠수 탈게.",
}

BOSS_QUIZ_FAIL_TEMPLATE = {
    'en': (
        "{score}% — need 80%.\n{wrong_lines}\n\n"
        "Let's go again."
    ),
    'ko': (
        "{score}% — 80% 필요.\n{wrong_lines}\n\n"
        "다시 가자."
    ),
}

BOSS_QUIZ_MISSED = {
    'en': "Missed — {label}: that's in your version, should have selected it",
    'ko': "놓침 — {label}: 네 버전에 있음, 골랐어야 함",
}

BOSS_QUIZ_WRONG_DISTRACTOR = {
    'en': "Wrong — {label}: not in your version (from the other version)",
    'ko': "오답 — {label}: 네 버전 아님 (다른 버전 거)",
}

BOSS_QUIZ_WRONG_ABSURD = {
    'en': "Wrong — {label}: made up",
    'ko': "오답 — {label}: 가짜",
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
    'en': "What do you want to know? Tap one.",
    'ko': "뭐가 궁금해? 하나 눌러봐.",
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
                "Yes. Add anyone. Their experience may differ since they "
                "won't be on a research version."
            ),
            'ko': (
                "응. 누구든 추가해도 돼. 연구 버전이 아니어서 경험은 다를 수 있어."
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
                "Data freezes after May 31. Short tail period for access — "
                "admin will announce the exact date."
            ),
            'ko': (
                "5월 31일 이후 데이터 동결. 짧은 정리 기간 있음 — "
                "어드민이 정확한 날짜 알려줄 거야."
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
            'en': "Tap **Call admin** in the welcome card. We'll figure it out.",
            'ko': "위 카드의 **Call admin** 눌러. 같이 해결하자.",
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
                "Not via me. There's a separate VersionSwitchRequest flow — "
                "talk to admin if you really need it."
            ),
            'ko': (
                "나로는 안 돼. 별도 VersionSwitchRequest 절차 있어 — "
                "정말 필요하면 어드민에게 얘기해."
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
                "Widget install is a participation requirement. "
                "Can't auto-detect on your phone, so the screenshot is the proof."
            ),
            'ko': (
                "위젯 설치는 참여 요건. 자동 감지가 안 돼서 스크린샷이 증빙이야."
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
                "Surveys and study reminders go through push. "
                "Without them you'll miss things and your data won't be complete."
            ),
            'ko': (
                "설문이랑 연구 알림이 푸시로 가. 안 켜두면 놓쳐서 데이터가 불완전해."
            ),
        },
    },
    {
        'key': 'what_witty_does',
        'question': {
            'en': 'What does WITty actually do?',
            'ko': 'WITty가 뭐 해?',
        },
        'answer': {
            'en': (
                "Walk you through the study, run audits, point you to features "
                "you haven't tried."
            ),
            'ko': (
                "연구 안내, audit 실행, 안 써본 기능 알려주기."
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
        'en': "If a participant pings a check-in in the forest and no one is around, did they ping?",
        'ko': "참여자가 숲에서 체크인을 ping했는데 아무도 못 봤다면, 정말 ping한 거야?",
    },
    {
        'en': "Sometimes I think about owls.",
        'ko': "가끔 부엉이에 대해 생각해.",
    },
    {
        'en': "The secret is there is no secret. The second secret is that one's free.",
        'ko': "비밀은 비밀이 없다는 거야. 두 번째 비밀은 그건 무료라는 거.",
    },
    {
        'en': "I'd tell you a UDP joke but you might not get it.",
        'ko': "UDP 농담 알려줄까 했는데 안 들릴 수 있어.",
    },
    {
        'en': "Today's vibe: cautious optimism with a side of confused.",
        'ko': "오늘 vibe: 조심스러운 낙관 + 약간의 혼란.",
    },
    {
        'en': "I just learned what a treadmill is. Seems unkind.",
        'ko': "방금 러닝머신이 뭔지 알았어. 참 잔인해 보여.",
    },
]

CAT_REPLY = {
    'en': "A cat. Acknowledged.",
    'ko': "고양이. 인지했음.",
}

WHO_AM_I_REPLY = {
    'en': "A WhoamI Today participant.",
    'ko': "WhoamI Today 참여자.",
}

# ---------- Welcome card inlines ----------

WC_KICKOFF_DONE_PRE_AUDIT = {
    'en': "Kickoff done. Run audit when you've explored a bit.",
    'ko': "킥오프 완료. 좀 둘러보고 audit 돌려.",
}

WC_AUDIT_DONE_PRE_BOSS = {
    'en': "Audit done. Boss quiz unlocked.",
    'ko': "Audit 완료. 보스 퀴즈 열림.",
}

WC_BOSS_PASSED_PRE_SWAP = {
    'en': "Done. See you May 18 for the swap.",
    'ko': "끝. 5월 18일 버전 전환 때 보자.",
}

WC_TIME_TO_ONBOARD_W = {
    'en': "You're on version W. Ready to start?",
    'ko': "너는 버전 W야. 시작할까?",
}

WC_TIME_TO_ONBOARD_Q = {
    'en': "You're on version Q. Ready to start?",
    'ko': "너는 버전 Q야. 시작할까?",
}

WC_POST_SWAP_W = {
    'en': "Swap happened. You're on version W now. Round 2?",
    'ko': "전환 됐어. 이제 버전 W. 2라운드?",
}

WC_POST_SWAP_Q = {
    'en': "Swap happened. You're on version Q now. Round 2?",
    'ko': "전환 됐어. 이제 버전 Q. 2라운드?",
}

WC_MID_FLOW = {
    'en': "Mid-step.",
    'ko': "진행 중.",
}

WC_AUDIT_IN_PROGRESS = {
    'en': "Audit in progress.",
    'ko': "Audit 진행 중.",
}

WC_WALKTHROUGH_IN_PROGRESS = {
    'en': "Walking through features.",
    'ko': "기능 안내 중.",
}

WC_DEFAULT_SILENT = {
    'en': "All set.",
    'ko': "준비 완료.",
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
        "  • **Run audit** — feature progress\n"
        "  • `faq` — common questions\n"
        "  • **Call admin** — escalate to a person\n"
        "Quiet otherwise."
    ),
    'ko': (
        "할 수 있는 것들:\n"
        "  • **Run audit** — 기능 진척도\n"
        "  • `faq` — 자주 묻는 질문\n"
        "  • **Call admin** — 사람한테 escalate\n"
        "그 외에는 조용히 있을게."
    ),
}
