from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import models
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.db.models import Q

from adoorback.models import AdoorTimestampedModel
from notification.models import Notification

from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE
from safedelete.managers import SafeDeleteManager

User = get_user_model()


class Reaction(AdoorTimestampedModel, SafeDeleteModel):
    user = models.ForeignKey(User, related_name='reaction_set', on_delete=models.CASCADE)
    emoji = models.CharField(blank=False, null=False, max_length=20)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.IntegerField()
    target = GenericForeignKey('content_type', 'object_id')

    reaction_targetted_notis = GenericRelation(Notification,
                                           content_type_field='target_type',
                                           object_id_field='target_id')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'emoji', 'content_type', 'object_id'], condition=Q(deleted__isnull=True), name='unique_reaction'),
        ]
        ordering = ['created_at']

    def __str__(self):
        return self.emoji

    @property
    def type(self):
        return self.__class__.__name__

    objects = SafeDeleteManager()

    _safedelete_policy = SOFT_DELETE_CASCADE
