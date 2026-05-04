"""Intent handlers for the wit_bot conversation engine.

Each handler signature: (state, incoming_message, user) -> list[(text, bot_payload)]
Handlers mutate state.current_intent / state.step / state.context as needed.
"""
from __future__ import annotations

from chat import wit_bot_state as state_mod


def idle_handler(state, message, user):
    """Default when no intent is active. Routes special payloads, else nudges."""
    payload = (message.bot_payload or {}).get('payload')

    if payload == 'start_onboarding':
        state_mod.set_intent(state, 'kickoff_welcome', step=0)
        return _kickoff_welcome_intro()

    if payload == 'resume_onboarding':
        # state.current_intent should already be set; re-render its prompt
        handler = HANDLERS.get(state.current_intent, idle_handler)
        return handler(state, message, user)

    # Unknown — short, on-voice nudge
    return [
        ("not sure what that was. try the welcome card up top, or type `wit?`.", None),
    ]


def _kickoff_welcome_intro():
    from chat.wit_bot_copy import WELCOME_INTRO
    from chat.wit_bot_payloads import card_with_buttons
    return [(WELCOME_INTRO, card_with_buttons([
        {'label': "let's go", 'payload': 'kickoff_welcome_continue'},
    ]))]


def kickoff_welcome_handler(state, message, user):
    """Stub — full implementation in Task 7."""
    return [("(kickoff_welcome stub — full impl in Task 7)", None)]


HANDLERS = {
    '': idle_handler,
    'kickoff_welcome': kickoff_welcome_handler,
}
