from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from adoorback.models import AdoorTimestampedModel
from feed.models import Post

from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE

User = get_user_model()


class ContentReport(AdoorTimestampedModel, SafeDeleteModel):
    user = models.ForeignKey(User, related_name='content_report_set', on_delete=models.CASCADE)
    post = models.ForeignKey(Post, related_name='content_report_set', on_delete=models.CASCADE)

    _safedelete_policy = SOFT_DELETE_CASCADE
    
    class Meta:
        indexes = [
            models.Index(fields=['id']),
        ]

    def __str__(self):
        return f'{self.user} reported {self.post.content_type} {self.post.object_id}'

    @property
    def type(self):
        return self.__class__.__name__
