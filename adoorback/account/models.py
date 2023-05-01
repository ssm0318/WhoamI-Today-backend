"""Django Model
Define Models for account APIs
"""
import secrets
import os

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser, UserManager
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models, transaction
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from adoorback.models import AdoorTimestampedModel

from safedelete import DELETED_INVISIBLE
from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE, HARD_DELETE
from safedelete.managers import SafeDeleteManager

from adoorback.models import AdoorTimestampedModel
from adoorback.utils.validators import AdoorUsernameValidator

class OverwriteStorage(FileSystemStorage):
    def get_available_name(self, name, max_length=None):
        if self.exists(name):
            os.remove(os.path.join(settings.MEDIA_ROOT, name))
        return name


def to_profile_images(instance, filename):
    return 'profile_images/{username}.png'.format(username=instance)
GENDER_CHOICES = (
    (0, _('여성')),
    (1, _('남성')),
    (2, _('트랜스젠더 (transgender)')),
    (3, _('논바이너리 (non-binary/non-conforming)')),
    (4, _('응답하고 싶지 않음')),
)

ETHNICITY_CHOICES = (
    (0, _('미국 원주민/알래스카 원주민 (American Indian/Alaska Native)')),
    (1, _('아시아인 (Asian)')),
    (2, _('흑인/아프리카계 미국인 (Black/African American)')),
    (3, _('히스패닉/라틴계 미국인 (Hispanic/Latino)')),
    (4, _('하와이 원주민/다른 태평양 섬 주민 (Native Hawaiian/Other Pacific Islander)')),
    (5, _('백인 (White)')),
)


def random_profile_color():
    # use random int so that initial users get different colors
    return '#{0:06X}'.format(secrets.randbelow(16777216))
GENDER_CHOICES = (
    (0, _('여성')),
    (1, _('남성')),
    (2, _('트랜스젠더 (transgender)')),
    (3, _('논바이너리 (non-binary/non-conforming)')),
    (4, _('응답하고 싶지 않음')),
)

ETHNICITY_CHOICES = (
    (0, _('미국 원주민/알래스카 원주민 (American Indian/Alaska Native)')),
    (1, _('아시아인 (Asian)')),
    (2, _('흑인/아프리카계 미국인 (Black/African American)')),
    (3, _('히스패닉/라틴계 미국인 (Hispanic/Latino)')),
    (4, _('하와이 원주민/다른 태평양 섬 주민 (Native Hawaiian/Other Pacific Islander)')),
    (5, _('백인 (White)')),
)


class UserCustomManager(UserManager, SafeDeleteManager):
    _safedelete_visibility = DELETED_INVISIBLE


class User(AbstractUser, AdoorTimestampedModel, SafeDeleteModel):
    """User Model
    This model extends the Django Abstract User model
    """
    username_validator = AdoorUsernameValidator()

    username = models.CharField(
        _('username'),
        max_length=20,
        unique=True,
        help_text=_('Required. 20 characters or fewer. Letters (alphabet & 한글), digits and _ only.'),
        validators=[username_validator],
        error_messages={
            'unique': _("A user with that username already exists."),
        },
    )
    email = models.EmailField(unique=True)
    question_history = models.CharField(null=True, max_length=500)
    profile_pic = models.CharField(default=random_profile_color, max_length=7)
    profile_image = models.ImageField(storage=OverwriteStorage(), upload_to=to_profile_images, blank=True, null=True)
    friends = models.ManyToManyField('self', symmetrical=True, blank=True)
    gender = models.IntegerField(choices=GENDER_CHOICES, null=True)
    date_of_birth = models.DateField(null=True)
    ethnicity = models.IntegerField(choices=ETHNICITY_CHOICES, null=True)
    research_agreement = models.BooleanField(default=False)
    language = models.CharField(max_length=10,
                                choices=settings.LANGUAGES,
                                default=settings.LANGUAGE_CODE)

    friendship_targetted_notis = GenericRelation("notification.Notification",
                                                 content_type_field='target_type',
                                                 object_id_field='target_id')
    friendship_originated_notis = GenericRelation("notification.Notification",
                                                  content_type_field='origin_type',
                                                  object_id_field='origin_id')

    _safedelete_policy = SOFT_DELETE_CASCADE

    objects = UserCustomManager()

    class Meta:
        indexes = [
            models.Index(fields=['id']),
            models.Index(fields=['username']),
        ]
        ordering = ['id']

    @classmethod
    def are_friends(cls, user1, user2):
        return user2.id in user1.friend_ids or user1 == user2

    @property
    def type(self):
        return self.__class__.__name__

    @property
    def friend_ids(self):
        return list(self.friends.values_list('id', flat=True))

    @property
    def reported_user_ids(self):
        from user_report.models import UserReport
        return list(UserReport.objects.filter(user=self).values_list('reported_user_id', flat=True))

    @property
    def user_report_blocked_ids(self): # returns ids of users
        from user_report.models import UserReport
        return list(UserReport.objects.filter(user=self).values_list('reported_user_id', flat=True)) + list(UserReport.objects.filter(reported_user=self).values_list('user_id', flat=True))

    @property
    def content_report_blocked_ids(self): # returns ids of posts
        from content_report.models import ContentReport
        return list(ContentReport.objects.filter(user=self).values_list('post_id', flat=True))


class FriendRequest(AdoorTimestampedModel, SafeDeleteModel):
    """FriendRequest Model
    This model describes FriendRequest between users
    """
    requester = models.ForeignKey(
        get_user_model(), related_name='sent_friend_requests', on_delete=models.CASCADE)
    requestee = models.ForeignKey(
        get_user_model(), related_name='received_friend_requests', on_delete=models.CASCADE)
    accepted = models.BooleanField(null=True)

    friend_request_targetted_notis = GenericRelation("notification.Notification",
                                                     content_type_field='target_type',
                                                     object_id_field='target_id')
    friend_request_originated_notis = GenericRelation("notification.Notification",
                                                      content_type_field='origin_type',
                                                      object_id_field='origin_id')

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['requester', 'requestee', ], condition=Q(deleted__isnull=True), name='unique_friend_request'),
        ]
        indexes = [
            models.Index(fields=['-updated_at']),
        ]
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.requester} sent to {self.requestee} ({self.accepted})'

    @property
    def type(self):
        return self.__class__.__name__


@transaction.atomic
@receiver(m2m_changed)
def delete_friend_noti(action, pk_set, instance, **kwargs):
    if action == "post_remove":
        friend = User.objects.get(id=pk_set.pop())
        # remove friendship related notis from both users
        friend.friendship_targetted_notis.filter(user=instance).delete(force_policy=HARD_DELETE)
        instance.friendship_targetted_notis.filter(user=friend).delete(force_policy=HARD_DELETE)
        FriendRequest.objects.filter(requester=instance, requestee=friend).delete(force_policy=HARD_DELETE)
        FriendRequest.objects.filter(requester=friend, requestee=instance).delete(force_policy=HARD_DELETE)


@transaction.atomic
@receiver(post_save, sender=FriendRequest)
def create_friend_noti(created, instance, **kwargs):
    if instance.deleted:
        return

    accepted = instance.accepted
    Notification = apps.get_model('notification', 'Notification')
    requester = instance.requester
    requestee = instance.requestee

    if requester.id in requestee.user_report_blocked_ids: # do not create notification from/for blocked user
        return

    if created:
        Notification.objects.create(user=requestee, actor=requester,
                                    origin=requester, target=instance,
                                    message_ko=f'{requester.username}님이 친구 요청을 보냈습니다.',
                                    message_en=f'{requester.username} has requested to be your friend.',
                                    redirect_url=f'/users/{requester.username}')
        return
    elif accepted:
        if User.are_friends(requestee, requester):  # receiver function was triggered by undelete
            return

        Notification.objects.create(user=requestee, actor=requester,
                                    origin=requester, target=requester,
                                    message_ko=f'{requester.username}님과 친구가 되었습니다.',
                                    message_en=f'You are now friends with {requester.username}.',
                                    redirect_url=f'/users/{requester.username}')
        Notification.objects.create(user=requester, actor=requestee,
                                    origin=requestee, target=requestee,
                                    message_ko=f'{requestee.username}님과 친구가 되었습니다.',
                                    message_en=f'You are now friends with {requestee.username}.',
                                    redirect_url=f'/users/{requestee.username}')
        # add friendship
        requester.friends.add(requestee)

    # make friend request notification invisible once requestee has responded
    instance.friend_request_targetted_notis.filter(user=requestee,
                                                   actor=requester).update(is_read=True,
                                                                           is_visible=False)
