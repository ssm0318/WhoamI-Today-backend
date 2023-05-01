from django.db import transaction
from django.http import JsonResponse
from django.utils import translation
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from notification.models import Notification
from notification.serializers import NotificationSerializer

from adoorback.utils.permissions import IsOwnerOrReadOnly
from adoorback.utils.validators import adoor_exception_handler
from adoorback.utils.content_types import get_friend_request_type, get_response_request_type


class NotificationList(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        return Notification.objects.visible_only().filter(user=self.request.user)


class FriendRequestNotiList(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        return Notification.objects.visible_only().filter(target_type=get_friend_request_type(), user=self.request.user)


class ResponseRequestNotiList(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        return Notification.objects.visible_only().filter(target_type=get_response_request_type(), user=self.request.user)


def notification_id(request):
    notifications = Notification.objects.unread_only().filter(user__username=request.GET.get('username'))
    if notifications.count() == 0:
        return JsonResponse({"id": 0, "num_unread": 0})
    return JsonResponse({"id": notifications.first().id,
                         "num_unread": notifications.count()})


class NotificationDetail(generics.UpdateAPIView):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]

    def get_exception_handler(self):
        return adoor_exception_handler

    def patch(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        ids = request.data.get('ids', [])
        queryset = Notification.objects.filter(id__in=ids)
        queryset.update(is_read=True)
        serializer = self.get_serializer(queryset, many=True)

        return Response(serializer.data)
