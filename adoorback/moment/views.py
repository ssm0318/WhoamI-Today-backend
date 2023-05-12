from django.shortcuts import render

from django.db import transaction

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser

from adoorback.utils.validators import adoor_exception_handler

import moment.serializers as ms
from moment.models import Moment

class MomentList(generics.CreateAPIView):
    """
    List all moments, or create a new moment.
    """
    queryset = Moment.objects.all()
    serializer_class = ms.MomentSerializer
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
