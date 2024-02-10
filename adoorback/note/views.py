from django.db import transaction
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from adoorback.utils.permissions import IsNotBlocked, IsAuthorOrReadOnly, IsShared
from adoorback.utils.validators import adoor_exception_handler
from note.models import Note
from note.serializers import NoteSerializer
import comment.serializers as cs
import qna.serializers as qs


class NoteList(generics.ListCreateAPIView):
    queryset = Note.objects.all()
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated, IsNotBlocked]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class NoteComments(generics.ListAPIView):
    serializer_class = cs.PostCommentsSerializer
    permission_classes = [IsAuthenticated, IsNotBlocked]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        return Note.objects.filter(id=self.kwargs.get('pk'))


class NoteDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated, IsAuthorOrReadOnly, IsShared]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        return Note.objects.get(id=self.kwargs.get('pk'))

    def get_queryset(self):
        return Note.objects.all()
