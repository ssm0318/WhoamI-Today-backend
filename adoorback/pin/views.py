from django.db import transaction, IntegrityError
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import generics, permissions
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from adoorback.utils.permissions import IsOwnerOrReadOnly
from adoorback.utils.validators import adoor_exception_handler
from pin.models import Pin
from pin.serializers import PinSerializer

User = get_user_model()

class PinCreate(generics.CreateAPIView):
    queryset = Pin.objects.all()
    serializer_class = PinSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        try:
            serializer.save()
        except IntegrityError:
            raise ValidationError({
                "detail": _("이미 고정된 게시물입니다."),
                "code": "duplicate_pin"
            })


class PinDestroy(generics.DestroyAPIView):
    queryset = Pin.objects.all()
    serializer_class = PinSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]

    def get_exception_handler(self):
        return adoor_exception_handler


class MyPinList(generics.ListAPIView):
    serializer_class = PinSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Pin.objects.filter(user=self.request.user).order_by('-created_at')


class UserPinList(generics.ListAPIView):
    serializer_class = PinSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        username = self.kwargs.get('username')
        return Pin.objects.filter(user__username=username).order_by('-created_at')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        visible_pins = []
        for pin in queryset:
            if pin.content_object and pin.content_object.is_audience(request.user):
                visible_pins.append(pin)
        
        page = self.paginate_queryset(visible_pins)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(visible_pins, many=True)
        return Response(serializer.data)
