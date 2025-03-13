from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import models, transaction
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.auth import get_user_model
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db import IntegrityError
from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE
from safedelete.managers import SafeDeleteManager

from account.models import User
from adoorback.models import AdoorModel
from adoorback.utils.helpers import wrap_content
from adoorback.utils.content_types import get_comment_type, get_generic_relation_type
from content_report.models import ContentReport
from like.models import Like
from notification.models import Notification, NotificationActor
from user_tag.models import UserTag
from utils.helpers import parse_user_tag_from_content


User = get_user_model()


class CommentManager(SafeDeleteManager):

    def comments_only(self, **kwargs):
        return self.exclude(content_type=get_comment_type(), **kwargs)

    def replies_only(self, **kwargs):
        return self.filter(content_type=get_comment_type(), **kwargs)


class Comment(AdoorModel, SafeDeleteModel):
    author = models.ForeignKey(User, related_name='comment_set', on_delete=models.CASCADE)
    is_private = models.BooleanField(default=False)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.IntegerField()
    target = GenericForeignKey('content_type', 'object_id')

    replies = GenericRelation('self')
    comment_likes = GenericRelation(Like)
    comment_user_tags = GenericRelation(UserTag)

    comment_targetted_notis = GenericRelation(Notification,
                                              content_type_field='target_type',
                                              object_id_field='target_id')
    comment_originated_notis = GenericRelation(Notification,
                                               content_type_field='origin_type',
                                               object_id_field='origin_id')

    objects = CommentManager()

    _safedelete_policy = SOFT_DELETE_CASCADE

    @property
    def type(self):
        return self.__class__.__name__

    @property
    def liked_user_ids(self):
        return self.comment_likes.values_list('user_id', flat=True)

    @property
    def participants(self):
        return self.replies.values_list('author_id', flat=True).distinct()

    def is_reply(self):
        return isinstance(self.target, Comment)


@receiver(post_save, sender=Comment)
def create_noti(instance, created, **kwargs):
    if not created:  # do not run when triggered by soft delete or undelete
        return

    origin_author = instance.target.author
    actor = instance.author
    origin = instance.target
    target = instance

    content_preview = wrap_content(instance.content)

    # if is_reply
    if origin.type == 'Comment':
        redirect_url = f'/{origin.target.type.lower()}s/{origin.target.id}'
        # send a notification to the author of the origin comment
        if origin_author == actor:
            pass
        elif actor.id in origin_author.user_report_blocked_ids:
            pass
        else:
            noti = Notification.objects.create(user=origin_author,
                                               origin_id=origin.id,
                                               origin_type=get_generic_relation_type(origin.type),
                                               target_id=target.id,
                                               target_type=get_comment_type(),
                                               message_ko=f'{actor.username}이 회원님의 댓글에 답글을 남겼습니다: "{content_preview}"',
                                               message_en=f'{actor.username} has replied to your comment: "{content_preview}"',
                                               redirect_url=redirect_url)
            NotificationActor.objects.create(user=actor, notification=noti)

        # send a notification to the author of the qna where the origin comment commented
        post_author = origin.target.author
        if post_author == origin_author:
            pass
        elif post_author == actor:
            pass
        elif actor.id in post_author.user_report_blocked_ids:
            pass
        else:
            noti = Notification.objects.create(user=post_author,
                                               origin_id=origin.id,
                                               origin_type=get_generic_relation_type(origin.type),
                                               target_id=target.id,
                                               target_type=get_comment_type(),
                                               message_ko=f'회원님의 답변에 달린 댓글에 새로운 답글이 달렸습니다: "{content_preview}"',
                                               message_en=f'Someone replied to a comment on your response: "{content_preview}"',
                                               redirect_url=redirect_url)
            NotificationActor.objects.create(user=actor, notification=noti)

        # send notifications to participants of the origin comment
        if not instance.is_private:
            for participant_id in origin.participants:
                if participant_id == origin_author.id:
                    continue
                if participant_id == post_author.id:
                    continue
                if participant_id == actor.id:
                    continue
                participant = User.objects.get(id=participant_id)
                if actor.id in participant.user_report_blocked_ids:
                    continue
                content_type = ContentType.objects.get_for_model(origin).model
                if (content_type, origin.id) in participant.content_report_blocked_model_ids:
                    return
                noti = Notification.objects.create(user=participant,
                                                origin_id=origin.id,
                                                origin_type=get_generic_relation_type(origin.type),
                                                target_id=target.id,
                                                target_type=get_comment_type(),
                                                message_ko=f'회원님이 답글을 단 댓글에 새로운 답글이 달렸습니다: "{content_preview}"',
                                                message_en=f'Someone replied to a comment you responded to: "{content_preview}"',
                                                redirect_url=redirect_url)
                NotificationActor.objects.create(user=actor, notification=noti)

    # if not reply
    else:
        redirect_url = f'/{origin.type.lower()}s/{origin.id}'
        # send a notification to the author of the origin qna
        origin_target_name_ko = '게시글' if origin.type == 'Note' else '답변'
        origin_target_name_en = 'post' if origin.type == 'Note' else 'response'
        if origin_author == actor:
            pass
        elif actor.id in origin_author.user_report_blocked_ids:
            pass
        else:
            noti = Notification.objects.create(user=origin_author,
                                               origin_id=origin.id,
                                               origin_type=get_generic_relation_type(origin.type),
                                               target_id=target.id,
                                               target_type=get_comment_type(),
                                               message_ko=f'{actor.username}님이 회원님의 {origin_target_name_ko}에 댓글을 남겼습니다: "{content_preview}"',
                                               message_en=f'{actor.username} has commented on your {origin_target_name_en}: "{content_preview}"',
                                               redirect_url=redirect_url)
            NotificationActor.objects.create(user=actor, notification=noti)

        # send notifications to participants of the origin qna
        if not instance.is_private:
            for participant_id in origin.participants:
                if participant_id == origin_author.id:
                    continue
                if participant_id == actor.id:
                    continue
                participant = User.objects.get(id=participant_id)
                if actor.id in participant.user_report_blocked_ids:
                    continue
                content_type = ContentType.objects.get_for_model(origin).model
                if (content_type, origin.id) in participant.content_report_blocked_model_ids:
                    return
                noti = Notification.objects.create(user=participant,
                                                origin_id=origin.id,
                                                origin_type=get_generic_relation_type(origin.type),
                                                target_id=target.id,
                                                target_type=get_comment_type(),
                                                message_ko=f'회원님이 댓글을 단 {origin_target_name_ko}에 새로운 댓글이 달렸습니다: "{content_preview}"',
                                                message_en=f'A new comment was added to the {origin_target_name_en} you commented on: "{content_preview}"',
                                                redirect_url=redirect_url)
                NotificationActor.objects.create(user=actor, notification=noti)


@transaction.atomic
@receiver(post_save, sender=Comment)
def create_user_tag(instance, **kwargs):
    content = instance.content
    tagging_user = instance.author
    object_id = instance.id
    content_type = get_generic_relation_type(instance.type)

    tagged_users, word_indices = parse_user_tag_from_content(content)

    words = content.split(' ')
    for i, tagged_user in enumerate(tagged_users):
        tagged_username = tagged_user.username
        word_idx = word_indices[i]
        try:
            offset = sum([len(w) for w in words[:word_idx]]) + word_idx + 1  # length of words + spaces + '@'
            UserTag.objects.create(tagging_user_id=tagging_user.id, tagged_user_id=tagged_user.id,
                                   object_id=object_id, content_type=content_type,
                                   offset=offset, length=len(tagged_username), username_str=tagged_username)
        except IntegrityError as e:
            constraint_failed = False
            for arg in e.args:
                if 'constraint' in arg:
                    constraint_failed = True
            if constraint_failed:
                continue
            else:
                print("error creating UserTag: ", e.args)
