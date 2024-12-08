from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import generics, exceptions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Ping, get_or_create_ping_room
from .serializers import PingSerializer

User = get_user_model()


class PingList(generics.ListCreateAPIView):
    serializer_class = PingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        try:
            connected_user = User.objects.get(id=self.kwargs.get('pk'))
            if not user.is_connected(connected_user):
                raise exceptions.PermissionDenied("You are not connected to this user")
        except User.DoesNotExist:
            raise exceptions.NotFound("Connected user not found")

        ping_room = get_or_create_ping_room(connected_user, user)

        pings = Ping.objects.filter(ping_room=ping_room)
        return pings

    def perform_create(self, serializer):
        user = self.request.user
        try:
            connected_user = User.objects.get(id=self.kwargs.get('pk'))

            if not user.is_connected(connected_user):
                raise exceptions.PermissionDenied("You are not connected to this user")
        except User.DoesNotExist:
            raise exceptions.NotFound("Connected user not found")

        ping_room = get_or_create_ping_room(user, connected_user)

        serializer.save(sender=user, receiver=connected_user, ping_room=ping_room)


class MarkPingAsRead(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        ping = get_object_or_404(Ping, id=pk, receiver=user)

        if ping.is_read:
            return Response({"detail": "Ping is already marked as read."}, status=status.HTTP_400_BAD_REQUEST)
        
        ping.is_read = True
        ping.save()
        return Response({"detail": "Ping marked as read."}, status=status.HTTP_200_OK)
