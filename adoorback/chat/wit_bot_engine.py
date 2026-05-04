"""Intent state-machine engine for wit_bot.

Replaces the old beta-loop implementation. Dispatch flow:
1. read WitBotConversationState for the sender
2. look up the intent handler matching state.current_intent
3. handler returns a list of (text, bot_payload) tuples to post
4. handler mutates state (intent / step / context) before returning
"""
from __future__ import annotations

import logging

from django.db import transaction


logger = logging.getLogger(__name__)

WELCOME_EVENT_TYPE = 'wit_welcome_card'


def _post_replies(room, bot, user, replies):
    """Persist each reply as a Message. Each item: (text, bot_payload | None)."""
    if not replies:
        return
    from chat.models import Message
    for text, bot_payload in replies:
        Message.objects.create(
            chat_room=room,
            sender=bot,
            receiver=user,
            content=text,
            bot_payload=bot_payload,
        )


def _post_welcome(room, bot, user):
    """Post the state-aware welcome card with event_type so refresh can replace it.
    Called from `ensure_wit_bot_room`."""
    from chat.models import Message as MessageModel
    from chat.wit_bot_welcome_card import build_welcome_card
    card = build_welcome_card(user)
    MessageModel.objects.create(
        chat_room=room, sender=bot, receiver=user,
        content=card.get('intro', ''),
        bot_payload=card,
        event_type=WELCOME_EVENT_TYPE,
    )


def _refresh_welcome_card(room, bot, user):
    """Delete any existing wit_welcome_card message and post a fresh one
    reflecting current state."""
    from chat.models import Message as MessageModel
    from chat.wit_bot_welcome_card import build_welcome_card
    MessageModel.objects.filter(
        chat_room=room, event_type=WELCOME_EVENT_TYPE,
    ).delete()
    card = build_welcome_card(user)
    MessageModel.objects.create(
        chat_room=room, sender=bot, receiver=user,
        content=card.get('intro', ''),
        bot_payload=card,
        event_type=WELCOME_EVENT_TYPE,
    )


def handle_user_message(message):
    """Entry point — dispatch a freshly created user message to a wit_bot reply.

    Caller (the `dispatch_wit_bot_engine` post_save signal) has already verified:
      - sender is not the bot
      - chat_room is a wit_bot 1-on-1
      - message is not a system event
    """
    from chat.wit_bot import ensure_wit_bot_user, escalate_to_human, is_wit_bot
    from chat import wit_bot_state as state_mod
    from chat import wit_bot_intents as intents

    bot = ensure_wit_bot_user()
    user = message.sender
    room = message.chat_room

    if is_wit_bot(user):
        return

    payload = message.bot_payload or {}
    is_admin_choice = (
        payload.get('kind') == 'choice' and payload.get('payload') == 'admin'
    )

    state = state_mod.get_or_create_state(user)

    with transaction.atomic():
        # Safety hatch — admin escalation always wins, regardless of intent.
        if is_admin_choice:
            escalate_to_human(user)
            _post_replies(room, bot, user, [
                ("Admin has been called in 👀", None),
            ])
            return

        # Dispatch on current intent
        handler = intents.HANDLERS.get(state.current_intent, intents.idle_handler)
        replies = handler(state, message, user)
        _post_replies(room, bot, user, replies)

        # Refresh welcome card so its CTA reflects new state
        _refresh_welcome_card(room, bot, user)
