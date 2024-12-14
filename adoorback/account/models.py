from datetime import time
import glob
import os
import secrets
import urllib.parse

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser, UserManager
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import FileSystemStorage
from django.db import models, transaction
from django.db.models import Max, Q
from django.db.models.signals import post_save, post_delete
from django.db.utils import IntegrityError
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField
from safedelete import DELETED_INVISIBLE
from safedelete.models import SafeDeleteModel, SOFT_DELETE_CASCADE, HARD_DELETE
from safedelete.managers import SafeDeleteManager

from adoorback.models import AdoorTimestampedModel
from adoorback.utils.validators import AdoorUsernameValidator
from notification.models import NotificationActor
from category.models import Category  # Add this import


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


def to_profile_images(instance, filename):
    return 'profile_images/{username}.png'.format(username=instance)


def random_profile_color():
    # use random int so that initial users get different colors
    return '#{0:06X}'.format(secrets.randbelow(16777216))


class UserCustomManager(UserManager, SafeDeleteManager):
    _safedelete_visibility = DELETED_INVISIBLE


class User(AbstractUser, AdoorTimestampedModel, SafeDeleteModel):
    username_validator = AdoorUsernameValidator()

    username = models.CharField(
        _('username'),
        max_length=50,
        help_text=_('Required. 50 characters or fewer. Letters (alphabet & 한글), digits, -, _, and @ only.'),
        validators=[username_validator],
        error_messages={
            'unique': _("A user with that username already exists."),
        },
    )
    email = models.EmailField(unique=True)
    question_history = models.CharField(null=True, max_length=500)
    profile_pic = models.CharField(default=random_profile_color, max_length=7)
    profile_image = models.ImageField(storage=OverwriteStorage(), upload_to=to_profile_images, blank=True, null=True)
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
    pronouns = models.CharField(null=True, max_length=30)
    bio = models.CharField(null=True, max_length=118)

    friends = models.ManyToManyField('self', symmetrical=True, blank=True)  # TODO: fade out
    favorites = models.ManyToManyField('self', symmetrical=False, related_name='favorite_of', blank=True)
    hidden = models.ManyToManyField('self', symmetrical=False, related_name='hidden_by', blank=True)

    friendship_targetted_notis = GenericRelation("notification.Notification",
                                                 content_type_field='target_type',
                                                 object_id_field='target_id')
    friendship_originated_notis = GenericRelation("notification.Notification",
                                                  content_type_field='origin_type',
                                                  object_id_field='origin_id')

    _safedelete_policy = SOFT_DELETE_CASCADE

    # Django 기본 설정에서는 username이 고유해야 하지만 (USERNAME_FIELD)를 우리는 고유하지 않은 username을 허용하고 싶음.
    # USERNAME_FIELD를 email로 설정하여 이메일을 인증에 사용하고, username은 고유하지 않아도 되도록 함.
    USERNAME_FIELD = 'email'  
    
    # USERNAME_FIELD를 email로 바꾼대신, 반드시 username을 입력하�� 요구.
    REQUIRED_FIELDS = ['username'] 

    objects = UserCustomManager()

    class Meta:
        indexes = [
            models.Index(fields=['id']),
            models.Index(fields=['username'], condition=models.Q(deleted__isnull=True), name='username_active_idx'),
        ]
        constraints = [
            models.UniqueConstraint(fields=['username'], condition=Q(deleted__isnull=True), name='unique_active_username')
        ]
        ordering = ['id']

    def __str__(self):
        return self.username

    def save(self, *args, **kwargs):
        # Ensure that only connected users can be added to favorites or hidden
        if self.id is not None:  # Existing user
            current_connected_users = set(self.connected_user_ids)
            new_favorites = set(self.favorites.values_list('id', flat=True))
            new_hidden = set(self.hidden.values_list('id', flat=True))

            if not new_favorites.issubset(current_connected_users) or not new_hidden.issubset(current_connected_users):
                raise ValueError("Favorites and hidden must be among the user's connected users.")

        super().save(*args, **kwargs)

    @classmethod
    # TODO: fade out
    def are_friends(cls, user1, user2):
        return user2.id in user1.friend_ids or user1 == user2

    @classmethod
    def user_read(cls, user1, user2):
        # Check if user1 has read all of user2's responses
        user2_response_queryset = user1.can_access_response_set(user2)
        if any(user1.id not in response.reader_ids for response in user2_response_queryset):
            return False

        # Check if user1 has read user2's current check-in
        user2_check_in = user1.can_access_check_in(user2)
        if user2_check_in and user1.id not in user2_check_in.reader_ids:
            return False

        # Check if user1 has read user2's notes
        user2_note_queryset = user1.can_access_note_set(user2)
        if any(user1.id not in note.reader_ids for note in user2_note_queryset):
            return False

        return True

    @property
    def type(self):
        return self.__class__.__name__

    def is_connected(self, user):
        """Checks if self (current user) is connected with user"""
        return Connection.objects.filter(
            Q(user1=user, user2=self) | Q(user1=self, user2=user)
        ).exists()

    def is_follower(self, user):
        """Checks if self (current user) is a 'follower' of user"""
        return Connection.objects.filter(
            Q(user1=user, user2=self, user1_choice='follower') |
            Q(user1=self, user2=user, user2_choice='follower')
        ).exists()

    def is_friend(self, user):
        """Checks if self (current user) is a 'friend' of user"""
        return Connection.objects.filter(
            Q(user1=user, user2=self, user1_choice='friend') |
            Q(user1=self, user2=user, user2_choice='friend')
        ).exists()

    @property
    def connected_users(self):
        connections = Connection.objects.filter(
            Q(user1=self) | Q(user2=self)
        ).values_list('user1', 'user2')

        id_list = [
            user2_id if user1_id == self.id else user1_id
            for user1_id, user2_id in connections
        ]

        return User.objects.filter(id__in=id_list)
    
    @property
    def followers(self):
        connections = Connection.objects.filter(
            Q(user1=self, user1_choice='follower') | 
            Q(user2=self, user2_choice='follower')
        ).values_list('user1', 'user2')

        id_list = [
            user2_id if user1_id == self.id else user1_id
            for user1_id, user2_id in connections
        ]

        return User.objects.filter(id__in=id_list)
    
    @property
    def friends_(self):  # TODO: change to friends after 'friends' field is removed
        connections = Connection.objects.filter(
            Q(user1=self, user1_choice='friend') | 
            Q(user2=self, user2_choice='friend')
        ).values_list('user1', 'user2')

        id_list = [
            user2_id if user1_id == self.id else user1_id
            for user1_id, user2_id in connections
        ]

        return User.objects.filter(id__in=id_list)

    @property
    def connected_user_ids(self):
        connections = Connection.objects.filter(
            Q(user1=self) | Q(user2=self)
        ).values_list('user1', 'user2')

        id_list = [
            user2_id if user1_id == self.id else user1_id
            for user1_id, user2_id in connections
        ]

        return id_list

    @property
    def follower_ids(self):
        connections = Connection.objects.filter(
            Q(user1=self, user1_choice='follower') | 
            Q(user2=self, user2_choice='follower')
        ).values_list('user1', 'user2')

        id_list = [
            user2_id if user1_id == self.id else user1_id
            for user1_id, user2_id in connections
        ]

        return id_list

    @property
    def friend_ids(self):
        connections = Connection.objects.filter(
            Q(user1=self, user1_choice='friend') | 
            Q(user2=self, user2_choice='friend')
        ).values_list('user1', 'user2')

        id_list = [
            user2_id if user1_id == self.id else user1_id
            for user1_id, user2_id in connections
        ]

        return id_list

    @property
    def reported_user_ids(self):
        from user_report.models import UserReport
        return list(UserReport.objects.filter(user=self).values_list('reported_user_id', flat=True))

    @property
    def user_report_blocked_ids(self):  # returns ids of users
        from user_report.models import UserReport
        return list(UserReport.objects.filter(user=self).values_list('reported_user_id', flat=True)) + list(
            UserReport.objects.filter(reported_user=self).values_list('user_id', flat=True))

    @property
    def content_report_blocked_model_ids(self):  # returns ids of posts
        from content_report.models import ContentReport
        blocked_contents = []
        for report in self.content_report_set.all():
            content_type = ContentType.objects.get_for_id(report.content_type_id).model
            blocked_contents.append((content_type, report.object_id))
        return blocked_contents

    @property
    def unread_message_cnt(self):
        chat_rooms = self.chat_rooms.all()
        unread_cnt = 0
        for room in chat_rooms:
            unread_cnt += room.unread_cnt(self)
        return unread_cnt

    def most_recent_update(self, user):
        # most recent update time of self (among self's content that user can access)
        most_recent_response = user.can_access_response_set(self).aggregate(Max('created_at'))['created_at__max']
        most_recent_check_in = user.can_access_check_in(self)
        if most_recent_check_in:
            most_recent_check_in = most_recent_check_in.created_at
        most_recent_note = user.can_access_note_set(self).aggregate(Max('created_at'))['created_at__max']
        most_recent_times = [most_recent_response, most_recent_check_in, most_recent_note]
        most_recent_times = [time for time in most_recent_times if time is not None]
        
        if most_recent_times:
            return max(most_recent_times)
        else:
            return None

    def can_access_response_set(self, user):
        from qna.models import Response
        from category.models import Subscription

        #gets the user's subscribed categories
        subscribed_categories = Subscription.objects.filter(user=self).values_list('category_id', flat=True)

        # Then, filters responses by:
        # 1. Author (user parameter)
        # 2. Category (must be in subscribed categories)
        # 3. Sharing scope (user must be included in sharing scope)
        responses = Response.objects.filter(
            author=user,
            category_id__in=subscribed_categories
        )
        
        # Further filter by checking if self is in sharing_scope
        return [response for response in responses if self in response.sharing_scope.get_members()]

    def can_access_check_in(self, user):
        # return check-in of user that self can access
        from check_in.models import CheckIn
        check_in = user.check_in_set.filter(is_active=True).first()
        if check_in and CheckIn.is_audience(check_in, self):
            return check_in
        return None

    def can_access_note_set(self, user):
        from note.models import Note
        from category.models import Subscription
        
        subscribed_categories = Subscription.objects.filter(user=self).values_list('category_id', flat=True)
        
        notes = Note.objects.filter(
            author=user,
            category_id__in=subscribed_categories
        )
        return [note for note in notes if self in note.sharing_scope.get_members()]


#added 11/18/24:
    def get_subscribed_content(self, content_type=None):
        from category.models import Subscription
        from qna.models import Response
        from note.models import Note
        
        subscribed_categories = Subscription.objects.filter(user=self).values_list('category_id', flat=True)
        
        if content_type == 'response':
            responses = Response.objects.filter(category_id__in=subscribed_categories)
            return [r for r in responses if self in r.sharing_scope.get_members()]
        elif content_type == 'note':
            notes = Note.objects.filter(category_id__in=subscribed_categories)
            return [n for n in notes if self in n.sharing_scope.get_members()]
        else:
            responses = Response.objects.filter(category_id__in=subscribed_categories)
            notes = Note.objects.filter(category_id__in=subscribed_categories)
            return (
                [r for r in responses if self in r.sharing_scope.get_members()],
                [n for n in notes if self in n.sharing_scope.get_members()]
            )


class FriendRequest(AdoorTimestampedModel, SafeDeleteModel):
    requester = models.ForeignKey(
        get_user_model(), related_name='sent_friend_requests', on_delete=models.CASCADE)
    requestee = models.ForeignKey(
        get_user_model(), related_name='received_friend_requests', on_delete=models.CASCADE)
    accepted = models.BooleanField(null=True)
    requester_choice = models.CharField(max_length=10, choices=[('friend', 'Friend'), ('follower', 'Follower')], null=True)

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


class Connection(AdoorTimestampedModel, SafeDeleteModel):
    CHOICES = (
        ('friend', 'Friend'),
        ('follower', 'Follower'),
    )

    user1 = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name='connections_as_user1'
    )
    user2 = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name='connections_as_user2'
    )
    user1_choice = models.CharField(max_length=10, choices=CHOICES)
    user2_choice = models.CharField(max_length=10, choices=CHOICES)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user1', 'user2', ], condition=Q(deleted__isnull=True), name='unique_connection'),
                models.CheckConstraint(check=~models.Q(user1=models.F('user2')), name='no_self_connection')
        ]
        indexes = [
            models.Index(fields=['user1', 'user2']),
            models.Index(fields=['user1', 'user1_choice']),
            models.Index(fields=['user2', 'user2_choice']),
        ]

    def __str__(self):
        return f"Connection between {self.user1} and {self.user2}"
    
    def save(self, *args, **kwargs):
        # check if reverse Connection already exists
        if Connection.objects.filter(user1=self.user2, user2=self.user1).exists():
            raise ValueError("A reverse Connection already exists.")
        
        # Ensure that user1 always has the smaller ID to enforce consistency
        if self.user1.id > self.user2.id:
            self.user1, self.user2 = self.user2, self.user1
            self.user1_choice, self.user2_choice = self.user2_choice, self.user1_choice

        super().save(*args, **kwargs)

    @classmethod
    def get_connection_between(cls, user_a, user_b):
        """Fetch the Connection object between two users, if it exists."""
        return cls.objects.filter(
            Q(user1=user_a, user2=user_b) | Q(user1=user_b, user2=user_a)
        ).first()

    def user1_is_friend(self):
        """Check if user2 set user1 as 'friend'."""
        return self.user2_choice == 'friend'
    
    def user2_is_friend(self):
        """Check if user1 set user2 as 'friend'."""
        return self.user1_choice == 'friend'
    
    def user1_is_follower(self):
        """Check if user2 set user1 as 'follower'."""
        return self.user2_choice == 'follower'
    
    def user2_is_follower(self):
        """Check if user1 set user2 as 'follower'."""
        return self.user1_choice == 'follower'

class BlockRec(AdoorTimestampedModel, SafeDeleteModel):
    user = models.ForeignKey(
        get_user_model(), related_name='block_recs', on_delete=models.CASCADE)
    blocked_user = models.ForeignKey(
        get_user_model(), related_name='received_block_recs', on_delete=models.CASCADE)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'blocked_user'], condition=Q(deleted__isnull=True),
                                    name='unique_block_rec'),
        ]

    def __str__(self):
        return f'{self.user} blocked recommendation of {self.blocked_user}'

    @property
    def type(self):
        return self.__class__.__name__

#removed deprecated Subscription model

@transaction.atomic
@receiver(post_delete, sender=Connection)
def connection_removed(instance, **kwargs):
    '''
    when Connection is deleted, 
    1) remove related notis
    2) remove connected user from favorites & hidden
    3) inactivate chat room
    '''
    user1 = instance.user1
    user2 = instance.user2

    # 1. Remove friendship related notis from both users
    user1.friendship_targetted_notis.filter(user=user2).delete(force_policy=HARD_DELETE)
    user2.friendship_targetted_notis.filter(user=user1).delete(force_policy=HARD_DELETE)
    FriendRequest.objects.filter(requester=user1, requestee=user2).delete(force_policy=HARD_DELETE)
    FriendRequest.objects.filter(requester=user2, requestee=user1).delete(force_policy=HARD_DELETE)

    # 2. Remove from favorites & hidden
    try:
        user1.favorites.remove(user2)
    except IntegrityError:
        pass
    try:
        user1.hidden.remove(user2)
    except IntegrityError:
        pass
    try:
        user2.favorites.remove(user1)
    except IntegrityError:
        pass
    try:
        user2.hidden.remove(user1)
    except IntegrityError:
        pass

    # 3. Inactivate chat rooms
    from chat.models import ChatRoom
    chat_rooms = ChatRoom.objects.filter(users__in=[user1, user2])
    for chat_room in chat_rooms:
        if chat_room.users.count() == 2:
            chat_room.active = False
            chat_room.save()


@transaction.atomic
@receiver(post_save, sender=FriendRequest)
def create_connection_noti(created, instance, **kwargs):
    if instance.deleted:
        return

    accepted = instance.accepted
    Notification = apps.get_model('notification', 'Notification')
    requester = instance.requester
    requestee = instance.requestee

    if requester.id in requestee.user_report_blocked_ids:  # do not create notification from/for blocked user
        return

    if created:
        noti = Notification.objects.create(user=requestee,
                                           origin=requester, target=instance,
                                           message_ko=f'{requester.username}님이 친구 요청을 보냈습니다.',
                                           message_en=f'{requester.username} has requested to be your friend.',
                                           redirect_url=f'/users/{requester.username}')
        NotificationActor.objects.create(user=requester, notification=noti)
        return
    elif accepted:
        if requester.is_connected(requestee):  # receiver function was triggered by undelete
            return

        noti = Notification.objects.create(user=requestee,
                                           origin=requester, target=requester,
                                           message_ko=f'{requester.username}님과 친구가 되었습니다.',
                                           message_en=f'You are now friends with {requester.username}.',
                                           redirect_url=f'/users/{requester.username}')
        NotificationActor.objects.create(user=requester, notification=noti)
        noti = Notification.objects.create(user=requester,
                                           origin=requestee, target=requestee,
                                           message_ko=f'{requestee.username}님과 친구가 되었습니다.',
                                           message_en=f'You are now friends with {requestee.username}.',
                                           redirect_url=f'/users/{requestee.username}')
        NotificationActor.objects.create(user=requestee, notification=noti)

        # make connection
        Connection.objects.create(
            user1=requester,
            user2=requestee,
            user1_choice='friend',  # TODO: fix hard coded 'friend' option
            user2_choice='friend',  # TODO: fix hard coded 'friend' option
        )

        # make chat room
        from chat.models import ChatRoom
        chat_room = ChatRoom()
        chat_room.save()
        chat_room.users.add(requester, requestee)

    # make friend request notification invisible once requestee has responded
    instance.friend_request_targetted_notis.filter(user=requestee,
                                                   actors__id=requester.id).update(is_read=True,
                                                                                   is_visible=False)


@transaction.atomic
@receiver(post_save, sender=User)
def user_created(created, instance, **kwargs):
    '''
    when User is created, 
    1) send notification
    '''
    if instance.deleted:
        return

    if created:
        # send notification
        from notification.models import Notification
        admin = User.objects.filter(is_superuser=True).first()
        noti = Notification.objects.create(user=instance,
                                           target=admin,
                                           origin=admin,
                                           message_ko=f"{instance.username}님, 보다 재밌는 후엠아이 이용을 위해 친구를 추가해보세요!",
                                           message_en=f"{instance.username}, try making friends to share your whoami!",
                                           redirect_url='/friends/explore')
        NotificationActor.objects.create(user=admin, notification=noti)


@transaction.atomic
@receiver(post_save, sender=User)
def delete_old_profile_image(sender, instance, **kwargs):
    if instance.pk:
        if instance.profile_image:
            profile_images_dir = os.path.join(settings.MEDIA_ROOT, 'profile_images')
            current_image_name = os.path.basename(instance.profile_image.name)
            current_hash = current_image_name.split('_')[-1].split('.')[0]

            # username_{hash}.png 형태의 모든 파일을 찾습니다.
            pattern = os.path.join(profile_images_dir, f'{instance.username}_*.png')
            existing_images = glob.glob(pattern)
            print(len(existing_images))

            for image_path in existing_images:
                image_name = os.path.basename(image_path)
                image_hash = image_name.split('_')[-1].split('.')[0]
                if image_hash != current_hash:
                    os.remove(image_path)  # 해시 값이 다른 파일을 삭제합니다.

def is_included(author, user, sharing_scope):
    if sharing_scope == 'public':
        return True
    if sharing_scope == 'private':
        return user == author
    if sharing_scope == 'neighbor':
        return user.is_connected(author)
    if sharing_scope == 'friend':
        return user.is_friend(author)
    return False
