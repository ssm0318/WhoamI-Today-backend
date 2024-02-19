import urllib

from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.auth import get_user_model
from django.db import models
from django.core.files.storage import FileSystemStorage
from safedelete import SOFT_DELETE_CASCADE
from safedelete.models import SafeDeleteModel

from django.conf import settings

from account.models import FriendGroup
from adoorback.models import AdoorModel
from comment.models import Comment
from like.models import Like
from notification.models import Notification

User = get_user_model()


class OverwriteStorage(FileSystemStorage):
    base_url = urllib.parse.urljoin(settings.BASE_URL, settings.MEDIA_URL)

    def get_available_name(self, name, max_length=None):
        if self.exists(name):
            self.delete(name)
        return name


def note_image_path(instance, filename):
    return f'note_images/{instance.author_id}/{filename}'


class OverwriteStorage(FileSystemStorage):
    base_url = urllib.parse.urljoin(settings.BASE_URL, settings.MEDIA_URL)

    def get_available_name(self, name, max_length=None):
        if self.exists(name):
            self.delete(name)
        return name


def note_image_path(instance, filename):
    return f'note_images/{instance.author_id}/{filename}'


class Note(AdoorModel, SafeDeleteModel):
    author = models.ForeignKey(User, related_name='note_set', on_delete=models.CASCADE)
    image = models.ImageField(upload_to=note_image_path, storage=OverwriteStorage(), null=True, blank=True)

    note_comments = GenericRelation(Comment)
    note_likes = GenericRelation(Like)

    share_everyone = models.BooleanField(default=False, blank=True)
    share_groups = models.ManyToManyField(FriendGroup, related_name='shared_notes', blank=True)
    share_friends = models.ManyToManyField(User, related_name='shared_notes', blank=True)

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

    def is_audience(self, user):
        if self.author == user:
            return True

        if self.share_everyone:
            return True

        if not User.are_friends(self.author, user):
            return False

        if self.share_groups.filter(friends=user).exists():
            return True

        if self.share_friends.filter(pk=user.pk).exists():
            return True

        return False

    class Meta:
        indexes = [
            models.Index(fields=['-id']),
        ]

