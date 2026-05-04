"""Intent handlers for the wit_bot conversation engine.

Each handler signature: (state, incoming_message, user) -> list[(text, bot_payload)]
Handlers mutate state.current_intent / state.step / state.context as needed.

Flow:
    idle -> kickoff_welcome -> kickoff_quiz_1 -> kickoff_quiz_2 -> kickoff_quiz_3
         -> kickoff_push -> kickoff_friend -> kickoff_widget -> idle (kickoff complete)
"""
from __future__ import annotations

from chat import wit_bot_state as state_mod
from chat.wit_bot_payloads import card_with_buttons, multi_select, upload_request


# ---------- Idle ----------

def idle_handler(state, message, user):
    """Default when no intent is active. Routes special payloads, else nudges."""
    payload = (message.bot_payload or {}).get('payload')
    text = (message.content or '').strip().lower()

    if payload == 'start_onboarding':
        state_mod.set_intent(state, 'kickoff_welcome', step=0)
        return _kickoff_welcome_intro()

    if payload == 'resume_onboarding':
        handler = HANDLERS.get(state.current_intent, idle_handler)
        return handler(state, message, user)

    if payload == 'run_audit':
        state_mod.set_intent(state, 'audit', step=0)
        return audit_handler(state, message, user)

    if payload == 'take_boss_quiz':
        state_mod.set_intent(state, 'final_quiz', step=0)
        return final_quiz_handler(state, message, user)

    if payload and payload.startswith('faq:'):
        return _faq_answer(payload.split(':', 1)[1])

    # Text-triggered easter eggs / commands
    if text in ('faq', 'help me', 'questions'):
        return _faq_menu()
    if text in ('wit?', 'wit', 'witty?'):
        return _wit_reply()
    if text == 'who am i':
        from chat.wit_bot_copy import WHO_AM_I_REPLY
        return [(WHO_AM_I_REPLY, None)]
    if text == 'help':
        from chat.wit_bot_copy import HELP_REPLY
        return [(HELP_REPLY, None)]
    if '🐈' in text or '🐱' in text:
        from chat.wit_bot_copy import CAT_REPLY
        return [(CAT_REPLY, None)]

    return [
        ("not sure what that was. try the welcome card up top, or type `wit?`.", None),
    ]


def _kickoff_welcome_intro():
    from chat.wit_bot_copy import WELCOME_INTRO
    return [(WELCOME_INTRO, card_with_buttons([
        {'label': "let's go", 'payload': 'kickoff_welcome_continue'},
    ]))]


# ---------- kickoff_welcome ----------

def kickoff_welcome_handler(state, message, user):
    payload = (message.bot_payload or {}).get('payload')
    if payload == 'kickoff_welcome_continue':
        return _enter_kickoff_quiz_1(state)
    return _kickoff_welcome_intro()


# ---------- kickoff_quiz_1 (multi-select study requirements) ----------

def _enter_kickoff_quiz_1(state):
    from chat.wit_bot_copy import QUIZ_1_STUDY_REQUIREMENTS as q
    state_mod.set_intent(state, 'kickoff_quiz_1', step=0)
    payload = multi_select(intent='kickoff_quiz_1', options=q['options'])
    return [(q['prompt'], payload)]


def kickoff_quiz_1_handler(state, message, user):
    payload = message.bot_payload or {}
    if payload.get('kind') != 'multi_select_response' or payload.get('intent') != 'kickoff_quiz_1':
        return _enter_kickoff_quiz_1(state)

    from chat.wit_bot_copy import QUIZ_1_STUDY_REQUIREMENTS as q
    selected = set(payload.get('selected', []))
    by_value = {o['value']: o for o in q['options']}

    correct_total = sum(1 for o in q['options'] if o['correct'])
    incorrect_total = sum(1 for o in q['options'] if not o['correct'])
    correct_selected = sum(1 for v in selected if by_value.get(v, {}).get('correct'))
    correct_omitted = sum(
        1 for o in q['options'] if not o['correct'] and o['value'] not in selected
    )

    score = (correct_selected + correct_omitted) / (correct_total + incorrect_total)

    lines = ["here's how you did:"]
    for o in q['options']:
        was_selected = o['value'] in selected
        if o['correct'] and was_selected:
            lines.append(f"  ✓ {o['label']}")
        elif o['correct'] and not was_selected:
            lines.append(f"  ✗ MISSED — {o['label']}: {o.get('explanation', '')}")
        elif not o['correct'] and was_selected:
            lines.append(f"  ✗ WRONG — {o['label']}: {o.get('explanation', '')}")
    lines.append(f"\nscore: {int(score * 100)}%")
    reveal = "\n".join(lines)

    state_mod.set_progress(state, user.current_ver, 'kickoff', {
        'quiz_1': {'score': score, 'selected': list(selected)},
    })

    return [(reveal, None), *_enter_kickoff_quiz_2(state)]


# ---------- kickoff_quiz_2 (single-select swap timing) ----------

def _enter_kickoff_quiz_2(state):
    from chat.wit_bot_copy import QUIZ_2_SWAP_TIMING as q
    state_mod.set_intent(state, 'kickoff_quiz_2', step=0)
    payload = card_with_buttons([
        {'label': o['label'], 'payload': f"q2:{o['value']}"} for o in q['options']
    ])
    return [(q['prompt'], payload)]


def kickoff_quiz_2_handler(state, message, user):
    payload = (message.bot_payload or {}).get('payload', '')
    if not payload.startswith('q2:'):
        return _enter_kickoff_quiz_2(state)

    from chat.wit_bot_copy import QUIZ_2_SWAP_TIMING as q
    chosen_value = payload.split(':', 1)[1]
    chosen = next((o for o in q['options'] if o['value'] == chosen_value), None)

    prog = state_mod.progress_for(state, user.current_ver)
    quiz_state = prog.get('kickoff', {}).get('quiz_2', {'attempts': 0})
    quiz_state['attempts'] = quiz_state.get('attempts', 0) + 1

    if chosen and chosen['correct']:
        quiz_state['correct'] = True
        state_mod.set_progress(state, user.current_ver, 'kickoff', {'quiz_2': quiz_state})
        return [(q['reveal_correct'], None), *_enter_kickoff_quiz_3(state)]

    state_mod.set_progress(state, user.current_ver, 'kickoff', {'quiz_2': quiz_state})
    payload = card_with_buttons([
        {'label': o['label'], 'payload': f"q2:{o['value']}"} for o in q['options']
    ])
    return [(q['reveal_wrong'], None), ("try again:", payload)]


# ---------- kickoff_quiz_3 (single-select surveys location) ----------

def _enter_kickoff_quiz_3(state):
    from chat.wit_bot_copy import QUIZ_3_SURVEYS_LOCATION as q
    state_mod.set_intent(state, 'kickoff_quiz_3', step=0)
    payload = card_with_buttons([
        {'label': o['label'], 'payload': f"q3:{o['value']}"} for o in q['options']
    ])
    return [(q['prompt'], payload)]


def kickoff_quiz_3_handler(state, message, user):
    payload = (message.bot_payload or {}).get('payload', '')
    if not payload.startswith('q3:'):
        return _enter_kickoff_quiz_3(state)

    from chat.wit_bot_copy import QUIZ_3_SURVEYS_LOCATION as q
    chosen_value = payload.split(':', 1)[1]
    chosen = next((o for o in q['options'] if o['value'] == chosen_value), None)

    prog = state_mod.progress_for(state, user.current_ver)
    quiz_state = prog.get('kickoff', {}).get('quiz_3', {'attempts': 0})
    quiz_state['attempts'] = quiz_state.get('attempts', 0) + 1

    if chosen and chosen['correct']:
        quiz_state['correct'] = True
        state_mod.set_progress(state, user.current_ver, 'kickoff', {'quiz_3': quiz_state})
        return [(q['reveal_correct'], None), *_enter_kickoff_push(state, user)]

    state_mod.set_progress(state, user.current_ver, 'kickoff', {'quiz_3': quiz_state})
    payload = card_with_buttons([
        {'label': o['label'], 'payload': f"q3:{o['value']}"} for o in q['options']
    ])
    return [(q['reveal_wrong'], None), ("try again:", payload)]


# ---------- kickoff_push (FCM check) ----------

def _enter_kickoff_push(state, user):
    state_mod.set_intent(state, 'kickoff_push', step=0)
    return _check_push_and_continue(state, user)


def _check_push_and_continue(state, user):
    from custom_fcm.models import CustomFCMDevice
    from chat.wit_bot_copy import PUSH_NOTIF_ON_COPY, PUSH_NOTIF_OFF_COPY

    has_device = CustomFCMDevice.objects.filter(user=user, active=True).exists()
    if has_device:
        state_mod.set_progress(state, user.current_ver, 'kickoff', {'push_notif': 'ok'})
        return [(PUSH_NOTIF_ON_COPY, None), *_enter_kickoff_friend(state, user)]

    state_mod.set_progress(state, user.current_ver, 'kickoff', {'push_notif': 'asked'})
    return [(PUSH_NOTIF_OFF_COPY, card_with_buttons([
        {'label': "Done — they're on now", 'payload': 'kickoff_push_done'},
    ]))]


def kickoff_push_handler(state, message, user):
    return _check_push_and_continue(state, user)


# ---------- kickoff_friend (Connection check) ----------

def _enter_kickoff_friend(state, user):
    state_mod.set_intent(state, 'kickoff_friend', step=0)
    return _check_friend_and_continue(state, user)


def _check_friend_and_continue(state, user):
    from chat.wit_bot_copy import FRIEND_MIN_OK_COPY, FRIEND_MIN_NEEDED_COPY

    has_friend = user.friends.exists()
    if has_friend:
        state_mod.set_progress(state, user.current_ver, 'kickoff', {'friend_min': 'ok'})
        return [(FRIEND_MIN_OK_COPY, None), *_enter_kickoff_widget(state, user)]

    state_mod.set_progress(state, user.current_ver, 'kickoff', {'friend_min': 'asked'})
    return [(FRIEND_MIN_NEEDED_COPY, card_with_buttons([
        {'label': 'Done — added one', 'payload': 'kickoff_friend_done'},
    ]))]


def kickoff_friend_handler(state, message, user):
    return _check_friend_and_continue(state, user)


# ---------- kickoff_widget (screenshot collection) ----------

def _enter_kickoff_widget(state, user):
    """Prompt for widget screenshot. If user already has an approved or
    pending widget shot from a prior version's kickoff, skip and complete."""
    from chat.models import OnboardingScreenshot
    from chat.wit_bot_copy import WIDGET_PROMPT_COPY

    if OnboardingScreenshot.objects.filter(
        user=user, kind='widget', status__in=['approved', 'pending'],
    ).exists():
        # Re-using the V1 widget shot — skip directly to complete.
        state_mod.set_progress(state, user.current_ver, 'kickoff', {
            'widget_screenshot': {'status': 'reused_from_prior'},
        })
        return _enter_kickoff_complete(state, user)

    state_mod.set_intent(state, 'kickoff_widget', step=0)
    return [(WIDGET_PROMPT_COPY, upload_request(context='widget'))]


def kickoff_widget_handler(state, message, user):
    from chat.wit_bot_copy import WIDGET_RECEIVED_COPY
    from chat.models import OnboardingScreenshot

    payload = message.bot_payload or {}
    is_upload_resp = (
        payload.get('kind') == 'upload_response' and payload.get('context') == 'widget'
    )
    if not is_upload_resp or not message.image:
        return _enter_kickoff_widget(state, user)

    OnboardingScreenshot.objects.create(
        user=user,
        version=user.current_ver,
        kind='widget',
        message=message,
    )
    state_mod.set_progress(state, user.current_ver, 'kickoff', {
        'widget_screenshot': {'status': 'pending', 'message_id': message.id},
    })
    return [(WIDGET_RECEIVED_COPY, None), *_enter_kickoff_complete(state, user)]


def _enter_kickoff_complete(state, user):
    from chat.wit_bot_copy import WRAP_KICKOFF
    state_mod.set_intent(state, '', step=0)
    state_mod.set_progress(state, user.current_ver, 'kickoff', {'completed': True})
    return [(WRAP_KICKOFF, None)]


# ---------- Audit ----------

def _predicate_status(predicate, user):
    """Return 'engaged' | 'self_reported' | 'not_yet'."""
    from chat.models import OnboardingEvent
    if predicate.is_engaged(user):
        return 'engaged'
    if OnboardingEvent.objects.filter(
        user=user, event_key=f'self_report:{predicate.feature_key}',
    ).exists():
        return 'self_reported'
    return 'not_yet'


def _build_audit_report(user):
    """Run all predicates for the user's version, return (engaged, missing) lists."""
    from chat.wit_bot_predicates import predicates_for
    engaged = []
    missing = []
    for pred in predicates_for(user.current_ver):
        status = _predicate_status(pred, user)
        if status in ('engaged', 'self_reported'):
            engaged.append(pred)
        else:
            missing.append(pred)
    return engaged, missing


def audit_handler(state, message, user):
    """Initial entry to audit + branch on user's response."""
    from chat.wit_bot_copy import (
        AUDIT_HEADER, AUDIT_RESULT_TEMPLATE, AUDIT_NOTHING_MISSING,
        EXPLORE_LATER, JUST_LIST_INTRO,
    )
    from chat.wit_bot_payloads import card_with_buttons

    payload = (message.bot_payload or {}).get('payload', '')

    # Branch on follow-up choice
    if payload == 'audit_walkthrough':
        return _enter_walkthrough(state, user)
    if payload == 'audit_just_list':
        _, missing = _build_audit_report(user)
        if not missing:
            state_mod.set_intent(state, '', step=0)
            return [(AUDIT_NOTHING_MISSING, None)]
        out = [(JUST_LIST_INTRO, None)]
        for pred in missing:
            out.append(_walkthrough_feature_card(pred, mode='list'))
        state_mod.set_intent(state, '', step=0)
        return out
    if payload == 'audit_later':
        state_mod.set_intent(state, '', step=0)
        return [(EXPLORE_LATER, None)]

    # Default: fresh audit run
    engaged, missing = _build_audit_report(user)

    if not missing:
        state_mod.set_intent(state, '', step=0)
        state_mod.set_progress(state, user.current_ver, 'audit', {
            'last_engaged_count': len(engaged),
            'last_missing_count': 0,
        })
        return [(AUDIT_HEADER, None), (AUDIT_NOTHING_MISSING, None)]

    engaged_lines = "\n".join(f"  ✓ {p.display_name}" for p in engaged) or "  (nothing yet)"
    missing_lines = "\n".join(f"  ⏳ {p.display_name}" for p in missing)
    body = AUDIT_RESULT_TEMPLATE.format(
        engaged_count=len(engaged),
        engaged_list=engaged_lines,
        missing_count=len(missing),
        missing_list=missing_lines,
    )
    state_mod.set_progress(state, user.current_ver, 'audit', {
        'last_engaged_count': len(engaged),
        'last_missing_count': len(missing),
    })

    return [
        (AUDIT_HEADER, None),
        (body, card_with_buttons([
            {'label': 'Walk me through them', 'payload': 'audit_walkthrough'},
            {'label': 'Just give me the list', 'payload': 'audit_just_list'},
            {'label': "I'll explore, audit me later", 'payload': 'audit_later'},
        ])),
    ]


# ---------- Walkthrough ----------

def _walkthrough_feature_card(predicate, mode='walkthrough'):
    """Build a deep_link_card for one feature.

    mode='walkthrough' → 3 buttons: Take me there / Mark as done / Skip
    mode='list' → 1 button: Take me there
    """
    from chat.wit_bot_payloads import card_with_buttons

    text = f"**{predicate.display_name}**\n{predicate.description}"

    buttons = []
    if predicate.deep_link:
        buttons.append({'label': 'Take me there', 'navigate_to': predicate.deep_link})

    if mode == 'walkthrough':
        buttons.append({
            'label': 'Mark as done',
            'payload': f'walkthrough_done:{predicate.feature_key}',
        })
        buttons.append({
            'label': 'Skip for now',
            'payload': f'walkthrough_skip:{predicate.feature_key}',
        })

    return (text, card_with_buttons(buttons))


def _enter_walkthrough(state, user):
    from chat.wit_bot_copy import WALKTHROUGH_INTRO, AUDIT_NOTHING_MISSING

    _, missing = _build_audit_report(user)
    if not missing:
        state_mod.set_intent(state, '', step=0)
        return [(AUDIT_NOTHING_MISSING, None)]

    state_mod.set_intent(state, 'walkthrough', step=0)
    state_mod.set_progress(state, user.current_ver, 'walkthrough', {
        'missing_keys': [p.feature_key for p in missing],
        'index': 0,
    })

    first = missing[0]
    return [
        (WALKTHROUGH_INTRO, None),
        _walkthrough_feature_card(first, mode='walkthrough'),
    ]


def walkthrough_handler(state, message, user):
    from chat.wit_bot_copy import WALKTHROUGH_COMPLETE
    from chat.models import OnboardingEvent
    from chat.wit_bot_predicates import predicate_by_key

    payload = (message.bot_payload or {}).get('payload', '')
    prog = state_mod.progress_for(state, user.current_ver)
    walk = prog.get('walkthrough', {})
    missing_keys = walk.get('missing_keys', [])
    index = walk.get('index', 0)

    if not missing_keys:
        state_mod.set_intent(state, '', step=0)
        return [(WALKTHROUGH_COMPLETE, None)]

    # Process current feature's response
    advanced = False
    if payload.startswith('walkthrough_done:'):
        feature_key = payload.split(':', 1)[1]
        OnboardingEvent.objects.create(
            user=user, version=user.current_ver,
            event_key=f'self_report:{feature_key}',
        )
        advanced = True
    elif payload.startswith('walkthrough_skip:'):
        advanced = True

    if advanced:
        index += 1
        state_mod.set_progress(state, user.current_ver, 'walkthrough', {'index': index})

    # If done, wrap up
    if index >= len(missing_keys):
        state_mod.set_intent(state, '', step=0)
        return [(WALKTHROUGH_COMPLETE, None)]

    # Otherwise, send next feature card
    next_pred = predicate_by_key(missing_keys[index])
    if next_pred is None:
        # Skip stale entries
        index += 1
        state_mod.set_progress(state, user.current_ver, 'walkthrough', {'index': index})
        if index >= len(missing_keys):
            state_mod.set_intent(state, '', step=0)
            return [(WALKTHROUGH_COMPLETE, None)]
        next_pred = predicate_by_key(missing_keys[index])

    return [_walkthrough_feature_card(next_pred, mode='walkthrough')]


# ---------- Boss quiz (end-of-version final exam) ----------

def _build_final_quiz_options(version):
    """Build quiz options dynamically. Real-in-version → correct;
    real-only-in-other → incorrect distractor; absurd bank → incorrect.
    """
    import random
    from chat.wit_bot_copy import ABSURD_FEATURES
    from chat.wit_bot_predicates import PREDICATES

    other_version = 'version_q' if version == 'version_w' else 'version_w'
    options = []

    for p in PREDICATES:
        if version in p.versions:
            options.append({
                'value': f'real:{p.feature_key}',
                'label': p.display_name,
                'correct': True,
            })
        elif other_version in p.versions:
            options.append({
                'value': f'distractor:{p.feature_key}',
                'label': p.display_name,
                'correct': False,
            })

    for ab in ABSURD_FEATURES:
        slug = ab.lower().replace(' ', '_').replace('-', '_')
        options.append({
            'value': f'absurd:{slug}',
            'label': ab,
            'correct': False,
        })

    random.shuffle(options)
    return options


def _enter_final_quiz(state, user):
    from chat.wit_bot_copy import BOSS_QUIZ_INTRO
    from chat.wit_bot_payloads import multi_select

    options = _build_final_quiz_options(user.current_ver)

    prog = state_mod.progress_for(state, user.current_ver)
    fq = prog.get('final_quiz', {})
    attempts = fq.get('attempts_history', [])

    state_mod.set_intent(state, 'final_quiz', step=0)
    state_mod.set_progress(state, user.current_ver, 'final_quiz', {
        'current_options': [
            {'value': o['value'], 'label': o['label'], 'correct': o['correct']}
            for o in options
        ],
        'attempt_number': len(attempts) + 1,
    })

    return [(BOSS_QUIZ_INTRO, multi_select(intent='final_quiz', options=options))]


def final_quiz_handler(state, message, user):
    from chat.wit_bot_copy import BOSS_QUIZ_PASS_TEMPLATE, BOSS_QUIZ_FAIL_TEMPLATE

    payload = message.bot_payload or {}
    if payload.get('kind') != 'multi_select_response' or payload.get('intent') != 'final_quiz':
        return _enter_final_quiz(state, user)

    prog = state_mod.progress_for(state, user.current_ver)
    fq = prog.get('final_quiz', {})
    saved_options = fq.get('current_options', [])
    if not saved_options:
        return _enter_final_quiz(state, user)

    selected = set(payload.get('selected', []))

    correct_count = sum(
        1 for o in saved_options
        if (o['value'] in selected) == bool(o['correct'])
    )
    total = len(saved_options)
    score = correct_count / total if total else 0.0

    attempts_history = fq.get('attempts_history', [])
    attempts_history.append({'score': score, 'selected': list(selected)})

    if score >= 0.8:
        state_mod.set_progress(state, user.current_ver, 'final_quiz', {
            'attempts_history': attempts_history,
            'passed': True,
            'final_score': score,
        })
        state_mod.set_intent(state, '', step=0)
        return [(BOSS_QUIZ_PASS_TEMPLATE.format(score=int(score * 100)), None)]

    # Fail — reveal wrong + retry
    wrong_lines = []
    for o in saved_options:
        was_selected = o['value'] in selected
        if o['correct'] and not was_selected:
            wrong_lines.append(
                f"  ✗ MISSED — {o['label']}: that IS in your version, you should have selected it"
            )
        elif not o['correct'] and was_selected:
            origin = (
                "from the OTHER version" if o['value'].startswith('distractor:')
                else "completely made up"
            )
            wrong_lines.append(
                f"  ✗ WRONG — {o['label']}: not in your version ({origin})"
            )

    reveal = BOSS_QUIZ_FAIL_TEMPLATE.format(
        score=int(score * 100),
        wrong_lines='\n'.join(wrong_lines) if wrong_lines else '  (somehow none — tap Submit again)',
    )

    state_mod.set_progress(state, user.current_ver, 'final_quiz', {
        'attempts_history': attempts_history,
    })

    # Auto re-enter for retry
    return [(reveal, None), *_enter_final_quiz(state, user)]


# ---------- FAQ ----------

def _faq_menu():
    from chat.wit_bot_copy import FAQ_ENTRIES, FAQ_MENU_INTRO
    from chat.wit_bot_payloads import card_with_buttons

    return [(
        FAQ_MENU_INTRO,
        card_with_buttons([
            {'label': e['question'], 'payload': f'faq:{e["key"]}'} for e in FAQ_ENTRIES
        ]),
    )]


def _faq_answer(faq_key):
    from chat.wit_bot_copy import FAQ_ENTRIES

    entry = next((e for e in FAQ_ENTRIES if e['key'] == faq_key), None)
    if entry is None:
        return _faq_menu()
    return [(entry['answer'], None)]


def _wit_reply():
    import random
    from chat.wit_bot_copy import WIT_REPLIES
    return [(random.choice(WIT_REPLIES), None)]


# ---------- Dispatch table ----------

HANDLERS = {
    '': idle_handler,
    'kickoff_welcome': kickoff_welcome_handler,
    'kickoff_quiz_1': kickoff_quiz_1_handler,
    'kickoff_quiz_2': kickoff_quiz_2_handler,
    'kickoff_quiz_3': kickoff_quiz_3_handler,
    'kickoff_push': kickoff_push_handler,
    'kickoff_friend': kickoff_friend_handler,
    'kickoff_widget': kickoff_widget_handler,
    'audit': audit_handler,
    'walkthrough': walkthrough_handler,
    'final_quiz': final_quiz_handler,
}
