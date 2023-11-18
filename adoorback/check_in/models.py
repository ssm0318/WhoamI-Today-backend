from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from account.models import FriendGroup
from adoorback.models import AdoorTimestampedModel

from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE

User = get_user_model()


class CheckIn(AdoorTimestampedModel, SafeDeleteModel):
    AVAILABILITY_CHOICES = [
        ('no_status', 'No Status'),
        ('not_available', 'Not Available'),
        ('may_be_slow', 'May Be Slow'),
        ('available', 'Available'),
    ]

    user = models.ForeignKey(User, related_name='check_in_set', on_delete=models.CASCADE)
    is_active = models.BooleanField(default=False)
    mood = models.CharField(blank=True, null=True, max_length=5)
    availability = models.CharField(max_length=20, choices=AVAILABILITY_CHOICES, default='no_status')
    description = models.CharField(blank=True, null=True, max_length=88)
    # song = SpotifySongField()

    share_everyone = models.BooleanField(default=True)
    share_groups = models.ManyToManyField(FriendGroup, related_name='shared_check_ins', blank=True)
    share_friends = models.ManyToManyField(User, related_name='shared_check_ins', blank=True)

    readers = models.ManyToManyField(User, related_name='read_check_ins')

    _safedelete_policy = SOFT_DELETE_CASCADE

    def __str__(self):
        return self.description
    
    @property
    def reader_ids(self):
        return self.readers.values_list('id', flat=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['is_active']),
        ]


@transaction.atomic
@receiver(post_save, sender=CheckIn)
def add_user_to_readers(instance, created, **kwargs):
    if not created:
        return
    instance.readers.add(instance.user)
    instance.save()
