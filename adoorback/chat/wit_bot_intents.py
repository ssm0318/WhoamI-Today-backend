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

    if payload == 'start_onboarding':
        state_mod.set_intent(state, 'kickoff_welcome', step=0)
        return _kickoff_welcome_intro()

    if payload == 'resume_onboarding':
        handler = HANDLERS.get(state.current_intent, idle_handler)
        return handler(state, message, user)

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
    from chat.wit_bot_copy import WIDGET_PROMPT_COPY
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
}
