from datetime import timedelta
from django.utils import timezone
from django.db.models import Q

from rest_framework import generics, permissions
from rest_framework import status
from rest_framework.response import Response

from playlist.models import Song
from playlist.serializers import SongSerializer


class SongList(generics.ListCreateAPIView):
    """
    List (Feed): Returns songs from friends/close_friends/self within 7 days.
    Create: Share a song.
    """
    serializer_class = SongSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        cutoff_date = timezone.now() - timedelta(days=7)

        # Get connected users (friends + close friends)
        connected_user_ids = user.connected_user_ids
        # Include self
        visible_user_ids = connected_user_ids + [user.id]

        return Song.objects.filter(
            user_id__in=visible_user_ids,
            created_at__gte=cutoff_date
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class SongDetail(generics.DestroyAPIView):
    """
    Destroy: Unshare a song (soft delete).
    """
    queryset = Song.objects.all()
    serializer_class = SongSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Allow user to delete only their own songs
        return Song.objects.filter(user=self.request.user)
