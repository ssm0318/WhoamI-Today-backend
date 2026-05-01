"""Beta-loop engine for wit_bot conversations.

Behavior is deliberately tiny: every user input — free text or any non-admin
button tap — gets a "hehe!" reply with the same 4-button card. Tapping the
"Call in the admin" button immediately escalates to wit_admin (via the
existing `escalate_to_human` flow) and posts an acknowledgement.

Welcome message is posted into the room when `ensure_wit_bot_room` first
creates it (see `_post_welcome`).
"""
from __future__ import annotations

import logging

from django.db import transaction


logger = logging.getLogger(__name__)


def _beta_card():
    """The canonical 4-button card. Re-rendered after every non-admin reply."""
    return {
        "kind": "card",
        "buttons": [
            {"label": "Get started with onboarding", "action": "reply", "payload": "onboarding"},
            {"label": "I'm confused", "action": "reply", "payload": "confused"},
            {"label": "tehehe", "action": "reply", "payload": "tehehe"},
            {"label": "Call in the admin", "action": "reply", "payload": "admin"},
        ],
    }


def _post_replies(room, bot, user, replies):
    """Persist each reply as a Message and broadcast to both participants.

    Each item in `replies` is `(text, bot_payload | None)`.
    """
    if not replies:
        return
    from chat.models import Message
    from chat.views import broadcast_message_for_room
    for text, bot_payload in replies:
        msg = Message.objects.create(
            chat_room=room,
            sender=bot,
            receiver=user,
            content=text,
            bot_payload=bot_payload,
        )
        broadcast_message_for_room(msg)


def _post_welcome(room, bot, user):
    """Post the proactive welcome card. Called from `ensure_wit_bot_room` on
    first room creation."""
    welcome_text = (
        "Hi! I'm your onboarding assistant 👋\n"
        "I'm still in beta, which means I might giggle instead of help.\n"
        "What would you like to do?"
    )
    _post_replies(room, bot, user, [(welcome_text, _beta_card())])


def handle_user_message(message):
    """Entry point — dispatch a freshly created user message to a wit_bot reply.

    Caller (the `dispatch_wit_bot_engine` post_save signal) has already verified:
      - sender is not the bot
      - chat_room is a wit_bot 1-on-1 (not a group, not wit_admin-flagged)
      - message is not a system event
    """
    from chat.wit_bot import ensure_wit_bot_user, escalate_to_human, is_wit_bot

    bot = ensure_wit_bot_user()
    user = message.sender
    room = message.chat_room

    # Belt-and-suspenders.
    if is_wit_bot(user):
        return

    payload = message.bot_payload or {}
    is_admin_choice = (
        payload.get('kind') == 'choice' and payload.get('payload') == 'admin'
    )

    with transaction.atomic():
        if is_admin_choice:
            escalate_to_human(user)
            _post_replies(room, bot, user, [
                ("Admin has been called in 👀", None),
            ])
            return

        # Free text OR any of the three joke buttons → loop.
        _post_replies(room, bot, user, [
            ("hehe!", _beta_card()),
        ])
