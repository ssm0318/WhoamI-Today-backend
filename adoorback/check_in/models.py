from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from adoorback.models import AdoorTimestampedModel

from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE

from content_report.models import ContentReport

User = get_user_model()


class CheckIn(AdoorTimestampedModel, SafeDeleteModel):
    SOCIAL_BATTERY_CHOICES = [
        ('completely_drained', 'Completely Drained'),
        ('low', 'Low Social Battery'),
        ('needs_recharge', 'Needs Recharge'),
        ('moderately_social', 'Moderately Social'),
        ('fully_charged', 'Fully Charged'),
        ('super_social', 'Super Social Mode (HMU!)'),
    ]

    user = models.ForeignKey(User, related_name='check_in_set', on_delete=models.CASCADE)
    is_active = models.BooleanField(default=False)
    mood = models.CharField(blank=True, null=True, max_length=5)
    social_battery = models.CharField(blank=True, null=True, max_length=30, choices=SOCIAL_BATTERY_CHOICES)
    description = models.CharField(blank=True, null=True, max_length=88)
    track_id = models.CharField(blank=True, null=True, max_length=50)
    visibility = ArrayField(
        models.CharField(max_length=20),
        blank=True,
        default=list
    )

    readers = models.ManyToManyField(User, related_name='read_check_ins')

    _safedelete_policy = SOFT_DELETE_CASCADE

    def __str__(self):
        return self.description or ""
    
    @property
    def reader_ids(self):
        return self.readers.values_list('id', flat=True)
    
    def is_audience(self, user):
        from account.models import Connection

        content_type = ContentType.objects.get_for_model(self)
        if ContentReport.objects.filter(user=user, content_type=content_type, object_id=self.pk).exists():
            return False

        if self.user.id in user.user_report_blocked_ids:
            return False

        if self.user == user:
            return True

        # Hierarchical Visibility Checks
        if 'public' in self.visibility:
            return True
            
        # Check Follower
        if 'followers' in self.visibility:
            if user.is_following(self.user):
                return True
                
        # Check Friend
        if 'friends' in self.visibility:
             # Check for connection
             if Connection.objects.filter(
                (models.Q(user1=self.user) & models.Q(user2=user)) | 
                (models.Q(user1=user) & models.Q(user2=self.user))
             ).exists():
                 return True
                 
        # Check Close Friend
        if 'close_friends' in self.visibility:
            if user.is_close_friend(self.user):
                # Upgrade logic
                connection = Connection.get_connection_between(self.user, user)
                if connection:
                    if self.user == connection.user1:
                        update_past_posts = connection.user1_update_past_posts
                        upgrade_time = connection.user1_upgrade_time
                    else:
                        update_past_posts = connection.user2_update_past_posts
                        upgrade_time = connection.user2_upgrade_time

                    if update_past_posts:
                        return True
                    elif upgrade_time is None:
                        return True
                    elif self.created_at > upgrade_time:
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
