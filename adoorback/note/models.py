import urllib

from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import FileSystemStorage
from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from safedelete import SOFT_DELETE_CASCADE
from safedelete.models import SafeDeleteModel

from django.conf import settings

from account.models import FriendGroup
from adoorback.models import AdoorModel
from comment.models import Comment
from content_report.models import ContentReport
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
    return f'note_images/{instance.note.author_id}/{filename}'


class Note(AdoorModel, SafeDeleteModel):
    author = models.ForeignKey(User, related_name='note_set', on_delete=models.CASCADE)

    note_comments = GenericRelation(Comment)
    note_likes = GenericRelation(Like)
    readers = models.ManyToManyField(User, related_name='read_notes')

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
    
    @property
    def reader_ids(self):
        return self.readers.values_list('id', flat=True)

    def is_audience(self, user):
        content_type = ContentType.objects.get_for_model(self)
        if ContentReport.objects.filter(user=user, content_type=content_type, object_id=self.pk).exists():
            print("is_audience: report exists")
            return False

        if self.author.id in user.user_report_blocked_ids:
            print("is_audience: author is blocked")
            return False

        if self.author == user:
            print("is_audience: author is user")
            return True

        if User.are_friends(self.author, user):
            return True

        return False

    class Meta:
        indexes = [
            models.Index(fields=['-id']),
        ]


class NoteImage(SafeDeleteModel):
    note = models.ForeignKey('Note', related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to=note_image_path, storage=OverwriteStorage())
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    _safedelete_policy = SOFT_DELETE_CASCADE

    def __str__(self):
        return f'image id {self.id} of {self.note}'

    class Meta:
        ordering = ['-created_at']


@transaction.atomic
@receiver(post_save, sender=Note)
def add_author_to_readers(instance, created, **kwargs):
    if not created:
        return
    instance.readers.add(instance.author)
    instance.save()
