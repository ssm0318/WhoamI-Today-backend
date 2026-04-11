from itertools import chain

from rest_framework.response import Response as DRFResponse

from account.serializers_q import QCurrentUserSerializer, QUserProfileSerializer
from account.views import (
    CurrentUserDetail, UserProfile, CurrentUserNoteList, UserNoteList,
    CurrentUserAllPostList, UserAllPostList, FriendFeed,
)
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
