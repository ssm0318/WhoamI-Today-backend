import os
import urllib.parse

from django.conf import settings
from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericRelation
from django.core.files.storage import FileSystemStorage

from comment.models import Comment
from like.models import Like
from adoorback.models import AdoorTimestampedModel

from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE

User = get_user_model()


class OverwriteStorage(FileSystemStorage):
    base_url = urllib.parse.urljoin(settings.BASE_URL, settings.MEDIA_URL)

    def get_available_name(self, name, max_length=None):
        if self.exists(name):
            os.remove(os.path.join(settings.MEDIA_ROOT, name))
        return name


def to_profile_images(instance, filename):
    return 'moment/{username}-{date}.png'.format(username=instance.author, date=instance.date)

class Moment(AdoorTimestampedModel, SafeDeleteModel):
    author = models.ForeignKey(User, related_name='moment_set', on_delete=models.CASCADE)
    date = models.DateField(blank=False, null=False, default='2008-10-03')
    available_limit = models.DateTimeField(blank=False, null=False, default='2008-10-03')
    mood = models.CharField(blank=True, null=True, max_length=20)
    photo = models.ImageField(storage=OverwriteStorage(), upload_to=to_profile_images, blank=True, null=True)
    description = models.CharField(blank=True, null=True, max_length=20)
    
    moment_comments = GenericRelation(Comment)
    moment_likes = GenericRelation(Like)
    readers = models.ManyToManyField(User, related_name='read_moments')
    
    _safedelete_policy = SOFT_DELETE_CASCADE
    
    def save(self, *args, **kwargs):
        if self.author and not self.readers.filter(pk=self.author.pk).exists():
            self.readers.add(self.author)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.description
    
    @property
    def type(self):
        return self.__class__.__name__

    @property
    def liked_user_ids(self):
        return self.moment_likes.values_list('user_id', flat=True)

    @property
    def participants(self):
        return self.moment_comments.values_list('author_id', flat=True).distinct()
    
    @property
    def reader_ids(self):
        return self.readers.values_list('id', flat=True)

    class Meta:
        indexes = [
            models.Index(fields=['-id']),
        ]