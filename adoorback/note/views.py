from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.http import Http404
from django.db.models import Q
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from safedelete.models import SOFT_DELETE_CASCADE

from adoorback.utils.permissions import IsNotBlocked, IsAuthorOrReadOnly, IsShared
from adoorback.utils.validators import adoor_exception_handler
import comment.serializers as cs
from like.serializers import LikeSerializer
from note.models import Note, NoteImage
from note.serializers import NoteSerializer
import qna.serializers as qs


class NoteCreate(generics.CreateAPIView):
    queryset = Note.objects.all()
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated, IsNotBlocked]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        images = self.request.FILES.getlist('images')
        note_instance = serializer.save(author=self.request.user)
        serializer.save(author=self.request.user)
        for image in images:
            NoteImage.objects.create(note=note_instance, image=image)


class NoteComments(generics.ListAPIView):
    serializer_class = cs.CommentFriendSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        from comment.models import Comment
        from content_report.models import ContentReport

        current_user = self.request.user

        note = Note.objects.get(id=self.kwargs.get('pk'))
        if not note.is_audience(current_user):
            return PermissionDenied("You do not have permission to view these comments.")
        
        blocked_content_ids = ContentReport.objects.filter(
            user=current_user,
            content_type=ContentType.objects.get_for_model(Comment)
        ).values_list('object_id', flat=True)

        return note.note_comments.exclude(
            id__in=blocked_content_ids,
            author_id__in=current_user.user_report_blocked_ids
        ).order_by('-created_at')

    def list(self, request, *args, **kwargs):
        current_user = self.request.user
        comments = self.get_queryset()

        all_comments_and_replies = comments
        for comment in comments:
            replies = comment.replies.exclude(author_id__in=current_user.user_report_blocked_ids)
            all_comments_and_replies = all_comments_and_replies.union(replies)

        page = self.paginate_queryset(comments)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            extra_field = {'count_including_replies': all_comments_and_replies.count()}
            paginated_response = self.get_paginated_response(serializer.data)
            paginated_response.data.update(extra_field)
            return paginated_response

        serializer = self.get_serializer(comments, many=True)
        extra_field = {'count_including_replies': all_comments_and_replies.count()}
        return Response({'results': serializer.data, **extra_field})


class NoteDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated, IsAuthorOrReadOnly, IsShared]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())

        pk = self.kwargs.get('pk')
        obj = queryset.filter(pk=pk).first()

        if obj is None:
            raise Http404('No Note matches the given query.')

        self.check_object_permissions(self.request, obj)

        return obj

    def get_queryset(self):
        return Note.objects.all()

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        new_images = request.FILES.getlist('images', [])
        existing_images = instance.images.all()

        for image in existing_images:
            image.delete(force_policy=SOFT_DELETE_CASCADE)

        for image in new_images:
            n = NoteImage.objects.create(note=instance, image=image)
        
        self.perform_update(serializer)
        return Response(serializer.data)


class NoteLikes(generics.ListAPIView):
    serializer_class = LikeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        from like.models import Like
        note_id = self.kwargs['pk']
        return Like.objects.filter(content_type__model='note', object_id=note_id)


class NoteRead(generics.UpdateAPIView):
    queryset = Note.objects.all()
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def patch(self, request, *args, **kwargs):
        current_user = self.request.user
        ids = request.data.get('ids', [])
        queryset = Note.objects.filter(id__in=ids)
        if len(ids) != queryset.count():
            return Response({'error': 'Note with provided IDs does not exist.'},
                                  status=status.HTTP_404_NOT_FOUND)
        for note in queryset:
            note.readers.add(current_user)
        serializer = self.get_serializer(queryset, many=True)

        return Response(serializer.data)
