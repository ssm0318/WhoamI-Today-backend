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
from notification.helpers import construct_message
from notification.models import Notification, NotificationActor

from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE
from safedelete.managers import SafeDeleteManager

User = get_user_model()


class Reaction(AdoorTimestampedModel, SafeDeleteModel):
    COMPONENT_CHOICES = [
        ('battery', 'Battery'),
        ('mood', 'Mood'),
        ('thought', 'Thought'),
        ('song', 'Song'),
    ]

    user = models.ForeignKey(User, related_name='reaction_set', on_delete=models.CASCADE)
    emoji = models.CharField(blank=False, null=False, max_length=20)
    component = models.CharField(
        max_length=20,
        choices=COMPONENT_CHOICES,
        null=True,
        blank=True,
    )

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.IntegerField()
    target = GenericForeignKey('content_type', 'object_id')

    reaction_targetted_notis = GenericRelation(Notification,
                                               content_type_field='target_type',
                                               object_id_field='target_id')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'emoji', 'content_type', 'object_id'],
                condition=Q(deleted__isnull=True, component__isnull=True),
                name='unique_reaction_no_component',
            ),
            models.UniqueConstraint(
                fields=['user', 'emoji', 'content_type', 'object_id', 'component'],
                condition=Q(deleted__isnull=True, component__isnull=False),
                name='unique_reaction_with_component',
            ),
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

    if origin.type == 'CheckIn':
        component = instance.component
        redirect_url = '/update'
        message_ko, message_en = construct_message(
            'reaction_checkin_noti',
            actor.username + "님", None,
            actor.username, None,
            1, None, None,
            emoji=target.emoji, component=component,
        )
        noti = Notification.objects.create(
            user=user, origin=origin, target=target,
            message_ko=message_ko, message_en=message_en,
            redirect_url=redirect_url,
        )
        NotificationActor.objects.create(user=actor, notification=noti)
    elif origin.type == 'Comment':
        content = wrap_content(origin.content)
        # reply인 경우 origin.target.target이 root post
        if origin.target.type == 'Comment':
            post = origin.target.target
        else:
            post = origin.target

        # Skip notification for private comments on entries that are no longer pinned
        # or where the recipient is no longer a friend of the entry owner.
        # user == post.owner (entry owner replied and got reacted to) is always valid.
        if (origin.is_private
                and post.type == 'CheckInComponentEntry'
                and user != post.owner
                and (not post.is_pinned or not post.owner.is_connected(user))):
            return

        if post.type == 'CheckInComponentEntry':
            if user == post.owner:
                redirect_url = f'/update?tab=pinned&highlight={post.id}'
            else:
                redirect_url = f'/users/{post.owner.username}/check-in/pinned?highlight={post.id}'
        elif post.type == 'CheckInPost':
            redirect_url = f'/users/{post.author.username}/snippets/pinned?highlight={post.id}'
        else:
            redirect_url = f'/{post.type.lower()}s/{post.id}'

        Notification.objects.create_or_update_notification(
            user=user, actor=actor, origin=origin, target=target,
            noti_type='reaction_comment_noti', redirect_url=redirect_url,
            content_en=content, content_ko=content,
        )
    else:
        is_mission_note = origin.type == 'Note' and getattr(origin, 'share_type', None) == 'mission'
        if is_mission_note:
            noti_type = "reaction_mission_note_noti"
            content_en = content_ko = ''
        else:
            noti_type = "reaction_response_noti"
            content_en = content_ko = wrap_content(origin.content)
        redirect_url = f'/{origin.type.lower()}s/{origin.id}'
        Notification.objects.create_or_update_notification(
            user=user, actor=actor, origin=origin, target=target,
            noti_type=noti_type, redirect_url=redirect_url,
            content_en=content_en, content_ko=content_ko,
            emoji=target.emoji,
        )
