from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import models, transaction
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

from adoorback.models import AdoorTimestampedModel
from adoorback.utils.helpers import wrap_content
from like.models import Like
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
            models.UniqueConstraint(fields=['user', 'emoji', 'content_type', 'object_id'],
                                    condition=Q(deleted__isnull=True), name='unique_reaction'),
        ]
        ordering = ['created_at']

    def __str__(self):
        return f'{self.user} reacted with {self.emoji}  on {self.content_type} ({self.object_id})'

    @property
    def type(self):
        return self.__class__.__name__

    objects = SafeDeleteManager()

    _safedelete_policy = SOFT_DELETE_CASCADE


@transaction.atomic
@receiver(post_save, sender=Reaction)
def create_reaction_noti(instance, created, **kwargs):
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

    content_preview = wrap_content(origin)

    redirect_url = f'/{origin.type.lower()}s/{origin.id}'
    Notification.objects.create_or_update_notification(user=user, actor=actor,
                                                       origin=origin, target=target, noti_type="reaction_response_noti",
                                                       redirect_url=redirect_url, content_preview=content_preview,
                                                       emoji=target.emoji)
