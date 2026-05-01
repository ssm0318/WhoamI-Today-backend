from itertools import chain
from operator import attrgetter

from django.contrib.contenttypes.models import ContentType
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response as DRFResponse

from account.serializers_q import QCurrentUserSerializer, QUserProfileSerializer
from account.views import (
    CurrentUserDetail, UserProfile, CurrentUserNoteList, UserNoteList,
    CurrentUserAllPostList, UserAllPostList, FriendFeed,
)
from adoorback.utils.validators import adoor_exception_handler
from note.models import Note
from note.serializers_q import QNoteSerializer
from qna.models import Response as _Response
from qna.serializers_q import QResponseSerializer


class QCurrentUserDetail(CurrentUserDetail):
    """Current user detail for Version Q (no chip categories/custom chips)."""
    serializer_class = QCurrentUserSerializer


class QUserProfile(UserProfile):
    """User profile for Version Q (no chip-related fields)."""
    serializer_class = QUserProfileSerializer


class QCurrentUserNoteList(CurrentUserNoteList):
    """Current user note list for Version Q (likes only, no share_type)."""
    serializer_class = QNoteSerializer


class QUserNoteList(UserNoteList):
    """User note list for Version Q (likes only, no share_type)."""
    serializer_class = QNoteSerializer


class QFriendFeed(FriendFeed):
    """Friend feed for Version Q (notes only, Q serializer)."""

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        note_ids = queryset.values_list("id", flat=True)
        notes_before_update = list(Note.objects.filter(id__in=note_ids).order_by('-created_at'))

        page = self.paginate_queryset(notes_before_update)
        if page is not None:
            serialized_data = QNoteSerializer(page, many=True, context=self.get_serializer_context()).data
        else:
            serialized_data = QNoteSerializer(notes_before_update, many=True, context=self.get_serializer_context()).data

        unread_note_ids = queryset.exclude(readers=request.user).values_list("id", flat=True)
        if unread_note_ids:
            request.user.read_notes.add(*unread_note_ids)

        if page is not None:
            return self.get_paginated_response(serialized_data)
        return DRFResponse(serialized_data)


class QCurrentUserAllPostList(CurrentUserAllPostList):
    """Current user all posts for Version Q."""

    def list(self, request, *args, **kwargs):
        combined_items = self.get_combined_items()

        page = self.paginate_queryset(combined_items)
        objects_to_serialize = page if page is not None else combined_items

        serialized_data = []
        for obj in objects_to_serialize:
            if isinstance(obj, Note):
                serialized = QNoteSerializer(obj, context=self.get_serializer_context()).data
                serialized['type'] = 'Note'
            elif isinstance(obj, _Response):
                serialized = QResponseSerializer(obj, context=self.get_serializer_context()).data
                serialized['type'] = 'Response'
            serialized_data.append(serialized)

        return self.get_paginated_response(serialized_data) if page is not None else DRFResponse(serialized_data)


class QUserAllPostList(UserAllPostList):
    """User all posts for Version Q."""

    def list(self, request, *args, **kwargs):
        combined_items = self.get_combined_items()

        page = self.paginate_queryset(combined_items)
        objects_to_serialize = page if page is not None else combined_items

        user = request.user
        serialized_data = []
        for obj in objects_to_serialize:
            if isinstance(obj, Note):
                serialized = QNoteSerializer(obj, context=self.get_serializer_context()).data
                serialized['type'] = 'Note'
            elif isinstance(obj, _Response):
                serialized = QResponseSerializer(obj, context=self.get_serializer_context()).data
                serialized['type'] = 'Response'
            serialized_data.append(serialized)

        for obj in objects_to_serialize:
            obj.readers.add(user)

        return self.get_paginated_response(serialized_data) if page is not None else DRFResponse(serialized_data)


class QDiscoverFeed(generics.ListAPIView):
    """Discover feed for Version Q: public posts from non-friends, reverse chronological."""
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_combined_feed_items(self):
        user = self.request.user

        exclude_ids = set(user.connected_user_ids + user.user_report_blocked_ids + [user.id])

        # Exclude content-reported posts at queryset level
        from content_report.models import ContentReport
        note_ct = ContentType.objects.get_for_model(Note)
        response_ct = ContentType.objects.get_for_model(_Response)
        reported_note_ids = set(ContentReport.objects.filter(
            user=user, content_type=note_ct
        ).values_list('object_id', flat=True))
        reported_response_ids = set(ContentReport.objects.filter(
            user=user, content_type=response_ct
        ).values_list('object_id', flat=True))

        notes = list(Note.objects.filter(
            visibility__contains=['public'],
            author__current_ver=user.current_ver,
        ).exclude(
            author_id__in=exclude_ids,
        ).exclude(
            author__is_superuser=True,
        ).exclude(
            id__in=reported_note_ids,
        ).select_related('author').order_by('-created_at'))

        responses = list(_Response.objects.filter(
            visibility__contains=['public'],
            author__current_ver=user.current_ver,
        ).exclude(
            author_id__in=exclude_ids,
        ).exclude(
            author__is_superuser=True,
        ).exclude(
            id__in=reported_response_ids,
        ).select_related('author', 'question').order_by('-created_at'))

        combined = sorted(chain(notes, responses), key=attrgetter('created_at'), reverse=True)
        return notes, responses, combined

    def list(self, request, *args, **kwargs):
        user = request.user
        notes, responses, combined = self.get_combined_feed_items()

        page = self.paginate_queryset(combined)
        objects_to_serialize = page if page is not None else combined

        # Re-validate access: filter out items no longer accessible
        # (visibility changed, author blocked, or content reported since query)
        objects_to_serialize = [obj for obj in objects_to_serialize if obj.is_audience(request.user)]

        serialized_data = []
        for obj in objects_to_serialize:
            if isinstance(obj, Note):
                body = QNoteSerializer(obj, context=self.get_serializer_context()).data
                serialized_data.append({'type': 'Note', 'body': body})
            elif isinstance(obj, _Response):
                body = QResponseSerializer(obj, context=self.get_serializer_context()).data
                serialized_data.append({'type': 'Response', 'body': body})

        # Mark as read
        note_ids_to_read = [obj.id for obj in objects_to_serialize if isinstance(obj, Note)]
        response_ids_to_read = [obj.id for obj in objects_to_serialize if isinstance(obj, _Response)]
        if note_ids_to_read:
            user.read_notes.add(*note_ids_to_read)
        if response_ids_to_read:
            user.read_responses.add(*response_ids_to_read)

        if page is not None:
            return self.get_paginated_response(serialized_data)
        return DRFResponse(serialized_data)
