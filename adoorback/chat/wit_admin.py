"""Helpers for the WIT Admin chat hotfix.

See docs/superpowers/specs/2026-04-25-wit-admin-chat-hotfix-design.md.
"""
from django.contrib.auth import get_user_model
from django.db import transaction

from chat.models import ChatRoom


WIT_ADMIN_USERNAME = 'wit_admin'
WIT_ADMIN_EMAIL = 'zeoni.res@gmail.com'
WIT_ADMIN_DISPLAY_NAME = 'WIT Admin'

OPERATOR_REPLIER_EMAIL = 'jaewonkim628@gmail.com'
OPERATOR_OBSERVER_EMAILS = ('koyrkr@gmail.com', 'njs03332@gmail.com')
ALL_OPERATOR_EMAILS = (OPERATOR_REPLIER_EMAIL,) + OPERATOR_OBSERVER_EMAILS


def ensure_wit_admin_user():
    """Get-or-create the WIT Admin user. Idempotent.

    Re-asserts critical attributes (email, is_active) on pre-existing rows
    to recover from manual edits or stale data.
    """
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=WIT_ADMIN_USERNAME,
        defaults={
            'email': WIT_ADMIN_EMAIL,
            'is_active': False,
        },
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=['password'])
        return user

    # Reassert critical attributes if the row pre-existed with drift
    changed = False
    if user.email != WIT_ADMIN_EMAIL:
        user.email = WIT_ADMIN_EMAIL
        changed = True
    if user.is_active:
        user.is_active = False
        changed = True
    if changed:
        user.save(update_fields=['email', 'is_active'])
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

    # Skip if `user` is WIT Admin or an operator
    if (
        user.id == wit.id
        or user.email == WIT_ADMIN_EMAIL
        or user.email in ALL_OPERATOR_EMAILS
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


def regular_recipients():
    """Active, non-deleted users excluding WIT Admin and the 3 operators."""
    User = get_user_model()
    excluded = list(ALL_OPERATOR_EMAILS) + [WIT_ADMIN_EMAIL]
    return User.objects.filter(is_active=True).exclude(email__in=excluded)


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
