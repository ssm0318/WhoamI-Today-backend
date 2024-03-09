import datetime
from django.db import models, transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.db.models import Q

from account.models import FriendGroup
from comment.models import Comment
from like.models import Like
from reaction.models import Reaction
from adoorback.models import AdoorModel, AdoorTimestampedModel
from adoorback.utils.helpers import wrap_content
from notification.models import Notification, NotificationActor

from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE, HARD_DELETE
from safedelete.managers import SafeDeleteManager

User = get_user_model()


class QuestionManager(SafeDeleteManager):

    def admin_questions_only(self, **kwargs):
        return self.filter(is_admin_question=True, **kwargs)

    def custom_questions_only(self, **kwargs):
        return self.filter(is_admin_question=False, **kwargs)

    def daily_questions(self, **kwargs):
        return self.filter(selected_dates__contains=[datetime.date.today()], **kwargs)

    def date_questions(self, date, **kwargs):
        return self.filter(selected_dates__contains=[date], **kwargs)


class Question(AdoorModel, SafeDeleteModel):
    author = models.ForeignKey(User, related_name='question_set', on_delete=models.CASCADE)

    selected_date = models.DateTimeField(null=True)  # obsolete
    selected_dates = ArrayField(models.DateField(), blank=True, default=list)
    selected = models.BooleanField(default=False)
    is_admin_question = models.BooleanField(default=True)

    question_targetted_notis = GenericRelation(Notification,
                                               content_type_field='target_type',
                                               object_id_field='target_id')
    question_originated_notis = GenericRelation(Notification,
                                                content_type_field='origin_type',
                                                object_id_field='origin_id')

    objects = QuestionManager()

    _safedelete_policy = SOFT_DELETE_CASCADE

    @property
    def type(self):
        return self.__class__.__name__

    @property
    def last_selected_date(self):
        return self.selected_dates[-1] if self.selected_dates else None

    class Meta:
        ordering = ['-id']


class Response(AdoorModel, SafeDeleteModel):
    author = models.ForeignKey(User, related_name='response_set', on_delete=models.CASCADE)
    question = models.ForeignKey(Question, related_name='response_set', on_delete=models.CASCADE)

    response_comments = GenericRelation(Comment)
    # to be deleted
    response_likes = GenericRelation(Like)
    response_reactions = GenericRelation(Reaction)
    readers = models.ManyToManyField(User, related_name='read_responses')

    share_everyone = models.BooleanField(default=False, blank=True)
    share_groups = models.ManyToManyField(FriendGroup, related_name='shared_responses', blank=True)
    share_friends = models.ManyToManyField(User, related_name='shared_responses', blank=True)

    response_targetted_notis = GenericRelation(Notification,
                                               content_type_field='target_type',
                                               object_id_field='target_id')
    response_originated_notis = GenericRelation(Notification,
                                                content_type_field='origin_type',
                                                object_id_field='origin_id')

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        ordering = ['-id']
        indexes = [
            models.Index(fields=['-id']),
        ]

    @property
    def type(self):
        return self.__class__.__name__

    # to be deleted
    @property
    def liked_user_ids(self):
        return self.response_likes.values_list('user_id', flat=True)

    @property
    def participants(self):
        return self.response_comments.values_list('author_id', flat=True).distinct()

    @property
    def reader_ids(self):
        return self.readers.values_list('id', flat=True)

    def is_audience(self, user):
        if self.author == user:
            return True

        if self.share_everyone:
            return True

        if not User.are_friends(self.author, user):
            return False

        if self.share_groups.filter(friends=user).exists():
            return True

        if self.share_friends.filter(pk=user.pk).exists():
            return True

        return False


class ResponseRequest(AdoorTimestampedModel, SafeDeleteModel):
    requester = models.ForeignKey(User, related_name='sent_response_request_set', on_delete=models.CASCADE)
    requestee = models.ForeignKey(User, related_name='received_response_request_set', on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    message = models.TextField(blank=True, null=True)

    response_request_targetted_notis = GenericRelation('notification.Notification',
                                                       content_type_field='target_type',
                                                       object_id_field='target_id')
    response_request_originated_notis = GenericRelation('notification.Notification',
                                                        content_type_field='origin_type',
                                                        object_id_field='origin_id')

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['requester', 'requestee', 'question'], condition=Q(deleted__isnull=True),
                name='unique_response_request'),
        ]
        indexes = [
            models.Index(fields=['-id']),
        ]

    def __str__(self):
        return f'{self.requester} sent ({self.question}) to {self.requestee}'

    @property
    def type(self):
        return self.__class__.__name__


@transaction.atomic
@receiver(post_save, sender=ResponseRequest)
def create_response_request_noti(instance, created, **kwargs):
    if instance.deleted:
        return

    if not created:
        return

    target = instance
    origin = instance.question
    requester = instance.requester
    requestee = instance.requestee

    content_preview = wrap_content(origin.content)

    if requester.id in requestee.user_report_blocked_ids:  # do not create notification from/for blocked user
        return
    redirect_url = f'/questions/{origin.id}/short-answer'
    Notification.objects.create_or_update_notification(user=requestee, actor=requester,
                                                       origin=origin, target=target, noti_type="response_request_noti",
                                                       redirect_url=redirect_url, content_preview=content_preview)


@transaction.atomic
@receiver(post_save, sender=Response)
def create_request_answered_noti(instance, created, **kwargs):
    if instance.deleted:
        return

    if not created:  # response edit만 해줬거나 익명으로만 공개한 경우
        return

    author_id = instance.author.id
    question_id = instance.question.id
    target = instance
    origin = instance
    actor = instance.author
    related_requests = ResponseRequest.objects.filter(
        requestee_id=author_id, question_id=question_id)
    redirect_url = f'/responses/{instance.id}'

    content_preview = wrap_content(origin)

    for request in related_requests:
        user = request.requester
        if actor.id in user.user_report_blocked_ids:  # do not create notification from/for blocked user
            return
        message_ko = f'{actor.username}님이 회원님이 보낸 질문에 답했습니다: "{content_preview}"'
        message_en = f'{actor.username} has responded to your question: "{content_preview}"'
        noti = Notification.objects.create(user=user,
                                           origin=origin, target=target,
                                           message_ko=message_ko, message_en=message_en, redirect_url=redirect_url)
        NotificationActor.objects.create(user=actor, notification=noti)


@transaction.atomic
@receiver(post_save, sender=Response)
def add_author_to_readers(instance, created, **kwargs):
    if not created:
        return
    instance.readers.add(instance.author)
    instance.save()
