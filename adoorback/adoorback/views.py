from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from adoorback.models import Mission
from adoorback.serializers import MissionSerializer


class MissionList(generics.ListAPIView):
    queryset = Mission.objects.all()
    serializer_class = MissionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
