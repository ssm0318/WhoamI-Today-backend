from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from adoorback.models import Mission
from adoorback.serializers import MissionSerializer
from adoorback.utils.mission_day import get_today_la_boundary
from note.models import Note, ShareType


MAX_MISSION_ATTEMPTS_PER_DAY = 5


def count_mission_attempts_today(user, now=None):
    """Count the user's mission Notes since the most recent 7AM LA boundary."""
    boundary = get_today_la_boundary(now=now)
    return Note.objects.filter(
        author=user,
        share_type=ShareType.MISSION,
        created_at__gte=boundary,
    ).count()


class MissionList(generics.ListAPIView):
    queryset = Mission.objects.all()
    serializer_class = MissionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class MissionToday(APIView):
    """Today's mission + the request user's attempt usage.

    Source of truth for the mission attempt counter — replaces the old
    localStorage tracker on the frontend.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        missions = list(Mission.objects.all().order_by('id'))
        if not missions:
            return Response({'detail': 'No missions configured.'}, status=503)

        boundary = get_today_la_boundary()
        # Day-of-year of the boundary in its tz-aware form. matches frontend
        # getDayOfYear() math (which shifts LA time back 7h and reads day-of-year).
        day_of_year = boundary.timetuple().tm_yday
        mission = missions[day_of_year % len(missions)]

        attempts_used = count_mission_attempts_today(request.user)
        attempts_remaining = max(0, MAX_MISSION_ATTEMPTS_PER_DAY - attempts_used)

        return Response({
            'id': mission.id,
            'prompt': mission.prompt,
            'type': mission.type,
            'attempts_used': attempts_used,
            'attempts_remaining': attempts_remaining,
            'max_attempts': MAX_MISSION_ATTEMPTS_PER_DAY,
        })
