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
        ('available', 'Available'),
        ('busy', 'Busy'),
        ('might_get_distracted', 'Might get distracted'),
        ('urgent_only', 'Urgent only'),
        ('about_to_sleep', 'About to sleep'),
        ('studying', 'Studying'),
        ('in_transit', 'In transit'),
        ('feeling_social', 'Feeling social'),
        ('feeling_quiet', 'Feeling quiet'),
    ]

    user = models.ForeignKey(User, related_name='check_in_set', on_delete=models.CASCADE)
    is_active = models.BooleanField(default=False)
    mood = models.CharField(blank=True, null=True, max_length=5)
    availability = models.CharField(max_length=20, choices=AVAILABILITY_CHOICES, default='no_status')
    description = models.CharField(blank=True, null=True, max_length=88)
    track_id = models.CharField(blank=True, null=True, max_length=50)

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
    
    def is_audience(self, user):
        """
        Returns True if the given user is in the audience that can view this check_in.
        """
        if not User.are_friends(self.user, user):
            return False
        
        if self.share_everyone:
            return True

        if self.share_groups.filter(friends=user).exists():
            return True

        if self.share_friends.filter(pk=user.pk).exists():
            return True

        return False

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
