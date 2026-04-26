from typing import Dict, Optional
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
