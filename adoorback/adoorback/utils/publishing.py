from rest_framework.exceptions import PermissionDenied


def can_publish(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    inviter = getattr(user, 'invited_from', None)
    if inviter is None:
        return True

    return user.is_connected(inviter)


def invite_status(user):
    if not user or not user.is_authenticated:
        return 'none'
    if user.is_superuser:
        return 'none'

    inviter = getattr(user, 'invited_from', None)
    if inviter is None:
        return 'none'
    if user.is_connected(inviter):
        return 'accepted'
    return 'pending'


def ensure_can_publish(user):
    if not can_publish(user):
        raise PermissionDenied(
            "You need to be accepted as a friend by the user who invited you before posting."
        )
