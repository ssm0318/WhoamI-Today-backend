from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.db.models import Q

from adoorback.models import AdoorTimestampedModel

from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE
from safedelete.managers import SafeDeleteManager

User = get_user_model()


class UserReport(AdoorTimestampedModel, SafeDeleteModel):
    """UserReport Model
    This model describes UserReport between users
    """
    user = models.ForeignKey(
        get_user_model(), related_name='filed_user_reports', on_delete=models.CASCADE)
    reported_user = models.ForeignKey(
        get_user_model(), related_name='received_user_report', on_delete=models.CASCADE)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'reported_user'], condition=Q(deleted__isnull=True), name='unique_user_report'),
        ]
        indexes = [
            models.Index(fields=['-created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} reported {self.reported_user}'

    @property
    def type(self):
        return self.__class__.__name__


@transaction.atomic
@receiver(post_save, sender=UserReport)
def delete_blocked_user_friendship(instance, created, **kwargs):
    if not created:
        return
        
    user = instance.user
    reported_user = instance.reported_user

    if reported_user.id in user.friend_ids:
        user.friends.remove(reported_user)
    
    from account.models import FriendRequest
    from feed.models import ResponseRequest
    FriendRequest.objects.filter(requester=user, requestee=reported_user).delete(force_policy=SOFT_DELETE_CASCADE)
    FriendRequest.objects.filter(requester=reported_user, requestee=user).delete(force_policy=SOFT_DELETE_CASCADE)
    ResponseRequest.objects.filter(requester=user, requestee=reported_user).delete(force_policy=SOFT_DELETE_CASCADE)
    ResponseRequest.objects.filter(requester=reported_user, requestee=user).delete(force_policy=SOFT_DELETE_CASCADE)
