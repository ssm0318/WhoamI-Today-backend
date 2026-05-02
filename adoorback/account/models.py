from datetime import time
import glob
import os
import secrets
import urllib.parse
import uuid

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser, UserManager
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.files.storage import FileSystemStorage
from django.contrib.postgres.fields import ArrayField
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

from .email import email_manager
from adoorback.models import AdoorTimestampedModel
from adoorback.utils.validators import AdoorUsernameValidator
from notification.models import NotificationActor


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

VERSION_CHOICES = (
    ('version_w', 'Version W'),
    ('version_q', 'Version Q'),
)

USER_GROUP_CHOICES = (
    ('group_w_first', 'Start with Version W, then swap to Q'),
    ('group_q_first', 'Start with Version Q, then swap to W'),
)

USER_TYPE_CHOICES = (
    ('direct', 'Direct Participant'),
    ('indirect', 'Indirect Participant'),
)

CHIP_CATEGORY_CHOICES = [
    ('basic_identities', 'Basic Identities'),
    ('favorite_platform', 'Favorite Platform'),
    ('least_favorite_platform', 'Least Favorite Platform'),
    ('hobbies_activities', 'Hobbies & Activities'),
    ('music_entertainment', 'Music & Entertainment'),
    ('values_allyship', 'Values & Allyship'),
    ('on_my_mind', 'On My Mind'),
    ('as_a_friend', 'As a Friend'),
    ('online_persona', 'Online Persona'),
]

# Mirrors check_in.models.CheckIn.VISIBILITY_CHOICES — kept here to avoid cross-app import.
PROFILE_VISIBILITY_CHOICES = [
    ('public', 'Public'),
    ('friends', 'Friends'),
    ('close_friends', 'Close Friends'),
    ('only_me', 'Only Me'),
]

CHIP_CATEGORY_DESCRIPTIONS = {
    'basic_identities': 'Life stage, social style, and personal traits.',
    'favorite_platform': 'The platforms you love most.',
    'least_favorite_platform': 'The platforms you could do without.',
    'hobbies_activities': 'What you do with your time — sports, creative work, lifestyle.',
    'music_entertainment': 'What you consume — genres, media, formats.',
    'values_allyship': 'Values, causes, and allyship you stand for.',
    'on_my_mind': 'Current rabbit holes, intellectual interests, life-phase topics.',
    'as_a_friend': 'How you show up in relationships — personality and values.',
    'online_persona': 'How you behave on the internet — distinct behavioral archetypes.',
}

CHIPS_BY_CATEGORY = {
    'basic_identities': [
        'In High School', 'In College', 'In Grad School', 'Working',
        'Gap Year', 'Figuring It Out', 'Taking a Break', 'Busy Most Days',
        'Introverted', 'Extroverted', 'Ambivert',
        'Lowkey', 'Chaotic', 'Chill',
        'Early Bird', 'Night Owl',
        'New Here', 'Local', 'From Out of State', 'International',
        'Research Participant', 'Been in Studies Before',
        'Here to Meet People', 'Just Exploring', 'Down for Whatever',
    ],
    'favorite_platform': [
        'Instagram', 'TikTok', 'YouTube', 'Snapchat', 'X / Twitter',
        'Discord', 'Reddit', 'Pinterest', 'BeReal', 'Threads',
        'WhoamI Today (WIT)',
    ],
    'least_favorite_platform': [
        'Instagram', 'TikTok', 'YouTube', 'Snapchat', 'X / Twitter',
        'Discord', 'Reddit', 'Pinterest', 'BeReal', 'Threads',
        'WhoamI Today (WIT)',
    ],
    'hobbies_activities': [
        'Gaming', 'Basketball', 'Soccer', 'Volleyball', 'Tennis', 'Gym', 'Running',
        'Skating', 'Climbing', 'Hiking', 'Surfing', 'Cycling', 'Drawing',
        'Photography', 'Cooking', 'Baking', 'Thrifting', 'Journaling', 'Reading',
        'Coding', 'Music Production', 'Video Editing', 'Fashion', 'DIY',
    ],
    'music_entertainment': [
        'Hip-Hop', 'R&B', 'Pop', 'Indie', 'K-Pop', 'Rock', 'EDM', 'Jazz', 'Lo-Fi',
        'Anime', 'K-Drama', 'Reality TV', 'Horror', 'Sci-Fi', 'Documentaries',
        'Comedy', 'Podcasts', 'Manga/Webtoons',
    ],
    'values_allyship': [
        'Trans Rights', 'Reproductive Rights', 'Immigrant Rights',
        'Racial Justice', 'Disability Rights', 'Neurodiversity',
        'Climate', 'Mental Health', 'Feminism', 'Queer Community',
        'Body Positivity', 'Sex Positivity',
    ],
    'on_my_mind': [
        'Astrology', 'Psychology', 'Philosophy', 'Sustainability', 'Mental Health',
        'Skincare', 'Spirituality', 'Finance', 'Language Learning', 'AI & Tech',
        'Design', 'Writing', 'College/Career', 'Fitness Journey',
    ],
    'as_a_friend': [
        'Good Listener', 'Brutally Honest', 'Hype Person', 'Low Maintenance',
        'Planner', 'Spontaneous', 'Overthinker',
        'Go With the Flow', 'Needs Alone Time', 'Always Down to Talk',
        'Dry Humor', 'Keeps It Real',
    ],
    'online_persona': [
        'Lurker', 'Content Creator', 'Meme Collector', 'Night Scroller',
        'Occasional Poster', 'Story Watcher', 'Always in the Comments',
        'Curated Feed', 'Posts and Deletes', 'Oversharer', 'Silent Supporter',
        'Late Replier',
    ],
}

ALL_CHIP_NAMES = {chip for chips in CHIPS_BY_CATEGORY.values() for chip in chips}

PERSONA_CHOICES = [
    ('lurker', 'Lurker'),
    ('content_creator', 'Content Creator'),
    ('private_reactor', 'Private Reactor'),
    ('public_commenter', 'Public Commenter'),
    ('instant_responder', 'Instant Responder'),
    ('takes_my_time', 'Takes My Time'),
    ('daily_scroller', 'Daily Scroller'),
    ('occasional_checker', 'Occasional Checker'),
    ('scheduled_checker', 'Scheduled Checker'),
    ('night_owl', 'Night Owl'),
    ('early_bird', 'Early Bird'),
    ('emoji_fan', 'Emoji Fan'),
    ('word_person', 'Word Person'),
    ('poster', 'Poster'),
    ('commenter', 'Commenter'),
    ('selfie_poster', 'Selfie Poster'),
    ('photo_heavy', 'Photo Heavy'),
    ('text_poster', 'Text Poster'),
    ('deep_talks', 'Deep Talks'),
    ('curious_asker', 'Curious Asker'),
    ('open_book', 'Open Book'),
    ('closed_book', 'Closed Book'),
    ('nofilter_purist', '#NoFilter Purist'),
    ('curated_aesthetic', 'Curated Aesthetic'),
    ('weekend_user', 'Weekend User'),
    ('everyday_presence', 'Everyday Presence'),
    ('trend_watcher', 'Trend Watcher'),
    ('meme_lover', 'Meme Lover'),
    ('frequent_poster', 'Frequent Poster'),
    ('occasional_poster', 'Occasional Poster'),
    ('shares_many_at_once', 'Shares Many at Once'),
    ('random_and_casual', 'Random and Casual'),
    ('stream_of_consciousness', 'Stream of Consciousness'),
    ('one_liners', 'One Liners'),
    ('throwbacks', 'Throwbacks'),
    ('music_sharer', 'Music Sharer'),
    ('opinion_poster', 'Opinion Poster'),
    ('silent_supporter', 'Silent Supporter'),
    ('always_online', 'Always Online'),
    ('rarely_posts_but_watches_everything', 'Rarely Posts but Watches Everything'),
    ('binge_scroller', 'Binge Scroller'),
    ('silent_observer', 'Silent Observer'),
    ('active_listener', 'Active Listener'),
    ('thoughtful_responder', 'Thoughtful Responder'),
]

class OverwriteStorage(FileSystemStorage):
    base_url = urllib.parse.urljoin(settings.BASE_URL, settings.MEDIA_URL)


def to_profile_images(instance, filename):
    return 'profile_images/{username}.png'.format(username=instance)


def random_profile_color():
    # use random int so that initial users get different colors
    return '#{0:06X}'.format(secrets.randbelow(16777216))


def default_noti_period_days():
    return ['0', '1', '2', '3', '4', '5', '6']


def default_persona():
    return []

def default_username_history():
    return []


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
    nationality = CountryField(null=True)
    research_agreement = models.BooleanField(default=False)
    signature = models.CharField(null=True, max_length=100)
    date_of_signature = models.DateField(null=True)
    language = models.CharField(max_length=10,
                                choices=settings.LANGUAGES,
                                default=settings.LANGUAGE_CODE)
    timezone = models.CharField(default=settings.TIME_ZONE, max_length=50)
    noti_time = models.TimeField(default=time(16, 0))
    noti_period_days = ArrayField(
        models.CharField(),
        default=default_noti_period_days,
        help_text="Days of the week for notifications, where 0=Sunday, 1=Monday, etc."
    )
    name = models.CharField(null=True, blank=True, max_length=50)
    pronouns = models.CharField(null=True, max_length=30)
    bio = models.CharField(null=True, max_length=118)
    persona = ArrayField(
        models.CharField(max_length=500),
        default=default_persona,
        blank=True,
        help_text="Multiple persona choices for the user."
    )

    # Tracking when interests/personas were last updated
    interests_updated_at = models.DateTimeField(null=True, blank=True)
    personas_updated_at = models.DateTimeField(null=True, blank=True)

    # 4-way visibility enum fields (replaces *_friends_only booleans).
    # Values: 'public' / 'friends' / 'close_friends' / 'only_me'.
    name_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='public')
    pronouns_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='public')
    bio_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='public')
    music_entertainment_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='public')
    hobbies_activities_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='public')
    on_my_mind_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='public')
    as_a_friend_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='public')
    online_persona_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='public')
    favorite_platform_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='public')
    least_favorite_platform_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='public')
    basic_identities_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='public')
    values_allyship_visibility = models.CharField(max_length=20, choices=PROFILE_VISIBILITY_CHOICES, default='public')

    favorites = models.ManyToManyField('self', symmetrical=False, related_name='favorite_of', blank=True)
    hidden = models.ManyToManyField('self', symmetrical=False, related_name='hidden_by', blank=True)

    last_interest_card_category = models.CharField(
        max_length=50, choices=CHIP_CATEGORY_CHOICES, null=True, blank=True,
        help_text="Last interest category shown in discover feed card, for rotation."
    )

    ver_changed_at = models.DateTimeField(null=True)
    current_ver = models.CharField(max_length=20, choices=VERSION_CHOICES, default='version_w')
    user_group = models.CharField(max_length=20, choices=USER_GROUP_CHOICES, default='group_w_first')
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='indirect')
    invited_from = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, 
                                     related_name="invited_users")
    
    is_public = models.BooleanField(default=True)
    has_changed_pw = models.BooleanField(default=False)
    username_history = ArrayField(
        base_field=models.CharField(max_length=50),
        default=default_username_history,
        blank=True,
        help_text="History of previously used usernames"
    )
    email_verified = models.BooleanField(default=False)
    has_received_first_archive_noti = models.BooleanField(default=False)

    friendship_targetted_notis = GenericRelation("notification.Notification",
                                                 content_type_field='target_type',
                                                 object_id_field='target_id')
    friendship_originated_notis = GenericRelation("notification.Notification",
                                                  content_type_field='origin_type',
                                                  object_id_field='origin_id')

    _safedelete_policy = SOFT_DELETE_CASCADE

    # Django default setting requires username to be unique (USERNAME_FIELD), but we want to allow non-unique usernames.
    # Set USERNAME_FIELD to email to use email for authentication, allowing username to be non-unique.
    USERNAME_FIELD = 'email'  
    
    # Since we changed USERNAME_FIELD to email, require username to be mandatory.
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
        # add initial username to username_history
        if not self.pk and self.username and not self.username_history:
            self.username_history = [self.username]

        # Ensure that only connected users can be added to favorites or hidden
        if self.id is not None:  # Existing user
            current_connected_users = set(self.connected_user_ids)
            new_favorites = set(self.favorites.values_list('id', flat=True))
            new_hidden = set(self.hidden.values_list('id', flat=True))

            if not new_favorites.issubset(current_connected_users) or not new_hidden.issubset(current_connected_users):
                raise ValueError("Favorites and hidden must be among the user's connected users.")

        super().save(*args, **kwargs)

    def safe_delete(self):
        for actor in self.notificationactor_set.all():
            actor.delete()
        for noti in self.received_noti_set.all():
            noti.delete()
        self.delete()

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

    def is_friend(self, user):
        """Checks if self (current user) is a 'friend' of user"""
        return Connection.objects.filter(
            Q(user1=user, user2=self, user1_choice='friend') |
            Q(user1=self, user2=user, user2_choice='friend')
        ).exists()

    def is_close_friend(self, user):
        """Checks if self (current user) is a 'close_friend' of user"""
        return Connection.objects.filter(
            Q(user1=user, user2=self, user1_choice='close_friend') |
            Q(user1=self, user2=user, user2_choice='close_friend')
        ).exists()

    @property
    def has_connected_users(self):
        return Connection.objects.filter(Q(user1=self) | Q(user2=self)).exists()

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
    def friends(self):
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
    def close_friends(self):
        connections = Connection.objects.filter(
            Q(user1=self, user1_choice='close_friend') | 
            Q(user2=self, user2_choice='close_friend')
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
    def close_friend_ids(self):
        connections = Connection.objects.filter(
            Q(user1=self, user1_choice='close_friend') | 
            Q(user2=self, user2_choice='close_friend')
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
        blocked_contents = []
        for report in self.content_report_set.all():
            content_type = ContentType.objects.get_for_id(report.content_type_id).model
            blocked_contents.append((content_type, report.object_id))
        return blocked_contents

    @property
    def unread_message_cnt(self):
        from chat.models import ChatRoom, Message, GroupReadCursor
        from chat.wit_admin import WIT_ADMIN_USERNAME
        from django.db.models import Q

        blocked_ids = self.user_report_blocked_ids

        # 1-on-1 unread (apply same filters as ChatRoomList)
        dm_rooms = ChatRoom.objects.filter(Q(user1=self) | Q(user2=self), is_group=False)
        # Exclude blocked users
        if blocked_ids:
            dm_rooms = dm_rooms.exclude(
                (Q(user1=self) & Q(user2_id__in=blocked_ids)) |
                (Q(user2=self) & Q(user1_id__in=blocked_ids))
            )
        # Version isolation (exclude WIT Admin rooms which are version-agnostic)
        dm_rooms = dm_rooms.exclude(
            ~Q(Q(user1__username=WIT_ADMIN_USERNAME) | Q(user2__username=WIT_ADMIN_USERNAME)) & (
                (Q(user1=self) & ~Q(user2__current_ver=self.current_ver)) |
                (Q(user2=self) & ~Q(user1__current_ver=self.current_ver))
            )
        )
        dm_unread = Message.objects.filter(chat_room__in=dm_rooms, receiver=self, is_read=False).count()

        # Group unread (using read cursors)
        group_rooms = ChatRoom.objects.filter(members=self, is_group=True)
        group_unread = 0
        for room in group_rooms:
            cursor = GroupReadCursor.objects.filter(user=self, chat_room=room).first()
            if cursor and cursor.last_read_message:
                group_unread += room.messages.exclude(sender=self).filter(
                    created_at__gt=cursor.last_read_message.created_at
                ).count()
            else:
                group_unread += room.messages.exclude(sender=self).count()

        return dm_unread + group_unread

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
        # return responses of user that self can access
        from qna.models import Response
        response_ids = [response.id for response in user.response_set.all() if Response.is_audience(response, self)]
        response_queryset = Response.objects.filter(id__in=response_ids)
        return response_queryset

    def can_access_check_in(self, user):
        # return check-in of user that self can access
        from check_in.models import CheckIn
        check_in = user.check_in_set.filter(is_active=True).first()
        if check_in and CheckIn.is_audience(check_in, self):
            return check_in
        return None

    def can_access_note_set(self, user):
        from note.models import Note
        note_ids = [note.id for note in user.note_set.all() if Note.is_audience(note, self)]
        note_queryset = Note.objects.filter(id__in=note_ids)
        return note_queryset


class FriendRequest(AdoorTimestampedModel, SafeDeleteModel):
    requester = models.ForeignKey(
        get_user_model(), related_name='sent_friend_requests', on_delete=models.CASCADE)
    requestee = models.ForeignKey(
        get_user_model(), related_name='received_friend_requests', on_delete=models.CASCADE)
    accepted = models.BooleanField(null=True)
    requester_choice = models.CharField(max_length=15, choices=[('friend', 'Friend'), ('close_friend', 'Close Friend')], null=True)
    requestee_choice = models.CharField(max_length=15, choices=[('friend', 'Friend'), ('close_friend', 'Close Friend')], null=True)
    requester_update_past_posts = models.BooleanField(default=False)
    requestee_update_past_posts = models.BooleanField(default=False)

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
        ('close_friend', 'Close Friend'),
    )

    user1 = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name='connections_as_user1'
    )
    user2 = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name='connections_as_user2'
    )
    user1_choice = models.CharField(max_length=15, choices=CHOICES)
    user2_choice = models.CharField(max_length=15, choices=CHOICES)
    user1_upgrade_time = models.DateTimeField(null=True, blank=True)
    user2_upgrade_time = models.DateTimeField(null=True, blank=True)
    user1_update_past_posts = models.BooleanField(default=False)
    user2_update_past_posts = models.BooleanField(default=False)

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
            self.user1_update_past_posts, self.user2_update_past_posts = self.user2_update_past_posts, self.user1_update_past_posts
            self.user1_upgrade_time, self.user2_upgrade_time = self.user2_upgrade_time, self.user1_upgrade_time

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
    
    def user1_is_close_friend(self):
        """Check if user2 set user1 as 'close_friend'."""
        return self.user2_choice == 'close_friend'
    
    def user2_is_close_friend(self):
        """Check if user1 set user2 as 'close_friend'."""
        return self.user1_choice == 'close_friend'

    @transaction.atomic
    def update_friendship_level(self, user, new_choice, update_past_posts=False):
        current_time = timezone.now()
        
        # Confirm which user is updating their choice
        if user == self.user1:
            old_choice = self.user1_choice
            self.user1_choice = new_choice
            if new_choice == 'close_friend' and old_choice == 'friend':
                self.user1_upgrade_time = current_time
                self.user1_update_past_posts = update_past_posts
        elif user == self.user2:
            old_choice = self.user2_choice
            self.user2_choice = new_choice
            if new_choice == 'close_friend' and old_choice == 'friend':
                self.user2_upgrade_time = current_time
                self.user2_update_past_posts = update_past_posts
        
        self.save()


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


RELATIONSHIP_TYPE_CHOICES = (
    ('school_friend', 'School Friend'),
    ('coworker', 'Coworker'),
    ('family', 'Family'),
    ('online_friend', 'Online Friend'),
    ('club_community', 'Club/Community'),
    ('not_yet', 'Not Yet Met'),
    ('other', 'Other'),
)

EVALUATION_CONTEXT_CHOICES = (
    ('request', 'Friend Request Sent'),
    ('accept', 'Friend Request Accepted'),
)


class FriendEvaluation(AdoorTimestampedModel, SafeDeleteModel):
    evaluator = models.ForeignKey(
        get_user_model(), related_name='friend_evaluations_given', on_delete=models.CASCADE)
    evaluated_user = models.ForeignKey(
        get_user_model(), related_name='friend_evaluations_received', on_delete=models.CASCADE)
    friend_request = models.ForeignKey(
        FriendRequest, related_name='evaluations', on_delete=models.CASCADE, null=True, blank=True)
    context = models.CharField(max_length=10, choices=EVALUATION_CONTEXT_CHOICES)
    closeness = models.IntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    relationship_type = models.CharField(
        max_length=20, choices=RELATIONSHIP_TYPE_CHOICES, null=True, blank=True)
    relationship_type_detail = models.CharField(max_length=50, null=True, blank=True)
    skipped = models.BooleanField(default=False)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['evaluator', 'evaluated_user', 'friend_request'],
                condition=Q(deleted__isnull=True),
                name='unique_friend_evaluation',
            ),
        ]
        indexes = [
            models.Index(fields=['evaluator', 'skipped']),
        ]

    def __str__(self):
        return f'{self.evaluator} evaluated {self.evaluated_user} ({self.context})'

    @property
    def type(self):
        return self.__class__.__name__


SUBSCRIPTION_TYPE_CHOICES = (
    # Ver. W — granular check-in components
    ('battery', 'Battery'),
    ('mood', 'Mood'),
    ('thought', 'Thought'),
    ('song', 'Song'),
    ('mission_of_the_day', 'Mission of the day'),
    ('question_of_the_day', 'Question of the day'),
    ('photo_of_the_day', 'Photo of the day'),
    # Ver. Q — image+text post-style entities
    ('check_in', 'Check-in (Ver.Q)'),
    ('post', 'Post (Ver.Q)'),
)


class Subscription(AdoorTimestampedModel, SafeDeleteModel):
    subscriber = models.ForeignKey(get_user_model(), related_name='subscriptions', on_delete=models.CASCADE)
    subscribed_to = models.ForeignKey(get_user_model(), related_name='subscribed_by', on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    subscription_type = models.CharField(max_length=32, choices=SUBSCRIPTION_TYPE_CHOICES, null=True, blank=True)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['subscriber', 'subscribed_to', 'subscription_type'],
                condition=Q(deleted__isnull=True, subscription_type__isnull=False),
                name='unique_subscription_by_type',
            ),
            models.UniqueConstraint(
                fields=['subscriber', 'subscribed_to', 'content_type'],
                condition=Q(deleted__isnull=True, subscription_type__isnull=True),
                name='unique_subscription',
            ),
        ]

    def __str__(self):
        label = self.subscription_type or self.content_type
        return f'{self.subscriber} subscribed to {label} of {self.subscribed_to}'


class Interest(AdoorTimestampedModel, SafeDeleteModel):
    """Stores all chip selections across all 7 categories."""
    content = models.CharField(max_length=100)
    category = models.CharField(max_length=50, choices=CHIP_CATEGORY_CHOICES, default='hobbies_activities', blank=True)
    users = models.ManyToManyField(get_user_model(), related_name='user_interests', blank=True)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        indexes = [
            models.Index(fields=['content']),
            models.Index(fields=['category']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['content', 'category'],
                condition=Q(deleted__isnull=True),
                name='unique_interest_per_category',
            ),
        ]

    def __str__(self):
        return self.content


class Persona(AdoorTimestampedModel, SafeDeleteModel):
    """Kept for backward compatibility. New chips go into Interest with category."""
    content = models.CharField(max_length=100, unique=True)
    users = models.ManyToManyField(get_user_model(), related_name='user_personas', blank=True)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        indexes = [
            models.Index(fields=['content']),
        ]

    def __str__(self):
        return self.content


class CustomChip(AdoorTimestampedModel, SafeDeleteModel):
    """User-created custom chips. Max 5 per category per user, max 25 chars."""
    user = models.ForeignKey(get_user_model(), related_name='custom_chips', on_delete=models.CASCADE)
    text = models.CharField(max_length=25)
    category = models.CharField(max_length=50, choices=CHIP_CATEGORY_CHOICES)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        indexes = [
            models.Index(fields=['user', 'category']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['user', 'text', 'category'], name='unique_custom_chip_per_user'),
        ]

    def __str__(self):
        return f'{self.user.username}: {self.text} ({self.category})'


class DiscoverFeed(AdoorTimestampedModel):
    user = models.ForeignKey(get_user_model(), related_name='discover_feeds', on_delete=models.CASCADE)
    response = models.ForeignKey('qna.Response', related_name='discover_feed_items', on_delete=models.CASCADE, null=True, blank=True)
    note = models.ForeignKey('note.Note', related_name='discover_feed_items', on_delete=models.CASCADE, null=True, blank=True)
    
    # Override created_at to allow consistent batch timestamps
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    
    # Category to explain why this was recommended
    CATEGORY_CHOICES = (
        ('mutual_friends', 'Mutual Friends'),
        ('mutual_traits', 'Mutual Traits'),
        ('anonymous', 'Anonymous'),
        ('random', 'Random'),
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['-created_at', 'sort_order']
        indexes = [
            models.Index(fields=['user', '-created_at', 'sort_order']),
        ]

    def __str__(self):
        content_obj = self.response or self.note
        content_id = content_obj.id if content_obj else "?"
        return f"DiscoverFeed for {self.user.username}: {content_id} ({self.category})"


class DiscoverFeedMusic(AdoorTimestampedModel):
    user = models.ForeignKey(
        get_user_model(), related_name='discover_feed_music', on_delete=models.CASCADE
    )
    song = models.ForeignKey(
        'check_in.Song', related_name='discover_feed_music_items', on_delete=models.CASCADE
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)

    CATEGORY_CHOICES = (
        ('mutual_friends', 'Mutual Friends'),
        ('mutual_traits', 'Mutual Traits'),
        ('anonymous', 'Anonymous'),
        ('random', 'Random'),
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['-created_at', 'sort_order']
        indexes = [
            models.Index(fields=['user', '-created_at', 'sort_order']),
        ]

    def __str__(self):
        return f"DiscoverFeedMusic for {self.user.username}: {self.song.id} ({self.category})"


class AppSession(SafeDeleteModel):
    user = models.ForeignKey(
        "User",
        on_delete=models.CASCADE  # When user is soft deleted, app session is soft deleted as well
    )
    session_id = models.CharField(max_length=36, unique=True, default=uuid.uuid4)  # UUID + unique setting
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    last_touch_time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} - {self.session_id} ({self.start_time} ~ {self.end_time})"


@transaction.atomic
@receiver(post_save, sender=Connection)
def connection_removed(instance, **kwargs):
    if not instance.deleted:
        return

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


    # 3. No-op: chat rooms use FK pairs, no deactivation needed on unfriend

    # 4. Remove all subscriptions between the two users
    Subscription.objects.filter(
        Q(subscriber=user1, subscribed_to=user2) | Q(subscriber=user2, subscribed_to=user1)
    ).delete()


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
                                           message_en=f'{requester.username} has sent a friend request.',
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
        # requester_choice can be null for legacy FriendRequests created before validation was added
        requester_choice = instance.requester_choice or 'friend'
        requestee_choice = instance.requestee_choice or 'friend'
        Connection.objects.create(
            user1=requester,
            user2=requestee,
            user1_choice=requester_choice,
            user2_choice=requestee_choice,
            user1_update_past_posts=instance.requester_update_past_posts,
            user2_update_past_posts=instance.requestee_update_past_posts,
            user1_upgrade_time=timezone.now() if requester_choice == 'close_friend' else None,
            user2_upgrade_time=timezone.now() if requestee_choice == 'close_friend' else None,
        )

        # create chat room for new friends
        from chat.models import get_or_create_chat_room
        get_or_create_chat_room(requester, requestee)

        # auto-subscribe close friends to check-in updates (version_w only)
        if requester.current_ver == 'version_w':
            from adoorback.utils.content_types import get_check_in_type
            check_in_ct = get_check_in_type()
            default_types = ('battery', 'mood', 'thought', 'song')
            if requester_choice == 'close_friend':
                for stype in default_types:
                    Subscription.objects.get_or_create(
                        subscriber=requester, subscribed_to=requestee,
                        content_type=check_in_ct, subscription_type=stype,
                    )
            if requestee_choice == 'close_friend':
                for stype in default_types:
                    Subscription.objects.get_or_create(
                        subscriber=requestee, subscribed_to=requester,
                        content_type=check_in_ct, subscription_type=stype,
                    )

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
    2) send verification email
    '''
    if instance.deleted:
        return

    if created:
        # send notification
        from notification.models import Notification
        admin = User.objects.filter(is_superuser=True).first()
        if admin:
            noti = Notification.objects.create(user=instance,
                                               target=admin,
                                               origin=admin,
                                               message_ko=f"{instance.username}님, 보다 재밌는 후엠아이 이용을 위해 친구를 추가해보세요!",
                                               message_en=f"{instance.username}, add your friends for a better WIT experience!",
                                               redirect_url='/friends/explore')
            NotificationActor.objects.create(user=admin, notification=noti)

    if created and instance.email:
        email_manager.send_verification_email(instance)


@transaction.atomic
@receiver(post_save, sender=User)
def delete_old_profile_image(sender, instance, **kwargs):
    if instance.pk:
        if instance.profile_image:
            profile_images_dir = os.path.join(settings.MEDIA_ROOT, 'profile_images')
            current_image_name = os.path.basename(instance.profile_image.name)
            current_hash = current_image_name.split('_')[-1].split('.')[0]

            # Find all files in the format username_{hash}.png
            pattern = os.path.join(profile_images_dir, f'{instance.username}_*.png')
            existing_images = glob.glob(pattern)
            print(len(existing_images))

            for image_path in existing_images:
                image_name = os.path.basename(image_path)
                image_hash = image_name.split('_')[-1].split('.')[0]
                if image_hash != current_hash:
                    os.remove(image_path)  # Delete files with different hash values


@transaction.atomic
@receiver(post_save, sender=User)
def provision_wit_admin_rooms(created, instance, **kwargs):
    """On user signup, create the WIT Admin chat + 3 operator proxy rooms.

    See docs/superpowers/specs/2026-04-25-wit-admin-chat-hotfix-design.md.
    """
    if not created:
        return
    if instance.deleted:
        return
    if not instance.is_active:
        return

    # Lazy import to avoid circular: chat.wit_admin imports chat.models which can
    # transitively reach account.models.
    from chat.wit_admin import provision_user_rooms, ALL_OPERATOR_EMAILS, WIT_ADMIN_EMAIL, SYSTEM_BOT_USERNAME

    if (
        instance.email in ALL_OPERATOR_EMAILS
        or instance.email == WIT_ADMIN_EMAIL
        or instance.username == SYSTEM_BOT_USERNAME
    ):
        return

    try:
        provision_user_rooms(instance)
    except (LookupError, IntegrityError):
        # LookupError: Operator users not yet seeded.
        # IntegrityError: wit_admin email collision or other DB constraint.
        # Either way, silently skip; the management command
        # (seed_wit_admin_chats) will catch this user up on the next run.
        return

    from chat.wit_bot import ensure_wit_bot_room

    try:
        ensure_wit_bot_room(instance)
    except (LookupError, IntegrityError):
        # Bot user not yet seeded or DB collision — seed_wit_bot will heal.
        return


class VersionSwitchRequest(AdoorTimestampedModel, SafeDeleteModel):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    user = models.ForeignKey(
        get_user_model(), related_name='version_switch_requests', on_delete=models.CASCADE)
    from_version = models.CharField(max_length=20, choices=VERSION_CHOICES)
    to_version = models.CharField(max_length=20, choices=VERSION_CHOICES)
    reason = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(
        get_user_model(), related_name='+', on_delete=models.SET_NULL, null=True, blank=True)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                condition=Q(status='pending') & Q(deleted__isnull=True),
                name='unique_pending_version_switch_request'),
        ]
        indexes = [
            models.Index(fields=['-created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} {self.from_version}→{self.to_version} ({self.status})'

    @property
    def type(self):
        return self.__class__.__name__
