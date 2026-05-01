"""Helpers for the wit_bot system user.

Phase 1: scripted onboarding chatbot that lives in a 1-on-1 ChatRoom with each
regular user, plus a "talk to a real person" escalation that promotes the room
in place to a 3-member group containing wit_admin.

Avatar source is the whoami logo at WhoamI-Today-frontend/public/whoami384.png;
ensure_wit_bot_user copies it into MEDIA_ROOT/profile_images/wit_bot.png on
first run.
"""
from __future__ import annotations

import logging
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files import File
from django.db import IntegrityError, transaction

from chat.models import ChatRoom
from chat.wit_admin import (
    ALL_OPERATOR_EMAILS,
    WIT_ADMIN_EMAIL,
    _ordered_pair,
    is_wit_admin,
)


logger = logging.getLogger(__name__)


WIT_BOT_USERNAME = 'wit_bot'
WIT_BOT_EMAIL = 'wit.bot@whoami.today'
WIT_BOT_DISPLAY_NAME = 'wit_bot'

# Bundled inside the backend repo so the avatar is available in any deployment
# without depending on the frontend repo being checked out next door.
WIT_BOT_AVATAR_SOURCE = Path(__file__).parent / 'assets' / 'wit_bot_avatar.png'


def _set_avatar_from_source(user):
    """Copy the bundled logo onto user.profile_image. Silent no-op on failure."""
    if user.profile_image:
        return
    if not WIT_BOT_AVATAR_SOURCE.is_file():
        logger.warning(
            'wit_bot avatar source missing at %s; skipping profile_image set.',
            WIT_BOT_AVATAR_SOURCE,
        )
        return
    try:
        with open(WIT_BOT_AVATAR_SOURCE, 'rb') as f:
            user.profile_image.save('wit_bot.png', File(f), save=True)
    except OSError as exc:
        logger.warning('wit_bot avatar copy failed: %s', exc)


def ensure_wit_bot_user():
    """Get-or-create the wit_bot user. Idempotent.

    Like ensure_wit_admin_user, this preserves manual auth state (password,
    is_active) on re-runs. The first call populates profile_image from the
    bundled logo asset.
    """
    User = get_user_model()

    user = User.all_objects.filter(username=WIT_BOT_USERNAME).first()
    if user is not None:
        if user.deleted:
            user.deleted = None
            user.save(update_fields=['deleted'])
        if user.email != WIT_BOT_EMAIL:
            user.email = WIT_BOT_EMAIL
            user.save(update_fields=['email'])
        _set_avatar_from_source(user)
        return user

    if User.all_objects.filter(email=WIT_BOT_EMAIL).exists():
        raise IntegrityError(
            f"Cannot create wit_bot: email {WIT_BOT_EMAIL} is already "
            f"registered to another user. Free the email first or change "
            f"WIT_BOT_EMAIL."
        )

    user = User.objects.create(
        username=WIT_BOT_USERNAME,
        email=WIT_BOT_EMAIL,
    )
    _set_avatar_from_source(user)
    return user


def is_wit_bot(user):
    return user is not None and user.username == WIT_BOT_USERNAME


@transaction.atomic
def ensure_wit_bot_room(user):
    """Create the standard 1-on-1 ChatRoom between `user` and wit_bot.

    Skips wit_bot itself, wit_admin, and the 3 operators — none of them need a
    bot conversation. Idempotent. The room is a plain 1-on-1 (no wit_admin
    proxy/blast flags) so the wit_admin fanout signal won't match it.
    """
    bot = ensure_wit_bot_user()

    if (
        user.id == bot.id
        or user.email == WIT_BOT_EMAIL
        or user.email == WIT_ADMIN_EMAIL
        or user.email in ALL_OPERATOR_EMAILS
    ):
        return None

    u1, u2 = _ordered_pair(user, bot)
    room, created = ChatRoom.objects.get_or_create(user1=u1, user2=u2)
    if created:
        from chat.wit_bot_engine import _post_welcome
        _post_welcome(room, bot, user)
    return room


@transaction.atomic
def escalate_to_human(user):
    """Promote the user's wit_bot 1-on-1 ChatRoom into a 3-member group.

    Adds wit_admin to the existing room's members M2M (preserves all message
    history, since we're not creating a new room). wit_admin gains read access
    to this room and only this room — Django's membership check at the
    consumer/view layer enforces the privacy invariant.
    """
    from chat.models import GroupReadCursor, Message
    from chat.wit_admin import ensure_wit_admin_user
    from notification.models import Notification, NotificationActor

    bot = ensure_wit_bot_user()
    admin = ensure_wit_admin_user()

    u1, u2 = _ordered_pair(user, bot)
    room = ChatRoom.objects.filter(user1=u1, user2=u2, is_group=False).first()
    if room is None:
        ensure_wit_bot_room(user)
        room = ChatRoom.objects.get(user1=u1, user2=u2, is_group=False)

    room.is_group = True
    room.name = f"Help: {user.username}"
    room.save(update_fields=['is_group', 'name'])
    room.members.set([user, bot, admin])

    latest = Message.objects.filter(chat_room=room).order_by('-created_at').first()
    for member in (user, bot, admin):
        GroupReadCursor.objects.update_or_create(
            user=member, chat_room=room,
            defaults={'last_read_message': latest},
        )

    # Reuse the existing system-event broadcast helper.
    from chat.views import _broadcast_system_message
    added_msg = Message.objects.create(
        chat_room=room, sender=bot, receiver=None,
        event_type='member_added',
    )
    added_msg.event_target_users.set([admin])
    _broadcast_system_message(room, added_msg)

    noti = Notification.objects.create(
        user=admin,
        origin=user,
        target=added_msg,
        message_ko=f"{user.username}님이 도움을 요청했어요",
        message_en=f"{user.username} asked for help",
        redirect_url=f"/chats/group/{room.id}",
    )
    NotificationActor.objects.create(user=user, notification=noti)

    return room
