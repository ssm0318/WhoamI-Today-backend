from django.db import transaction
from django.http import JsonResponse
from django.utils import translation
from django.utils import timezone
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from notification.models import Notification
from notification.serializers import NotificationSerializer

from adoorback.utils.permissions import IsOwnerOrReadOnly
from adoorback.utils.validators import adoor_exception_handler
from adoorback.utils.content_types import get_friend_request_type, get_response_request_type


class NotificationList(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)

        user = self.request.user
        notifications = Notification.objects.visible_only().filter(user=user)

        if user.ver_changed_at:
            notifications = notifications.filter(created_at__gte=user.ver_changed_at)

        return notifications


class FriendRequestNotiList(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def get_queryset(self):
        if 'HTTP_ACCEPT_LANGUAGE' in self.request.META:
            lang = self.request.META['HTTP_ACCEPT_LANGUAGE']
            translation.activate(lang)
        current_user = self.request.user
        queryset = Notification.objects.visible_only().filter(target_type=get_response_request_type(), user=current_user)

        grouped_notifications = []
        
        for noti in queryset:
            if not noti.origin or not hasattr(noti.origin, 'id'):
                continue
                
            question_id = noti.origin.id
            if not any(n.origin.id == question_id for n in grouped_notifications):
                response = noti.target.question.response_set.filter(
                    author=current_user
                ).filter(created_at__gt=noti.notification_updated_at)
                
                if not response.exists():
                    grouped_notifications.append(noti)
        
        return grouped_notifications


class NotificationDetail(generics.UpdateAPIView):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]

    def get_exception_handler(self):
        return adoor_exception_handler

    def patch(self, request, *args, **kwargs):
        ids = request.data.get('ids', [])
        queryset = Notification.objects.filter(id__in=ids)
        queryset.update(is_read=True)
        serializer = self.get_serializer(queryset, many=True)

        return Response(serializer.data)


class MarkAllNotificationsRead(generics.GenericAPIView):
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def patch(self, request, *args, **kwargs):
        user = request.user
        notifications = Notification.objects.unread_only(user=user)
        notifications.update(is_read=True)
        
        return Response(status=200)
