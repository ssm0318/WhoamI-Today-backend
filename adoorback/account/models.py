"""Django Model
Define Models for account APIs
"""
from datetime import time
import secrets
import os
import urllib.parse

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser, UserManager
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models, transaction
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from django_countries.fields import CountryField
from safedelete import DELETED_INVISIBLE
from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE, HARD_DELETE
from safedelete.managers import SafeDeleteManager

from adoorback.models import AdoorTimestampedModel
from adoorback.utils.validators import AdoorUsernameValidator


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


class OverwriteStorage(FileSystemStorage):
    base_url = urllib.parse.urljoin(settings.BASE_URL, settings.MEDIA_URL)

    def get_available_name(self, name, max_length=None):
        if self.exists(name):
            os.remove(os.path.join(settings.MEDIA_ROOT, name))
        return name


def to_profile_images(instance, filename):
    return 'profile_images/{username}.png'.format(username=instance)


def random_profile_color():
    # use random int so that initial users get different colors
    return '#{0:06X}'.format(secrets.randbelow(16777216))


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
    nationality = CountryField(null=True)
    research_agreement = models.BooleanField(default=False)
    signature = models.CharField(null=True, max_length=100)
    date_of_signature = models.DateField(null=True)
    language = models.CharField(max_length=10,
                                choices=settings.LANGUAGES,
                                default=settings.LANGUAGE_CODE)
    timezone = models.CharField(default=settings.TIME_ZONE, max_length=50)
    noti_time = models.TimeField(default=time(16, 0))

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


class FriendGroup(SafeDeleteModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='friend_groups')
    name = models.CharField(max_length=30)
    friends = models.ManyToManyField(User, blank=True)
    order = models.IntegerField(default=0)

    _safedelete_policy = SOFT_DELETE_CASCADE

    def __str__(self):
        return f'group "{self.name}" of user "{self.user.username}"'


@transaction.atomic
@receiver(m2m_changed, sender=User.friends.through)
def friend_removed(action, pk_set, instance, **kwargs):
    '''
    when Friendship is destroyed, 
    1) remove related notis
    2) remove friend from all share_friends of all posts
    '''
    if action == "post_remove":
        for friend_id in pk_set:
            friend = User.objects.get(id=friend_id)

            # remove friendship related notis from both users
            friend.friendship_targetted_notis.filter(user=instance).delete(force_policy=HARD_DELETE)
            instance.friendship_targetted_notis.filter(user=friend).delete(force_policy=HARD_DELETE)
            FriendRequest.objects.filter(requester=instance, requestee=friend).delete(force_policy=HARD_DELETE)
            FriendRequest.objects.filter(requester=friend, requestee=instance).delete(force_policy=HARD_DELETE)

            # remove from share_friends (TODO: if 'Note' model is added, add related logic here)
            for response in friend.shared_responses.filter(author=instance):
                response.share_friends.remove(friend)
            for response in instance.shared_responses.filter(author=friend):
                response.share_friends.remove(instance)
            for check_in in friend.shared_check_ins.filter(is_active=True, user=instance):
                check_in.share_friends.remove(friend)
            for check_in in instance.shared_check_ins.filter(is_active=True, user=friend):
                check_in.share_friends.remove(instance)


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


@transaction.atomic
@receiver(post_save, sender=User)
def user_created(created, instance, **kwargs):
    '''
    when User is created, 
    1) send notification
    2) add default friend group 'close friends'
    '''
    if instance.deleted:
        return
    
    if created:
        # send notification
        from notification.models import Notification
        admin = User.objects.filter(is_superuser=True).first()
        Notification.objects.create(user=instance,
                                    actor=admin,
                                    target=admin,
                                    origin=admin,
                                    message_ko=f"{instance.username}님, 보다 재밌는 후엠아이 이용을 위해 친구를 추가해보세요!",
                                    message_en=f"{instance.username}, try making friends to share your whoami!",
                                    redirect_url='/')
        
        # add default FriendGroup (close_friends)
        default_group, created = FriendGroup.objects.get_or_create(
            name='close friends',
            user=instance
        )
        instance.friend_groups.add(default_group)
