from django.db import models, transaction
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model

from adoorback.models import AdoorTimestampedModel

from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE

User = get_user_model()


class ContentReport(AdoorTimestampedModel, SafeDeleteModel):
    user = models.ForeignKey(User, related_name='content_report_set', on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey('content_type', 'object_id')

    _safedelete_policy = SOFT_DELETE_CASCADE
    
    class Meta:
        indexes = [
            models.Index(fields=['id']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} reported {self.target.type} {self.target.id}'

    @property
    def type(self):
        return self.__class__.__name__
