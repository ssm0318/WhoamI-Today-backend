from django.shortcuts import render
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

import chat.serializers as cs

class ChatRoomList(generics.ListAPIView):
    """
    Get all chat rooms of request user.
    """
    serializer_class = cs.ChatRoomSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        current_user = self.request.user
        return current_user.chat_rooms.all()
