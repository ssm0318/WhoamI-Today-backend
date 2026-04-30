"""Scripted decision-tree engine for wit_bot conversations.

Phase 1: keyword/regex matchers + handcrafted replies. Free-form input that
doesn't match any intent falls through to a canned "I'm a bot" prompt.

Phase 2 (deferred): LLM fallback at the unknown-intent branch.
"""
from __future__ import annotations

import logging
import re

from django.db import transaction


logger = logging.getLogger(__name__)


# State values stored on WitBotConversationState.current_intent.
INTENT_NONE = ''
INTENT_ONBOARDING_START = 'onboarding.start'
INTENT_AWAITING_ESCALATION = 'awaiting_escalation_confirm'


# Compiled matchers — case-insensitive, word-boundary-aware where it matters.
_TALK_TO_HUMAN_RE = re.compile(
    r'\b(real person|human|talk to (an? )?admin|wit_admin|operator|support)\b',
    re.IGNORECASE,
)
_AFFIRMATIVE_RE = re.compile(r'^\s*(yes|네|y|yeah|yep|sure|ok)\b', re.IGNORECASE)
_NEGATIVE_RE = re.compile(r'^\s*(no|n|nope|아니|cancel)\b', re.IGNORECASE)
_MISSION_RE = re.compile(r'\bmission\b', re.IGNORECASE)


def _get_or_create_state(user):
    from chat.models import WitBotConversationState
    state, _ = WitBotConversationState.objects.get_or_create(user=user)
    return state


def _post_replies(room, bot, user, replies):
    """Persist each reply as a Message and broadcast to both participants."""
    if not replies:
        return
    from chat.models import Message
    from chat.views import broadcast_message_for_room
    for text in replies:
        msg = Message.objects.create(
            chat_room=room,
            sender=bot,
            receiver=user,
            content=text,
        )
        broadcast_message_for_room(msg)


def _has_prior_user_messages(room, user):
    """True if the user has sent at least one prior message in this room."""
    from chat.models import Message
    return Message.objects.filter(chat_room=room, sender=user).count() > 1


def _handle_awaiting_escalation(state, user, message):
    """Inside the awaiting-confirmation branch — yes/no/other."""
    text = message.content or ''
    if _AFFIRMATIVE_RE.match(text):
        from chat.wit_bot import escalate_to_human
        # Clear state BEFORE escalation so the post_save signal triggered by
        # the system "member_added" message doesn't loop back through the
        # engine in some odd path.
        state.current_intent = INTENT_NONE
        state.step = 0
        state.context = {}
        state.save()
        escalate_to_human(user)
        return ["Bringing in a teammate now — wit_admin has been added to this chat."]
    if _NEGATIVE_RE.match(text):
        state.current_intent = INTENT_NONE
        state.step = 0
        state.context = {}
        state.save()
        return [
            "No problem — I'll stay here. Reply 'real person' anytime if you change your mind.",
        ]
    return [
        "Just to confirm — reply 'yes' to bring in a real person, or 'no' to keep chatting with me.",
    ]


def _handle_talk_to_human(state, user, message):
    state.current_intent = INTENT_AWAITING_ESCALATION
    state.step = 0
    state.context = {}
    state.save()
    return [
        "Want me to bring in a real person? Reply 'yes' to connect.",
    ]


def _handle_acceptmission(state, user, message):
    state.current_intent = INTENT_NONE
    state.step = 0
    state.context = {}
    state.save()
    return [
        "Tap the home tab and pick today's mission card to get started — "
        "the prompt will pre-fill in the note composer.",
    ]


def _handle_onboarding_start(state, user, message):
    state.current_intent = INTENT_ONBOARDING_START
    state.step = 1
    state.context = {}
    state.save()
    return [
        "Hi — I'm wit_bot 👋",
        "I can walk you through your first day on whoami today, "
        "or hand you off to a real person whenever you'd like. "
        "Type 'mission' to see today's prompt, or 'real person' to talk to the team.",
    ]


def _handle_unknown(state, user, message):
    # TODO(wit_bot Phase 2): plug in LLM fallback here for free-form replies.
    return [
        "I'm a bot — I didn't catch that. "
        "Reply 'real person' if you'd like me to connect you with the team.",
    ]


def handle_user_message(message):
    """Entry point — dispatch a freshly created user message to a wit_bot reply.

    Caller (the post_save signal) has already verified:
      - sender is the user, not wit_bot
      - chat_room is a wit_bot 1-on-1 (not group, not is_wit_admin_*)
      - message is not a system event

    All replies are persisted + broadcast inside this transaction.
    """
    from chat.wit_bot import ensure_wit_bot_user, is_wit_bot

    room = message.chat_room
    user = message.sender
    bot = ensure_wit_bot_user()

    # Belt-and-suspenders: never reply to ourselves.
    if is_wit_bot(user):
        return

    with transaction.atomic():
        state = _get_or_create_state(user)

        # awaiting_escalation_confirm short-circuits intent matching.
        if state.current_intent == INTENT_AWAITING_ESCALATION:
            replies = _handle_awaiting_escalation(state, user, message)
            _post_replies(room, bot, user, replies)
            return

        text = message.content or ''

        if _TALK_TO_HUMAN_RE.search(text):
            replies = _handle_talk_to_human(state, user, message)
        elif _MISSION_RE.search(text) and state.current_intent == INTENT_ONBOARDING_START:
            replies = _handle_acceptmission(state, user, message)
        elif state.current_intent == INTENT_NONE and not _has_prior_user_messages(room, user):
            replies = _handle_onboarding_start(state, user, message)
        else:
            replies = _handle_unknown(state, user, message)

        _post_replies(room, bot, user, replies)
