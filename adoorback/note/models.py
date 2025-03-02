import urllib
import uuid

from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import FileSystemStorage
from django.db import models, transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from safedelete import SOFT_DELETE_CASCADE, HARD_DELETE
from safedelete.models import SafeDeleteModel
from django.db.models import Q

from django.conf import settings

from account.models import Subscription, Connection
from adoorback.models import AdoorModel
from comment.models import Comment
from content_report.models import ContentReport
from like.models import Like
from notification.models import Notification, NotificationActor
from reaction.models import Reaction

User = get_user_model()


class OverwriteStorage(FileSystemStorage):
    base_url = urllib.parse.urljoin(settings.BASE_URL, settings.MEDIA_URL)

    def get_available_name(self, name, max_length=None):
        if self.exists(name):
            self.delete(name)
        return name


def note_image_path(instance, filename):
    unique_id = str(uuid.uuid4())[:8]
    return f'note_images/{instance.note.author_id}/{instance.note.id}/{unique_id}_{filename}'


class Note(AdoorModel, SafeDeleteModel):
    author = models.ForeignKey(User, related_name='note_set', on_delete=models.CASCADE)
    visibility = models.CharField(
        max_length=20,
        choices=[('friends', 'Friends'), ('close_friends', 'Close Friends')],
        default='friends'
    )

    note_comments = GenericRelation(Comment)
    note_likes = GenericRelation(Like)
    readers = models.ManyToManyField(User, related_name='read_notes')
    is_edited = models.BooleanField(default=False)

    note_targetted_notis = GenericRelation(Notification,
                                           content_type_field='target_type',
                                           object_id_field='target_id')
    note_originated_notis = GenericRelation(Notification,
                                            content_type_field='origin_type',
                                            object_id_field='origin_id')

    _safedelete_policy = SOFT_DELETE_CASCADE

    def __str__(self):
        return self.content

    def save(self, *args, **kwargs):
        if self.pk is not None:  # not when created
            original = Note.objects.get(pk=self.pk)
            if original.content != self.content:
                self.is_edited = True
        super().save(*args, **kwargs)

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

    @property
    def reactions(self):
        from django.contrib.contenttypes.models import ContentType
        note_content_type = ContentType.objects.get_for_model(self)
        return Reaction.objects.filter(content_type=note_content_type, object_id=self.id)

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

        connection = Connection.get_connection_between(self.author, user)

        if not connection:
            return False

        if self.visibility == 'close_friends':
            is_close = self.author.is_close_friend(user)
            if not is_close:
                return False

            if self.author == connection.user1:
                update_past_posts = connection.user1_update_past_posts
                upgrade_time = connection.user1_upgrade_time
            else:
                update_past_posts = connection.user2_update_past_posts
                upgrade_time = connection.user2_upgrade_time

            if update_past_posts:
                return True
            if upgrade_time is None:  # users were close friends from the beginning
                return True
            return self.created_at > upgrade_time
        
        return True

    class Meta:
        indexes = [
            models.Index(fields=['-id']),
        ]


class NoteImage(SafeDeleteModel):
    note = models.ForeignKey('Note', related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to=note_image_path, storage=OverwriteStorage())
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    _safedelete_policy = HARD_DELETE

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


@receiver(post_delete, sender=NoteImage)
def delete_image_file(sender, instance, **kwargs):
    # Ensure the file itself is deleted from storage
    instance.image.delete(save=False)


@receiver(post_save, sender=Note)
def send_notifications_to_subscribers(sender, instance, created, **kwargs):
    if not created:
        return

    author = instance.author
    note_content_type = ContentType.objects.get_for_model(Note)
    
    subscribers = Subscription.objects.filter(
        subscribed_to=author,
        content_type=note_content_type,
    ).values_list('subscriber', flat=True)

    for subscriber_id in subscribers:
        subscriber = get_user_model().objects.get(id=subscriber_id)
        
        noti = Notification.objects.create(
            user=subscriber,
            origin=instance,
            target=instance,
            message_ko=f'{author.username}님이 새 노트를 작성했습니다.',
            message_en=f'{author.username} has posted a new note.',
            redirect_url=f'/notes/{instance.id}'
        )
        NotificationActor.objects.create(user=author, notification=noti)
