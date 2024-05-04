from django.db import transaction
from django.http import Http404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from safedelete.models import SOFT_DELETE_CASCADE

from adoorback.utils.permissions import IsNotBlocked, IsAuthorOrReadOnly, IsShared
from adoorback.utils.validators import adoor_exception_handler
from like.serializers import LikeSerializer
from note.models import Note, NoteImage
from note.serializers import NoteSerializer
import comment.serializers as cs
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
    serializer_class = cs.PostCommentsSerializer
    permission_classes = [IsAuthenticated, IsNotBlocked]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        return Note.objects.filter(id=self.kwargs.get('pk'))

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data[0])

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data[0])


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
