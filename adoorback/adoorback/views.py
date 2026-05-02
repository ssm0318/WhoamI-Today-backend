from collections import OrderedDict

from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from adoorback.models import Mission
from adoorback.serializers import MissionSerializer
from adoorback.utils.mission_limits import MAX_MISSION_ATTEMPTS_PER_DAY
from adoorback.utils.mission_day import get_today_la_boundary
from note.models import Note, ShareType
from note.serializers import NoteSerializer


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


def _mission_note_filter(mission):
    note_field_names = {field.name for field in Note._meta.get_fields()}
    if 'mission_id' in note_field_names:
        return {'mission_id': mission}
    if 'mission' in note_field_names:
        return {'mission': mission}
    # Temporary compatibility until the mission FK change lands.
    return {'mission_prompt': mission.prompt}


class MissionAttempts(generics.ListAPIView):
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated]

    def get_mission(self):
        if not hasattr(self, '_mission'):
            self._mission = get_object_or_404(Mission, id=self.kwargs.get('mission_id'))
        return self._mission

    def get_queryset(self):
        mission = self.get_mission()
        notes = Note.objects.filter(
            share_type=ShareType.MISSION,
            **_mission_note_filter(mission),
        ).select_related('author').prefetch_related(
            'images',
            'videos',
            'readers',
        ).order_by('-created_at')

        visible_note_ids = [note.id for note in notes if note.is_audience(self.request.user)]
        return Note.objects.filter(id__in=visible_note_ids).order_by('-created_at')

    def list(self, request, *args, **kwargs):
        mission = self.get_mission()
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_response = self.get_paginated_response(serializer.data)
            paginated_response.data = OrderedDict([
                ('id', mission.id),
                ('prompt', mission.prompt),
                ('type', mission.type),
                *paginated_response.data.items(),
            ])
            return paginated_response

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'id': mission.id,
            'prompt': mission.prompt,
            'type': mission.type,
            'count': len(serializer.data),
            'next': None,
            'previous': None,
            'results': serializer.data,
        })
