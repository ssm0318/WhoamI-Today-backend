from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model

from adoorback.models import AdoorTimestampedModel
from check_in.models import Song

from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE

User = get_user_model()


class PlaylistFeed(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='playlist_feed')
    song = models.ForeignKey(Song, on_delete=models.CASCADE)
    category = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    sort_order = models.IntegerField(default=0)
    feed_id = models.UUIDField(null=True) # Batch ID

    class Meta:
        indexes = [
            models.Index(fields=['user', 'created_at']),
        ]
