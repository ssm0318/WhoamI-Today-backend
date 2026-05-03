"""Beta-loop engine for wit_bot conversations.

Behavior is deliberately tiny: every user input — free text or any non-admin
button tap — gets a randomized playful reply with the same 4-button card.
Tapping the "Call in the admin" button immediately escalates to wit_admin
(via the existing `escalate_to_human` flow) and posts an acknowledgement.

Welcome message is posted into the room when `ensure_wit_bot_room` first
creates it (see `_post_welcome`).
"""
from __future__ import annotations

import logging
import random

from django.db import transaction


logger = logging.getLogger(__name__)


# Pool of playful, deliberately-not-helpful replies. Every line is written so
# the user cannot mistake it for an error or NLU failure: random facts are
# tagged with 🎲 so the pattern is recognizable as "the bot is doing the
# random-fact thing", not "the bot didn't understand". The "by design" lines
# call out intent explicitly. Welcome message is NOT randomized — it stays as
# the canonical introduction in `_post_welcome`.
BETA_REPLIES = (
    # Playful giggles (3) — pure vibes, obviously not an answer.
    "hehe!",
    "tehe ✨",
    "🫧 bloop",
    # Random facts (8) — non-sequiturs, clearly tagged so the user reads them
    # as intentional silliness rather than failed comprehension.
    "🎲 random fact: a group of flamingos is called a flamboyance 🦩",
    "🎲 random fact: octopuses have three hearts and blue blood 🐙",
    "🎲 random fact: bananas are berries but strawberries aren't 🍌",
    "🎲 random fact: a day on Venus is longer than its year 🪐",
    "🎲 random fact: wombat poop is cube-shaped 🟫",
    "🎲 random fact: cows have best friends and get stressed when separated 🐄",
    "🎲 random fact: honey never spoils — archaeologists have eaten 3000-year-old honey 🍯",
    "🎲 random fact: there are more possible chess games than atoms in the universe ♟️",
    # Explicitly "by design" (3) — names the bot's unhelpfulness as intentional
    # so the user doesn't read it as broken.
    "not a bug — I'm just here to vibe 🎀",
    "I'm intentionally unhelpful for now — by design ✨",
    "pretend that was helpful 🎀",
)


def _beta_card():
    """The canonical 4-button card. Re-rendered after every non-admin reply."""
    return {
        "kind": "card",
        "buttons": [
            {"label": "Onboarding (coming soon)", "action": "reply", "payload": "onboarding"},
            {"label": "I'm confused", "action": "reply", "payload": "confused"},
            {"label": "tehehe", "action": "reply", "payload": "tehehe"},
            {"label": "Call in the admin", "action": "reply", "payload": "admin"},
        ],
    }


def _post_replies(room, bot, user, replies):
    """Persist each reply as a Message. The user's REST POST that triggered
    this engine run picks up newly-created messages from the same room and
    returns them inline (see MessageList.create), so we don't broadcast over
    WebSocket — that just races the inline response.

    Each item in `replies` is `(text, bot_payload | None)`.
    """
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

        # Free text OR any of the three joke buttons → loop with a random
        # playful reply + the same 4-button card.
        _post_replies(room, bot, user, [
            (random.choice(BETA_REPLIES), _beta_card()),
        ])
