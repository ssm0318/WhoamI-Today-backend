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


# Map of profile field name → 4-way visibility enum field name.
PROFILE_FIELD_VISIBILITY: Dict[str, str] = {
    'name': 'name_visibility',
    'bio': 'bio_visibility',
    'pronouns': 'pronouns_visibility',
}


def _tier_allows(tier: str, visibility: str) -> bool:
    if visibility == 'public':
        return True
    if visibility == 'only_me':
        return False
    if visibility == 'friends':
        return tier in ('friends', 'close_friends')
    if visibility == 'close_friends':
        return tier == 'close_friends'
    return False


def tier_allows_post(tier: str, visibility_array) -> bool:
    """Check whether a view-as tier can see a post with the given visibility array."""
    return any(_tier_allows(tier, v) for v in visibility_array)


def apply_profile_view_as(data: dict, owner, tier: Optional[str]) -> dict:
    """Mutate `data` in place to mask owner profile fields per the chosen tier.

    A field is masked when its visibility setting is stricter than what the
    chosen view-as tier should see (e.g. tier='public' hides any field whose
    visibility is 'friends' / 'close_friends' / 'only_me').
    """
    if tier is None:
        return data
    for field, vis_field in PROFILE_FIELD_VISIBILITY.items():
        visibility = getattr(owner, vis_field, 'public')
        if not _tier_allows(tier, visibility) and field in data:
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


# Username of the user that stands in as the "public non-friend" viewer for
# View As preview (when ?view_as=public is sent). Configurable via
# settings.VIEW_AS_PUBLIC_PROXY_USERNAME if defined; otherwise defaults below.
DEFAULT_NON_FRIEND_PROXY_USERNAME = 'wit_bot'


def _get_proxy_username() -> str:
    from django.conf import settings
    return getattr(settings, 'VIEW_AS_PUBLIC_PROXY_USERNAME', DEFAULT_NON_FRIEND_PROXY_USERNAME)


def resolve_public_proxy_viewer(target_owner):
    """Resolve the configured non-friend proxy user for `?view_as=public`.

    Returns the proxy User instance only when:
      - The proxy user exists
      - The proxy user is NOT the owner themselves
      - The proxy user is NOT connected to the owner (must actually be a non-friend
        for the preview to be representative of the public non-friend view)

    Returns None if any of the above fails. Callers should fall back to the
    existing tier-mode masking (via apply_profile_view_as) when None is returned.
    """
    User = get_user_model()
    try:
        proxy = User.objects.get(username=_get_proxy_username())
    except User.DoesNotExist:
        return None
    if proxy == target_owner:
        return None
    if target_owner.is_connected(proxy):
        return None
    return proxy
