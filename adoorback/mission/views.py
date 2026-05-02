from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from mission.models import Mission
from mission.serializers import MissionSerializer


class DailyMissionList(generics.ListAPIView):
    serializer_class = MissionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return Mission.objects.daily_missions(self.request.user)
