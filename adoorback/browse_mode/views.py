from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from browse_mode.models import BrowseModePreset, BrowseModeWishlistEntry
from browse_mode.serializers import (
    BrowseModePresetSerializer,
    BrowseModeWishlistEntrySerializer,
)


class BrowseModePresetList(generics.ListCreateAPIView):
    serializer_class = BrowseModePresetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return BrowseModePreset.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        try:
            serializer.save(user=self.request.user)
        except IntegrityError:
            raise ValidationError(
                {'name': "You already have a preset with this name."}
            )


class BrowseModePresetDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BrowseModePresetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return BrowseModePreset.objects.filter(user=self.request.user)

    def perform_update(self, serializer):
        try:
            serializer.save()
        except IntegrityError:
            raise ValidationError(
                {'name': "You already have a preset with this name."}
            )


class BrowseModePresetMarkUsed(APIView):
    """Bump `last_used_at` so recently-activated presets float to the top of
    the saved list. Frontend hits this when a custom preset is selected from
    the session-start prompt."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        preset = get_object_or_404(
            BrowseModePreset.objects.filter(user=request.user), pk=pk
        )
        preset.last_used_at = timezone.now()
        preset.save(update_fields=['last_used_at', 'updated_at'])
        serializer = BrowseModePresetSerializer(preset)
        return Response(serializer.data, status=status.HTTP_200_OK)


class BrowseModeWishlistCreate(generics.CreateAPIView):
    """Free-text feature requests submitted from the customize sheet.
    Write-only from the user's POV — they don't read each others' entries.
    """

    serializer_class = BrowseModeWishlistEntrySerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
