from django.db import transaction
from django.shortcuts import render
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from adoorback.utils.validators import adoor_exception_handler
from note.models import Note


class NoteList(generics.CreateAPIView):
    queryset = Note.objects.all()
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
