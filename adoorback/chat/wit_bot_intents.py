"""Intent handlers for the wit_bot conversation engine.

Each handler signature: (state, incoming_message, user) -> list[(text, bot_payload)]
Handlers mutate state.current_intent / state.step / state.context as needed.

Flow:
    idle -> kickoff_welcome -> kickoff_quiz_1 -> kickoff_quiz_2 -> kickoff_quiz_3
         -> kickoff_push -> kickoff_friend -> kickoff_widget -> idle (kickoff complete)
"""
from __future__ import annotations

from chat import wit_bot_state as state_mod
from chat.wit_bot_copy import t
from chat.wit_bot_payloads import card_with_buttons, multi_select, upload_request


# ---------- Global commands ----------

def try_global_command(state, message, user):
    """Handle commands that should work from ANY intent (welcome-card buttons +
    universal text commands). Returns a list of replies if matched, else None.

    Called by the engine before intent-specific dispatch. This is what makes
    the welcome card's Run audit / Take boss quiz / Resume buttons work even
    when the user is mid-quiz or mid-walkthrough.
    """
    payload = (message.bot_payload or {}).get('payload', '') or ''
    text = (message.content or '').strip().lower()

    # Welcome-card button payloads
    if payload == 'run_audit':
        state_mod.set_intent(state, 'audit', step=0)
        return audit_handler(state, message, user)

    if payload == 'take_boss_quiz':
        state_mod.set_intent(state, 'final_quiz', step=0)
        return final_quiz_handler(state, message, user)

    if payload == 'start_onboarding':
        state_mod.set_intent(state, 'kickoff_welcome', step=0)
        return _kickoff_welcome_intro(user)

    if payload and payload.startswith('faq:'):
        return _faq_answer(payload.split(':', 1)[1], user)

    # Text-typed global commands — only fire when no payload (don't eat
    # button taps that happen to have label='faq' etc.)
    if not payload:
        # Run audit by typing
        if text in ('run audit', 'audit', 'run_audit'):
            state_mod.set_intent(state, 'audit', step=0)
            return audit_handler(state, message, user)
        if text in ('faq', 'help me', 'questions'):
            return _faq_menu(user)
        if text in ('wit?', 'wit', 'witty?'):
            return _wit_reply(user)
        if text == 'who am i':
            from chat.wit_bot_copy import WHO_AM_I_REPLY
            return [(t(WHO_AM_I_REPLY, user), None)]
        if text == 'help':
            from chat.wit_bot_copy import HELP_REPLY
            return [(t(HELP_REPLY, user), None)]
        if '🐈' in text or '🐱' in text:
            from chat.wit_bot_copy import CAT_REPLY
            return [(t(CAT_REPLY, user), None)]

    return None


# ---------- Idle ----------

def idle_handler(state, message, user):
    """Default when no intent is active. Global commands have already been
    handled by `try_global_command` before this is called, so this only deals
    with the unknown-input nudge."""
    lang = getattr(user, 'language', 'en') or 'en'
    if lang == 'ko':
        nudge = "잘 모르겠는 입력이야. 위 카드 사용하거나 `wit?` 쳐봐."
    else:
        nudge = "not sure what that was. try the welcome card up top, or type `wit?`."
    return [(nudge, None)]


def _kickoff_welcome_intro(user):
    from chat.wit_bot_copy import LETS_GO, WELCOME_INTRO
    return [(t(WELCOME_INTRO, user), card_with_buttons([
        {'label': t(LETS_GO, user), 'payload': 'kickoff_welcome_continue'},
    ]))]


# ---------- kickoff_welcome ----------

def kickoff_welcome_handler(state, message, user):
    """At the very first step, ANY input (let's go button, resume button,
    or free text) advances to Quiz 1. Avoids the infinite re-prompt loop
    where the welcome card's Resume button kept re-rendering the intro."""
    return _enter_kickoff_quiz_1(state, user)


# ---------- kickoff_quiz_1 (multi-select study requirements) ----------

def _quiz_1_options_for_user(user):
    from chat.wit_bot_copy import QUIZ_1_STUDY_REQUIREMENTS as q
    return [
        {'value': o['value'], 'label': t(o['label'], user)}
        for o in q['options']
    ]


def _enter_kickoff_quiz_1(state, user, retry_intro=None):
    from chat.wit_bot_copy import QUIZ_1_STUDY_REQUIREMENTS as q
    state_mod.set_intent(state, 'kickoff_quiz_1', step=0)
    payload = multi_select(intent='kickoff_quiz_1', options=_quiz_1_options_for_user(user))
    prompt = retry_intro if retry_intro else t(q['prompt'], user)
    return [(prompt, payload)]


def kickoff_quiz_1_handler(state, message, user):
    payload = message.bot_payload or {}
    if payload.get('kind') != 'multi_select_response' or payload.get('intent') != 'kickoff_quiz_1':
        return _enter_kickoff_quiz_1(state, user)

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

    lang = getattr(user, 'language', 'en') or 'en'
    header = "결과:" if lang == 'ko' else "Here's how you did:"
    score_label = "점수" if lang == 'ko' else "Score"
    label_missed = "놓침" if lang == 'ko' else "MISSED"
    label_wrong = "오답" if lang == 'ko' else "WRONG"

    lines = [header]
    for o in q['options']:
        was_selected = o['value'] in selected
        loc_label = t(o['label'], user)
        loc_explanation = t(o.get('explanation', ''), user)
        if o['correct'] and was_selected:
            lines.append(f"  ✓ {loc_label}")
        elif o['correct'] and not was_selected:
            lines.append(f"  ✗ {label_missed} — {loc_label}: {loc_explanation}")
        elif not o['correct'] and was_selected:
            lines.append(f"  ✗ {label_wrong} — {loc_label}: {loc_explanation}")
    lines.append(f"\n{score_label}: {int(score * 100)}%")
    reveal = "\n".join(lines)

    # Track attempt history; require ≥80% to advance.
    prog = state_mod.progress_for(state, user.current_ver)
    quiz_state = prog.get('kickoff', {}).get('quiz_1', {'attempts': 0})
    quiz_state['attempts'] = quiz_state.get('attempts', 0) + 1
    quiz_state['score'] = score
    quiz_state['selected'] = list(selected)

    if score >= 0.8:
        quiz_state['passed'] = True
        state_mod.set_progress(state, user.current_ver, 'kickoff', {'quiz_1': quiz_state})
        return [(reveal, None), *_enter_kickoff_quiz_2(state, user)]

    # Below threshold — show reveal and re-render the same multi-select.
    state_mod.set_progress(state, user.current_ver, 'kickoff', {'quiz_1': quiz_state})
    retry_label = "80% 이하야. 다시 해봐:" if lang == 'ko' else "Below 80%. Try again:"
    return [(reveal, None), *_enter_kickoff_quiz_1(state, user, retry_intro=retry_label)]


# ---------- kickoff_quiz_2 (single-select swap timing) ----------

def _enter_kickoff_quiz_2(state, user):
    from chat.wit_bot_copy import QUIZ_2_SWAP_TIMING as q
    state_mod.set_intent(state, 'kickoff_quiz_2', step=0)
    payload = card_with_buttons([
        {'label': t(o['label'], user), 'payload': f"q2:{o['value']}"} for o in q['options']
    ])
    return [(t(q['prompt'], user), payload)]


def kickoff_quiz_2_handler(state, message, user):
    payload = (message.bot_payload or {}).get('payload', '')
    if not payload.startswith('q2:'):
        return _enter_kickoff_quiz_2(state, user)

    from chat.wit_bot_copy import QUIZ_2_SWAP_TIMING as q
    chosen_value = payload.split(':', 1)[1]
    chosen = next((o for o in q['options'] if o['value'] == chosen_value), None)

    prog = state_mod.progress_for(state, user.current_ver)
    quiz_state = prog.get('kickoff', {}).get('quiz_2', {'attempts': 0})
    quiz_state['attempts'] = quiz_state.get('attempts', 0) + 1

    if chosen and chosen['correct']:
        quiz_state['correct'] = True
        state_mod.set_progress(state, user.current_ver, 'kickoff', {'quiz_2': quiz_state})
        return [(t(q['reveal_correct'], user), None), *_enter_kickoff_quiz_3(state, user)]

    state_mod.set_progress(state, user.current_ver, 'kickoff', {'quiz_2': quiz_state})
    payload = card_with_buttons([
        {'label': t(o['label'], user), 'payload': f"q2:{o['value']}"} for o in q['options']
    ])
    lang = getattr(user, 'language', 'en') or 'en'
    retry_label = "다시 해봐:" if lang == 'ko' else "try again:"
    return [(t(q['reveal_wrong'], user), None), (retry_label, payload)]


# ---------- kickoff_quiz_3 (single-select surveys location) ----------

def _enter_kickoff_quiz_3(state, user):
    from chat.wit_bot_copy import QUIZ_3_SURVEYS_LOCATION as q
    state_mod.set_intent(state, 'kickoff_quiz_3', step=0)
    payload = card_with_buttons([
        {'label': t(o['label'], user), 'payload': f"q3:{o['value']}"} for o in q['options']
    ])
    return [(t(q['prompt'], user), payload)]


def kickoff_quiz_3_handler(state, message, user):
    payload = (message.bot_payload or {}).get('payload', '')
    if not payload.startswith('q3:'):
        return _enter_kickoff_quiz_3(state, user)

    from chat.wit_bot_copy import QUIZ_3_SURVEYS_LOCATION as q
    chosen_value = payload.split(':', 1)[1]
    chosen = next((o for o in q['options'] if o['value'] == chosen_value), None)

    prog = state_mod.progress_for(state, user.current_ver)
    quiz_state = prog.get('kickoff', {}).get('quiz_3', {'attempts': 0})
    quiz_state['attempts'] = quiz_state.get('attempts', 0) + 1

    if chosen and chosen['correct']:
        quiz_state['correct'] = True
        state_mod.set_progress(state, user.current_ver, 'kickoff', {'quiz_3': quiz_state})
        return [(t(q['reveal_correct'], user), None), *_enter_kickoff_push(state, user)]

    state_mod.set_progress(state, user.current_ver, 'kickoff', {'quiz_3': quiz_state})
    payload = card_with_buttons([
        {'label': t(o['label'], user), 'payload': f"q3:{o['value']}"} for o in q['options']
    ])
    lang = getattr(user, 'language', 'en') or 'en'
    retry_label = "다시 해봐:" if lang == 'ko' else "try again:"
    return [(t(q['reveal_wrong'], user), None), (retry_label, payload)]


# ---------- kickoff_push (FCM check) ----------

def _enter_kickoff_push(state, user):
    state_mod.set_intent(state, 'kickoff_push', step=0)
    return _check_push_and_continue(state, user)


def _check_push_and_continue(state, user):
    from custom_fcm.models import CustomFCMDevice
    from chat.wit_bot_copy import PUSH_DONE_BUTTON, PUSH_NOTIF_OFF_COPY, PUSH_NOTIF_ON_COPY

    has_device = CustomFCMDevice.objects.filter(user=user, active=True).exists()
    if has_device:
        state_mod.set_progress(state, user.current_ver, 'kickoff', {'push_notif': 'ok'})
        return [(t(PUSH_NOTIF_ON_COPY, user), None), *_enter_kickoff_friend(state, user)]

    state_mod.set_progress(state, user.current_ver, 'kickoff', {'push_notif': 'asked'})
    return [(t(PUSH_NOTIF_OFF_COPY, user), card_with_buttons([
        {'label': t(PUSH_DONE_BUTTON, user), 'payload': 'kickoff_push_done'},
    ]))]


def kickoff_push_handler(state, message, user):
    return _check_push_and_continue(state, user)


# ---------- kickoff_friend (Connection check) ----------

def _enter_kickoff_friend(state, user):
    state_mod.set_intent(state, 'kickoff_friend', step=0)
    return _check_friend_and_continue(state, user)


def _check_friend_and_continue(state, user):
    from chat.wit_bot_copy import FRIEND_DONE_BUTTON, FRIEND_MIN_NEEDED_COPY, FRIEND_MIN_OK_COPY

    has_friend = user.friends.exists()
    if has_friend:
        state_mod.set_progress(state, user.current_ver, 'kickoff', {'friend_min': 'ok'})
        return [(t(FRIEND_MIN_OK_COPY, user), None), *_enter_kickoff_widget(state, user)]

    state_mod.set_progress(state, user.current_ver, 'kickoff', {'friend_min': 'asked'})
    return [(t(FRIEND_MIN_NEEDED_COPY, user), card_with_buttons([
        {'label': t(FRIEND_DONE_BUTTON, user), 'payload': 'kickoff_friend_done'},
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
        state_mod.set_progress(state, user.current_ver, 'kickoff', {
            'widget_screenshot': {'status': 'reused_from_prior'},
        })
        return _enter_kickoff_complete(state, user)

    state_mod.set_intent(state, 'kickoff_widget', step=0)
    return [(t(WIDGET_PROMPT_COPY, user), upload_request(context='widget'))]


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
    return [(t(WIDGET_RECEIVED_COPY, user), None), *_enter_kickoff_complete(state, user)]


def _enter_kickoff_complete(state, user):
    from chat.wit_bot_copy import WRAP_KICKOFF
    state_mod.set_intent(state, '', step=0)
    state_mod.set_progress(state, user.current_ver, 'kickoff', {'completed': True})
    return [(t(WRAP_KICKOFF, user), None)]


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
        AUDIT_ALMOST_THERE, AUDIT_BTN_LATER, AUDIT_BTN_LIST, AUDIT_BTN_WALKTHROUGH,
        AUDIT_HEADER, AUDIT_NOTHING_MISSING, AUDIT_RESULT_TEMPLATE,
        EXPLORE_LATER, JUST_LIST_INTRO,
    )

    payload = (message.bot_payload or {}).get('payload', '')

    if payload == 'audit_walkthrough':
        return _enter_walkthrough(state, user)
    if payload == 'audit_just_list':
        _, missing = _build_audit_report(user)
        if not missing:
            state_mod.set_intent(state, '', step=0)
            return [(t(AUDIT_NOTHING_MISSING, user), None)]
        out = [(t(JUST_LIST_INTRO, user), None)]
        for pred in missing:
            out.append(_walkthrough_feature_card(pred, user, mode='list'))
        state_mod.set_intent(state, '', step=0)
        return out
    if payload == 'audit_later':
        state_mod.set_intent(state, '', step=0)
        return [(t(EXPLORE_LATER, user), None)]

    # Default: fresh audit run
    engaged, missing = _build_audit_report(user)

    if not missing:
        state_mod.set_intent(state, '', step=0)
        state_mod.set_progress(state, user.current_ver, 'audit', {
            'last_engaged_count': len(engaged),
            'last_missing_count': 0,
        })
        return [(t(AUDIT_HEADER, user), None), (t(AUDIT_NOTHING_MISSING, user), None)]

    lang = getattr(user, 'language', 'en') or 'en'
    nothing_yet = '  (아직 없음)' if lang == 'ko' else '  (nothing yet)'

    engaged_lines = "\n".join(f"  ✓ {p.display_name}" for p in engaged) or nothing_yet
    missing_lines = "\n".join(f"  ⏳ {p.display_name}" for p in missing)
    body = t(AUDIT_RESULT_TEMPLATE, user).format(
        engaged_count=len(engaged),
        engaged_list=engaged_lines,
        missing_count=len(missing),
        missing_list=missing_lines,
    )
    state_mod.set_progress(state, user.current_ver, 'audit', {
        'last_engaged_count': len(engaged),
        'last_missing_count': len(missing),
    })

    out = [(t(AUDIT_HEADER, user), None)]
    if len(missing) <= 10:
        out.append((t(AUDIT_ALMOST_THERE, user).format(n=len(missing)), None))
    out.append((body, card_with_buttons([
        {'label': t(AUDIT_BTN_WALKTHROUGH, user), 'payload': 'audit_walkthrough'},
        {'label': t(AUDIT_BTN_LIST, user), 'payload': 'audit_just_list'},
        {'label': t(AUDIT_BTN_LATER, user), 'payload': 'audit_later'},
    ])))
    return out


# ---------- Walkthrough ----------

def _walkthrough_feature_card(predicate, user, mode='walkthrough'):
    """Build a deep_link_card for one feature."""
    from chat.wit_bot_copy import (
        WALKTHROUGH_MARK_DONE, WALKTHROUGH_RECHECK, WALKTHROUGH_SKIP,
        WALKTHROUGH_TAKE_ME_THERE,
    )

    text = f"**{predicate.display_name}**\n{predicate.description}"

    buttons = []
    if predicate.deep_link:
        buttons.append({
            'label': t(WALKTHROUGH_TAKE_ME_THERE, user),
            'navigate_to': predicate.deep_link,
        })

    if mode == 'walkthrough':
        buttons.append({
            'label': t(WALKTHROUGH_RECHECK, user),
            'payload': f'walkthrough_recheck:{predicate.feature_key}',
        })
        buttons.append({
            'label': t(WALKTHROUGH_MARK_DONE, user),
            'payload': f'walkthrough_done:{predicate.feature_key}',
        })
        buttons.append({
            'label': t(WALKTHROUGH_SKIP, user),
            'payload': f'walkthrough_skip:{predicate.feature_key}',
        })

    return (text, card_with_buttons(buttons))


def _enter_walkthrough(state, user):
    from chat.wit_bot_copy import AUDIT_NOTHING_MISSING, WALKTHROUGH_INTRO

    _, missing = _build_audit_report(user)
    if not missing:
        state_mod.set_intent(state, '', step=0)
        return [(t(AUDIT_NOTHING_MISSING, user), None)]

    state_mod.set_intent(state, 'walkthrough', step=0)
    state_mod.set_progress(state, user.current_ver, 'walkthrough', {
        'missing_keys': [p.feature_key for p in missing],
        'index': 0,
    })

    first = missing[0]
    return [
        (t(WALKTHROUGH_INTRO, user), None),
        _walkthrough_feature_card(first, user, mode='walkthrough'),
    ]


def walkthrough_handler(state, message, user):
    from chat.wit_bot_copy import (
        WALKTHROUGH_COMPLETE, WALKTHROUGH_RECHECK_FAIL, WALKTHROUGH_RECHECK_OK,
    )
    from chat.models import OnboardingEvent
    from chat.wit_bot_predicates import predicate_by_key

    payload = (message.bot_payload or {}).get('payload', '')
    prog = state_mod.progress_for(state, user.current_ver)
    walk = prog.get('walkthrough', {})
    missing_keys = walk.get('missing_keys', [])
    index = walk.get('index', 0)

    if not missing_keys:
        state_mod.set_intent(state, '', step=0)
        return [(t(WALKTHROUGH_COMPLETE, user), None)]

    advanced = False
    pre_messages = []  # things to post before the next feature card

    # Re-check: re-run the predicate. If True, advance silently. If False, stay
    # and tell the user we still don't see it.
    if payload.startswith('walkthrough_recheck:'):
        feature_key = payload.split(':', 1)[1]
        pred = predicate_by_key(feature_key)
        if pred and pred.is_engaged(user):
            pre_messages.append((t(WALKTHROUGH_RECHECK_OK, user), None))
            advanced = True
        else:
            return [(t(WALKTHROUGH_RECHECK_FAIL, user), None)]

    elif payload.startswith('walkthrough_done:'):
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

    if index >= len(missing_keys):
        state_mod.set_intent(state, '', step=0)
        return pre_messages + [(t(WALKTHROUGH_COMPLETE, user), None)]

    next_pred = predicate_by_key(missing_keys[index])
    if next_pred is None:
        index += 1
        state_mod.set_progress(state, user.current_ver, 'walkthrough', {'index': index})
        if index >= len(missing_keys):
            state_mod.set_intent(state, '', step=0)
            return pre_messages + [(t(WALKTHROUGH_COMPLETE, user), None)]
        next_pred = predicate_by_key(missing_keys[index])

    return pre_messages + [_walkthrough_feature_card(next_pred, user, mode='walkthrough')]


# ---------- Boss quiz (end-of-version final exam) ----------

def _build_final_quiz_options(version, user):
    """Build quiz options dynamically for the given user's language.
    Real-in-version → correct; real-only-in-other → distractor; absurd → fake.
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
        options.append({
            'value': f'absurd:{ab["value"]}',
            'label': t(ab['label'], user),
            'correct': False,
        })

    random.shuffle(options)
    return options


def _enter_final_quiz(state, user):
    from chat.wit_bot_copy import BOSS_QUIZ_INTRO

    options = _build_final_quiz_options(user.current_ver, user)

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

    return [(t(BOSS_QUIZ_INTRO, user), multi_select(intent='final_quiz', options=options))]


def final_quiz_handler(state, message, user):
    from chat.wit_bot_copy import (
        BOSS_QUIZ_FAIL_TEMPLATE, BOSS_QUIZ_MISSED, BOSS_QUIZ_PASS_TEMPLATE,
        BOSS_QUIZ_WRONG_ABSURD, BOSS_QUIZ_WRONG_DISTRACTOR,
    )

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
        return [(t(BOSS_QUIZ_PASS_TEMPLATE, user).format(score=int(score * 100)), None)]

    # Fail — reveal wrong + retry
    wrong_lines = []
    for o in saved_options:
        was_selected = o['value'] in selected
        if o['correct'] and not was_selected:
            wrong_lines.append('  ✗ ' + t(BOSS_QUIZ_MISSED, user).format(label=o['label']))
        elif not o['correct'] and was_selected:
            tmpl = (
                BOSS_QUIZ_WRONG_DISTRACTOR if o['value'].startswith('distractor:')
                else BOSS_QUIZ_WRONG_ABSURD
            )
            wrong_lines.append('  ✗ ' + t(tmpl, user).format(label=o['label']))

    lang = getattr(user, 'language', 'en') or 'en'
    fallback = '  (어쨌든 다시 제출해 봐)' if lang == 'ko' else '  (somehow none — tap Submit again)'
    reveal = t(BOSS_QUIZ_FAIL_TEMPLATE, user).format(
        score=int(score * 100),
        wrong_lines='\n'.join(wrong_lines) if wrong_lines else fallback,
    )

    state_mod.set_progress(state, user.current_ver, 'final_quiz', {
        'attempts_history': attempts_history,
    })

    return [(reveal, None), *_enter_final_quiz(state, user)]


# ---------- FAQ ----------

def _faq_menu(user):
    from chat.wit_bot_copy import FAQ_ENTRIES, FAQ_MENU_INTRO

    return [(
        t(FAQ_MENU_INTRO, user),
        card_with_buttons([
            {'label': t(e['question'], user), 'payload': f'faq:{e["key"]}'}
            for e in FAQ_ENTRIES
        ]),
    )]


def _faq_answer(faq_key, user):
    from chat.wit_bot_copy import FAQ_ENTRIES

    entry = next((e for e in FAQ_ENTRIES if e['key'] == faq_key), None)
    if entry is None:
        return _faq_menu(user)
    return [(t(entry['answer'], user), None)]


def _wit_reply(user):
    import random
    from chat.wit_bot_copy import WIT_REPLIES
    return [(t(random.choice(WIT_REPLIES), user), None)]


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
