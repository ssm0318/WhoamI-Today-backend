from django.db import transaction
from django.utils import translation
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from note.models import Note
from notification.models import Notification
from notification.serializers import NotificationSerializer
from qna.models import Response as QnaResponse

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
        user = self.request.user
        notifications = Notification.objects.visible_only().filter(user=user)

        if user.ver_changed_at:
            notifications = notifications.filter(created_at__gte=user.ver_changed_at)

        notifications = list(notifications)

        # Collect referenced post IDs from redirect_urls
        note_ids = set()
        response_ids = set()
        for noti in notifications:
            try:
                parts = noti.redirect_url.strip('/').split('/')
                if parts[0] == 'notes':
                    note_ids.add(int(parts[1]))
                elif parts[0] == 'responses':
                    response_ids.add(int(parts[1]))
            except (ValueError, IndexError):
                pass

        # Batch-fetch referenced posts (SafeDeleteManager excludes soft-deleted)
        notes_map = {n.id: n for n in Note.objects.filter(id__in=note_ids)} if note_ids else {}
        responses_map = {r.id: r for r in QnaResponse.objects.filter(id__in=response_ids)} if response_ids else {}

        # Filter out notifications whose target post is deleted or user is no longer in audience
        audience_cache = {}
        result = []
        for noti in notifications:
            try:
                parts = noti.redirect_url.strip('/').split('/')
                if parts[0] == 'notes':
                    note_id = int(parts[1])
                    key = ('note', note_id)
                    if key not in audience_cache:
                        note = notes_map.get(note_id)
                        audience_cache[key] = note.is_audience(user) if note else False
                    if audience_cache[key]:
                        result.append(noti)
                    continue
                elif parts[0] == 'responses':
                    response_id = int(parts[1])
                    key = ('response', response_id)
                    if key not in audience_cache:
                        resp = responses_map.get(response_id)
                        audience_cache[key] = resp.is_audience(user) if resp else False
                    if audience_cache[key]:
                        result.append(noti)
                    continue
            except (ValueError, IndexError):
                pass
            result.append(noti)

        return result


class FriendRequestNotiList(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def get_queryset(self):
        return Notification.objects.visible_only().filter(target_type=get_friend_request_type(), user=self.request.user)


class ResponseRequestNotiList(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def get_queryset(self):
        current_user = self.request.user
        queryset = Notification.objects.visible_only().filter(target_type=get_response_request_type(), user=current_user)

        # filter out answered response-requests
        filtered_queryset = []
        for noti in queryset:
            response = noti.target.question.response_set.filter(author=current_user).filter(created_at__gt=noti.notification_updated_at)
            if not response.exists():
                filtered_queryset.append(noti)
        return filtered_queryset


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
