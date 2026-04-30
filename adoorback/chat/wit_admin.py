"""Helpers for the WIT Admin chat hotfix.

See docs/superpowers/specs/2026-04-25-wit-admin-chat-hotfix-design.md.
"""
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from chat.models import ChatRoom


WIT_ADMIN_USERNAME = 'wit_admin'
WIT_ADMIN_EMAIL = 'zeoni.res@gmail.com'
WIT_ADMIN_DISPLAY_NAME = 'WIT Admin'

OPERATOR_REPLIER_EMAIL = 'jaewonkim628@gmail.com'
OPERATOR_OBSERVER_EMAILS = ('koyrkr@gmail.com', 'njs03332@gmail.com')
ALL_OPERATOR_EMAILS = (OPERATOR_REPLIER_EMAIL,) + OPERATOR_OBSERVER_EMAILS


def ensure_wit_admin_user():
    """Get-or-create the WIT Admin user. Idempotent.

    WIT Admin is intentionally login-able — operators may sign in to it for
    direct UI access to the support inbox. The helper only ensures the row
    exists with the canonical username/email; it does NOT touch is_active or
    the password. Initial creation leaves the password unset (login impossible
    until an operator sets one via shell or admin), and any subsequent manual
    password / is_active changes are preserved across re-runs.

    Uses all_objects to also find soft-deleted users, and handles email
    collisions gracefully.
    """
    User = get_user_model()

    # Check all_objects (including soft-deleted) to avoid invisible-row conflicts.
    user = User.all_objects.filter(username=WIT_ADMIN_USERNAME).first()
    if user is not None:
        if user.deleted:
            user.deleted = None
            user.save(update_fields=['deleted'])
        if user.email != WIT_ADMIN_EMAIL:
            user.email = WIT_ADMIN_EMAIL
            user.save(update_fields=['email'])
        return user

    # Create new — but the target email might already belong to another user.
    if User.all_objects.filter(email=WIT_ADMIN_EMAIL).exists():
        raise IntegrityError(
            f"Cannot create wit_admin: email {WIT_ADMIN_EMAIL} is already "
            f"registered to another user. Free the email first or change "
            f"WIT_ADMIN_EMAIL."
        )

    user = User.objects.create(
        username=WIT_ADMIN_USERNAME,
        email=WIT_ADMIN_EMAIL,
    )
    return user


def resolve_operators():
    """Return [jaewon, koyrkr, njs] as User objects. Raise LookupError if any missing."""
    User = get_user_model()
    operators = []
    for email in ALL_OPERATOR_EMAILS:
        u = User.objects.filter(email=email).first()
        if u is None:
            raise LookupError(f"Operator user with email {email!r} not found")
        operators.append(u)
    return operators


def get_replier():
    """Return the jaewon operator user (the only one allowed to reply/blast)."""
    User = get_user_model()
    user = User.objects.filter(email=OPERATOR_REPLIER_EMAIL).first()
    if user is None:
        raise LookupError(f"Replier user {OPERATOR_REPLIER_EMAIL!r} not found")
    return user


def _ordered_pair(a, b):
    """Match ChatRoom.save() ordering convention (user1.id < user2.id)."""
    return (a, b) if a.id < b.id else (b, a)


@transaction.atomic
def provision_user_rooms(user):
    """Create the 1 WIT-Admin chat + 3 operator proxy rooms for `user`. Idempotent."""
    wit = ensure_wit_admin_user()
    operators = resolve_operators()

    # Skip if `user` is WIT Admin, an operator, or wit_bot. wit_bot is a peer
    # system user, not a customer of the WIT Admin support flow.
    if (
        user.id == wit.id
        or user.email == WIT_ADMIN_EMAIL
        or user.email in ALL_OPERATOR_EMAILS
        or user.username == SYSTEM_BOT_USERNAME
    ):
        return

    u1, u2 = _ordered_pair(user, wit)
    ChatRoom.objects.get_or_create(user1=u1, user2=u2)

    for op in operators:
        u1, u2 = _ordered_pair(user, op)
        room, created = ChatRoom.objects.get_or_create(
            user1=u1, user2=u2,
            defaults={'is_wit_admin_proxy': True},
        )
        if not created and not room.is_wit_admin_proxy:
            room.is_wit_admin_proxy = True
            room.save(update_fields=['is_wit_admin_proxy'])


@transaction.atomic
def ensure_blast_rooms():
    """Create the 3 operator-↔-WIT-Admin blast rooms. Idempotent."""
    wit = ensure_wit_admin_user()
    for op in resolve_operators():
        u1, u2 = _ordered_pair(wit, op)
        room, created = ChatRoom.objects.get_or_create(
            user1=u1, user2=u2,
            defaults={'is_wit_admin_blast_room': True},
        )
        if not created and not room.is_wit_admin_blast_room:
            room.is_wit_admin_blast_room = True
            room.save(update_fields=['is_wit_admin_blast_room'])


SYSTEM_BOT_USERNAME = 'wit_bot'


@transaction.atomic
def ensure_system_connections():
    """Connect all 5 system accounts (wit_admin, wit_bot, jaewon, koyrkr, njs)
    as friends with each other.

    Without these connections the chat-request UI fires when one signs in and
    opens a chat with another. Idempotent — `get_or_create` skips existing
    pairs.

    `wit_bot` is treated as optional: if it doesn't exist yet the helper
    connects the other 4 only.
    """
    from account.models import Connection

    User = get_user_model()
    wit = ensure_wit_admin_user()
    operators = resolve_operators()
    system_users = [wit, *operators]

    bot = User.objects.filter(username=SYSTEM_BOT_USERNAME).first()
    if bot is not None:
        system_users.append(bot)

    # Pairwise — every unordered pair gets a Connection if missing.
    for i, a in enumerate(system_users):
        for b in system_users[i + 1:]:
            u1, u2 = _ordered_pair(a, b)
            Connection.objects.get_or_create(
                user1=u1, user2=u2,
                defaults={'user1_choice': 'friend', 'user2_choice': 'friend'},
            )


def regular_recipients():
    """Active, non-deleted users excluding WIT Admin, the 3 operators, and wit_bot."""
    User = get_user_model()
    excluded_emails = list(ALL_OPERATOR_EMAILS) + [WIT_ADMIN_EMAIL]
    excluded_usernames = [SYSTEM_BOT_USERNAME]
    return (
        User.objects.filter(is_active=True)
        .exclude(email__in=excluded_emails)
        .exclude(username__in=excluded_usernames)
    )


def is_wit_admin(user):
    return user is not None and user.username == WIT_ADMIN_USERNAME


def is_replier(user):
    return user is not None and user.email == OPERATOR_REPLIER_EMAIL


def _copy_message_fields(source):
    """Return kwargs for Message.objects.create() that mirror `source`'s payload."""
    return {
        'content': source.content,
        'emoji': source.emoji,
        'image': source.image,
        'shared_content_type': source.shared_content_type,
        'shared_object_id': source.shared_object_id,
        'is_wit_admin_mirror': True,
    }
