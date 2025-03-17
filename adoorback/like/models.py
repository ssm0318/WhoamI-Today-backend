from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from safedelete.managers import SafeDeleteManager
from safedelete.models import SafeDeleteModel, SOFT_DELETE

from adoorback.models import AdoorTimestampedModel
from adoorback.utils.content_types import get_comment_type, get_like_type
from adoorback.utils.helpers import wrap_content
from notification.helpers import find_like_noti
from notification.models import Notification

User = get_user_model()


class LikeManager(SafeDeleteManager):
    use_for_related_fields = True

    def comment_likes_only(self, **kwargs):
        return self.filter(content_type=get_comment_type(), **kwargs)

    def post_likes_only(self, **kwargs):
        return self.exclude(content_type=get_comment_type(), **kwargs)


class Like(AdoorTimestampedModel, SafeDeleteModel):
    user = models.ForeignKey(User, related_name='like_set', on_delete=models.CASCADE)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.IntegerField()
    target = GenericForeignKey('content_type', 'object_id')

    like_targetted_notis = GenericRelation(Notification,
                                           content_type_field='target_type',
                                           object_id_field='target_id')
    objects = LikeManager()

    # Set to SOFT_DELETE.
    # If set to SOFT_DELETE_CASCADE, notification that has this like as a target is immediately deleted even if there are remaining actors.
    _safedelete_policy = SOFT_DELETE  

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'content_type', 'object_id'], condition=Q(deleted__isnull=True),
                                    name='unique_like'),
        ]
        ordering = ['id']

    def __str__(self):
        return f'{self.user} likes {self.content_type} ({self.object_id})'

    @property
    def type(self):
        return self.__class__.__name__


@transaction.atomic
@receiver(post_save, sender=Like)
def create_like_noti(instance, created, **kwargs):
    if instance.deleted or not created:
        return

    user = instance.target.author
    actor = instance.user
    origin = instance.target
    target = instance

    if user == actor:  # do not create notification for liker him/herself.
        return

    if actor.id in user.user_report_blocked_ids:  # do not create notification from/for blocked user
        return

    content = wrap_content(origin.content)

    if origin.type == 'Comment' and origin.target.type == 'Comment':  # if is reply
        redirect_url = f'/{origin.target.target.type.lower()}s/' \
                       f'{origin.target.target.id}'
        Notification.objects.create_or_update_notification(user=user, actor=actor,
                                                           origin=origin, target=target, noti_type="like_reply_noti",
                                                           redirect_url=redirect_url,
                                                           content_en=content, content_ko=content)
    elif origin.type == 'Comment':  # if is comment
        redirect_url = f'/{origin.target.type.lower()}s/' \
                       f'{origin.target.id}'
        Notification.objects.create_or_update_notification(user=user, actor=actor,
                                                           origin=origin, target=target, noti_type="like_comment_noti",
                                                           redirect_url=redirect_url,
                                                           content_en=content, content_ko=content)
    elif origin.type == 'Response':
        redirect_url = f'/{origin.type.lower()}s/{origin.id}'
        Notification.objects.create_or_update_notification(user=user, actor=actor,
                                                           origin=origin, target=target, noti_type="like_response_noti",
                                                           redirect_url=redirect_url,
                                                           content_en=content, content_ko=content)
    elif origin.type == 'Note':
        redirect_url = f'/{origin.type.lower()}s/{origin.id}'
        Notification.objects.create_or_update_notification(user=user, actor=actor,
                                                           origin=origin, target=target, noti_type="like_note_noti",
                                                           redirect_url=redirect_url,
                                                           content_en=content, content_ko=content)

@receiver(post_save, sender=Like)
def update_like_noti_after_delete(instance, **kwargs):
    if not instance.deleted:
        return

    user = instance.target.author
    actor = instance.user
    origin = instance.target

    # 1. Check whether there is a notification with target set as this instance.
    # If there is, and there are other actors in the notification,
    # we need to change the target of the notification to one of the remaining actors
    # before we remove the actor in create_or_update_notification.
    noti = Notification.objects.filter(target_type=get_like_type(), target_id=instance.id).first()
    if noti:
        remaining_actors = noti.actors.exclude(id=actor.id)
        if remaining_actors.exists():
            # Find the oldest like from a user other than current actor
            oldest_like = Like.objects.filter(
                content_type=instance.content_type,
                object_id=instance.object_id,
            ).exclude(user=instance.user).order_by('created_at').first()

            if oldest_like:
                noti.target_id = oldest_like.id
                noti.save()
            else:
                return
        else:
            noti.delete()
            return


    # 2. Find notification linked with this instance (Like object).
    # Since this Like instance is not the target of the notification,
    # we need to find this using find_like_noti method.
    noti_type = None
    if origin.type == 'Comment' and origin.target.type == 'Comment':
        noti_type = "like_reply_noti"
    elif origin.type == 'Comment':
        noti_type = "like_comment_noti"
    elif origin.type == 'Response':
        noti_type = "like_response_noti"
    elif origin.type == 'Note':
        noti_type = "like_note_noti"

    if noti_type is None:
        return
    
    noti = find_like_noti(user, origin, noti_type)

    if not noti:  # noti was already deleted because instance.user was the only actor
        return

    content = wrap_content(origin.content)

    # 3. Call method to modify notification content.
    # (eliminate this actor from the original notification)
    Notification.objects.create_or_update_notification(
        actor=actor,
        user=user,
        origin=origin,
        target=instance,
        noti_type=noti_type,
        redirect_url='',
        content_en=content,
        content_ko=content
    )
