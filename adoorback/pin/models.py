from django.db import models
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from adoorback.models import AdoorTimestampedModel

from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE

User = get_user_model()

class Pin(AdoorTimestampedModel, SafeDeleteModel):
    user = models.ForeignKey(User, related_name='pin_set', on_delete=models.CASCADE)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'content_type', 'object_id'],
                condition=Q(deleted__isnull=True),
                name='unique_pin'
            )
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} pinned {self.content_object}'

    @property
    def type(self):
        return self.__class__.__name__
