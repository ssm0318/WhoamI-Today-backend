from django.contrib.auth import get_user_model
from django.shortcuts import render
from rest_framework import generics, exceptions
from rest_framework.permissions import IsAuthenticated

from .models import Ping, get_or_create_ping_room, mark_pings_as_read
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
                print('??')
                raise exceptions.PermissionDenied("You are not connected to this user")
        except User.DoesNotExist:
            raise exceptions.NotFound("Connected user not found")

        ping_room = get_or_create_ping_room(connected_user, user)

        # mark pings in ping_room as read
        mark_pings_as_read(user, ping_room)

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

