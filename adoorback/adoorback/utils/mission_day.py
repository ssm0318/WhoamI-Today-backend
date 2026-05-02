"""Helpers for the mission day boundary.

A mission "day" runs from 7:00 AM America/Los_Angeles to 6:59:59 AM the next day,
matching the frontend `getDayOfYear` math in
`WhoamI-Today-frontend/src/components/share/MissionOfTheDay.tsx`. Every helper
that counts today's mission attempts must use the same boundary or the cap
will desync with the UI.
"""

from datetime import timedelta
import zoneinfo

from django.utils import timezone


LA_TZ = zoneinfo.ZoneInfo('America/Los_Angeles')
DAY_BOUNDARY_HOUR_LA = 7


def get_today_la_boundary(now=None):
    """Return the most recent 7:00 AM America/Los_Angeles boundary as an aware datetime.

    If `now` is before today's 7AM LA, the boundary is yesterday's 7AM LA.
    """
    if now is None:
        now = timezone.now()
    la_now = now.astimezone(LA_TZ)
    today_boundary_la = la_now.replace(
        hour=DAY_BOUNDARY_HOUR_LA, minute=0, second=0, microsecond=0
    )
    if la_now < today_boundary_la:
        today_boundary_la = today_boundary_la - timedelta(days=1)
    return today_boundary_la
