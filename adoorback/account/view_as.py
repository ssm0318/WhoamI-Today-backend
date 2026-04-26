from typing import Optional
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
