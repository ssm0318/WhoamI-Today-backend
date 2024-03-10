from rest_framework import generics, exceptions
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from chat.models import Message, ChatRoom
from collections import OrderedDict
from account.models import User

import chat.serializers as cs

class ChatRoomList(generics.ListAPIView):
    """
    Get all chat rooms of request user.
    """
    serializer_class = cs.ChatRoomSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        current_user = self.request.user
        current_user.chat_rooms.all()
        return current_user.chat_rooms.filter(messages__isnull=False).distinct()


class ReversePagination(PageNumberPagination):
    page_size = 30

    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', list(reversed(data)))
        ]))


class ChatRoomFriendList(generics.ListAPIView):
    """
    Get chat rooms with a friend.
    """
    serializer_class = cs.ChatRoomSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        current_user = self.request.user
        friend_id = self.kwargs.get('pk')
        friend = User.objects.get(id=friend_id)

        if (friend not in current_user.friends.all()):
            raise exceptions.PermissionDenied("You are not friend with this user")

        if (friend == current_user):
            raise exceptions.PermissionDenied("You cannot chat with yourself")

        chat_rooms = ChatRoom.objects.filter(users=current_user).filter(users=friend) \
            .filter(messages__isnull=False).distinct()

        return chat_rooms


class ChatMessagesListView(generics.ListAPIView):
    serializer_class = cs.MessageSerializer
    pagination_class = ReversePagination

    def get_queryset(self):
        try:
            chat_room = ChatRoom.objects.get(id=self.kwargs.get('pk'))
            if self.request.user not in chat_room.users.all():
                raise exceptions.PermissionDenied("You are not in this chat room")
        except ChatRoom.DoesNotExist:
            raise exceptions.NotFound("Chat room not found")

        chat_messages = Message.objects.filter(chat_room__id=self.kwargs.get('pk')).order_by('-id')
        return chat_messages
