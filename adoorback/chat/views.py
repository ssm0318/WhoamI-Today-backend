from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from chat.models import Message
from collections import OrderedDict

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


class ReversePagination(PageNumberPagination):
    # TODO - adjust page size
    page_size = 30

    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', list(reversed(data)))
        ]))

class ChatMessagesListView(generics.ListAPIView):
    serializer_class = cs.MessageSerializer
    pagination_class = ReversePagination

    def get_queryset(self):
        chat_messages = Message.objects.filter(chat_room__id=self.kwargs.get('pk')).order_by('-id')
        return chat_messages
