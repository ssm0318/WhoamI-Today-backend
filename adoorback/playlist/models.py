from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model

from adoorback.models import AdoorTimestampedModel
from check_in.models import CheckIn

from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE

User = get_user_model()


class Song(models.Model):
    """
    Deprecated. use CheckIn with track_id instead.
    Kept for migration safety until fully removed.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    track_id = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} shared {self.track_id}"


class PlaylistFeed(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='playlist_feed')
    check_in = models.ForeignKey(CheckIn, on_delete=models.CASCADE)
    category = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    sort_order = models.IntegerField(default=0)
    feed_id = models.UUIDField(null=True) # Batch ID

    class Meta:
        indexes = [
            models.Index(fields=['user', 'created_at']),
        ]
