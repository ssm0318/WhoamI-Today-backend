from typing import Dict, Optional
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError

VIEW_AS_TIERS = ('public', 'friends', 'close_friends')


def parse_view_as(request) -> Optional[str]:
    """Parse the `view_as` query param.

    Returns None if missing. Raises ValidationError(400) if present but
    not one of VIEW_AS_TIERS.
    """
    raw = request.query_params.get('view_as') if hasattr(request, 'query_params') else request.GET.get('view_as')
    if raw is None or raw == '':
        return None
    if raw not in VIEW_AS_TIERS:
        raise ValidationError({'view_as': f"Must be one of {VIEW_AS_TIERS}."})
    return raw


# Map of profile field name → friends_only flag name.
# Public viewer has the field hidden when the flag is True.
PROFILE_FIELD_FLAGS: Dict[str, str] = {
    'bio': 'bio_friends_only',
    'pronouns': 'pronouns_friends_only',
}


def apply_profile_view_as(data: dict, owner, tier: Optional[str]) -> dict:
    """Mutate `data` in place to mask owner profile fields per the chosen tier.

    Called only when `tier` is set and the requester is the owner. For the
    binary `_friends_only` flags, masking applies only to the 'public' tier;
    'friends' and 'close_friends' see the same fields a real friend sees.
    """
    if tier != 'public':
        return data
    for field, flag in PROFILE_FIELD_FLAGS.items():
        if getattr(owner, flag, False) and field in data:
            data[field] = None
    return data


def parse_view_as_user(request) -> Optional[str]:
    """Parse the `view_as_user` query param.

    Returns the username string if present, None if missing or empty.
    Does NOT validate that the user exists — that's resolve_shadow_viewer's job.
    """
    raw = (
        request.query_params.get('view_as_user')
        if hasattr(request, 'query_params')
        else request.GET.get('view_as_user')
    )
    if raw is None or raw == '':
        return None
    return raw


def resolve_shadow_viewer(request, target_owner):
    """Resolve `?view_as_user=<username>` to a User instance for shadow-viewer mode.

    Returns the chosen User instance only when:
      - The query param is present
      - The requester is the target profile's owner (gate against abuse)
      - The chosen user exists
      - The chosen user is NOT the owner themselves (no-op, return None)

    Returns None in all other cases. Callers should fall back to `request.user`.
    """
    username = parse_view_as_user(request)
    if username is None:
        return None
    # Owner-only gate: only the owner of the target profile may use shadow viewer.
    if request.user != target_owner:
        return None
    User = get_user_model()
    try:
        candidate = User.objects.get(username=username)
    except User.DoesNotExist:
        return None
    # Picking yourself as shadow viewer is identity → return None to fall back.
    if candidate == target_owner:
        return None
    return candidate
