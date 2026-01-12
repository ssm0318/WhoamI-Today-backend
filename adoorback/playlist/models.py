from django.db import models
from django.contrib.auth import get_user_model

from adoorback.models import AdoorTimestampedModel

from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE

User = get_user_model()


class Song(AdoorTimestampedModel, SafeDeleteModel):
    user = models.ForeignKey(User, related_name='songs', on_delete=models.CASCADE)
    track_id = models.CharField(max_length=50)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} shared {self.track_id}"
