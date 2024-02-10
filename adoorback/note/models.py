from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.auth import get_user_model
from django.db import models
from safedelete import SOFT_DELETE_CASCADE
from safedelete.models import SafeDeleteModel

from adoorback.models import AdoorModel
from comment.models import Comment
from like.models import Like
from notification.models import Notification

User = get_user_model()


class Note(AdoorModel, SafeDeleteModel):
    author = models.ForeignKey(User, related_name='note_set', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='images/', blank=True, null=True)

    note_comments = GenericRelation(Comment)
    note_likes = GenericRelation(Like)

    note_targetted_notis = GenericRelation(Notification,
                                           content_type_field='target_type',
                                           object_id_field='target_id')
    note_originated_notis = GenericRelation(Notification,
                                            content_type_field='origin_type',
                                            object_id_field='origin_id')

    _safedelete_policy = SOFT_DELETE_CASCADE

    def __str__(self):
        return self.content

    @property
    def type(self):
        return self.__class__.__name__

    @property
    def liked_user_ids(self):
        return self.note_likes.values_list('user_id', flat=True)

    @property
    def participants(self):
        return self.note_comments.values_list('author_id', flat=True).distinct()

    class Meta:
        indexes = [
            models.Index(fields=['-id']),
        ]
