from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.db.models import Q
from django.utils import timezone
from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE
from safedelete.managers import SafeDeleteManager

from account.models import Subscription, Connection
from adoorback.models import AdoorModel, AdoorTimestampedModel
from adoorback.utils.helpers import wrap_content
from comment.models import Comment
from content_report.models import ContentReport
from like.models import Like
from notification.models import Notification, NotificationActor
from reaction.models import Reaction

User = get_user_model()


class QuestionManager(SafeDeleteManager):

    def admin_questions_only(self, **kwargs):
        return self.filter(is_admin_question=True, **kwargs)

    def custom_questions_only(self, **kwargs):
        return self.filter(is_admin_question=False, **kwargs)

    def daily_questions(self, user, **kwargs):
        try:
            tz = ZoneInfo(user.timezone)
        except (ZoneInfoNotFoundError, AttributeError):
            tz = ZoneInfo('America/Los_Angeles')

        user_today = timezone.now().astimezone(tz).date()
        return self.filter(selected_dates__contains=[user_today], **kwargs)

    def date_questions(self, date, **kwargs):
        return self.filter(selected_dates__contains=[date], **kwargs)


class Question(AdoorModel, SafeDeleteModel):
    author = models.ForeignKey(User, related_name='question_set', on_delete=models.CASCADE)

    selected_date = models.DateTimeField(null=True, blank=True)  # obsolete
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
    visibility = ArrayField(
        models.CharField(max_length=20),
        blank=True,
        default=list
    )

    response_comments = GenericRelation(Comment)
    # to be deleted
    response_likes = GenericRelation(Like)
    response_reactions = GenericRelation(Reaction)
    readers = models.ManyToManyField(User, related_name='read_responses')
    is_edited = models.BooleanField(default=False)

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

    def save(self, *args, **kwargs):
        if self.pk is not None:  # not when created
            original = Response.objects.get(pk=self.pk)
            if original.content != self.content:
                self.is_edited = True
        super().save(*args, **kwargs)

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

    @property
    def reactions(self):
        from django.contrib.contenttypes.models import ContentType
        response_content_type = ContentType.objects.get_for_model(self)
        return Reaction.objects.filter(content_type=response_content_type, object_id=self.id)

    def is_audience(self, user):
        content_type = ContentType.objects.get_for_model(self)
        if ContentReport.objects.filter(user=user, content_type=content_type, object_id=self.pk).exists():
            return False

        if self.author.id in user.user_report_blocked_ids:
            return False

        if self.author == user:
            return True
            
        is_close_friend = user.is_close_friend(self.author)
        is_friend = Connection.objects.filter(
            (models.Q(user1=self.author) & models.Q(user2=user)) | 
            (models.Q(user1=user) & models.Q(user2=self.author))
        ).exists()
        is_following = user.is_following(self.author)

        # Check Close Friend
        if is_close_friend:
            # Upgrade logic for close friends
            connection = Connection.get_connection_between(self.author, user)
            if connection:  # Should exist if close friend
                if self.author == connection.user1:
                    update_past_posts = connection.user1_update_past_posts
                    upgrade_time = connection.user1_upgrade_time
                else:
                    update_past_posts = connection.user2_update_past_posts
                    upgrade_time = connection.user2_upgrade_time

                can_see_as_cf = False
                if update_past_posts:
                    can_see_as_cf = True
                elif upgrade_time is None:
                    can_see_as_cf = True
                elif self.created_at > upgrade_time:
                    can_see_as_cf = True
                
                if can_see_as_cf and 'close_friends' in self.visibility:
                    return True

        # Check Friend (Mutually Exclusive: Not Close Friend)
        if is_friend and not is_close_friend:
            if 'friends' in self.visibility:
                return True

        # Check Follower (Mutually Exclusive: Not Connected)
        if is_following and not is_friend:
             if 'follower' in self.visibility:
                return True

        # Check Public (Mutually Exclusive: Not Connected, Not Following)
        if not is_friend and not is_following:
            if 'public' in self.visibility:
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

    content_en = wrap_content(origin.content_en)
    content_ko = wrap_content(origin.content_ko)

    if requester.id in requestee.user_report_blocked_ids:  # do not create notification from/for blocked user
        return
    redirect_url = f'/questions/{origin.id}/new'
    Notification.objects.create_or_update_notification(user=requestee, actor=requester,
                                                       origin=origin, target=target, noti_type="response_request_noti",
                                                       redirect_url=redirect_url, content_en=content_en, content_ko=content_ko)


@transaction.atomic
@receiver(post_save, sender=Response)
def create_request_answered_noti(instance, created, **kwargs):
    if instance.deleted:
        return

    if not created:  # Only edited response or published anonymously
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
        if not Response.is_audience(instance, user):
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


@receiver(post_save, sender=Response)
def send_notifications_to_subscribers(sender, instance, created, **kwargs):
    if not created:
        return

    author = instance.author
    response_content_type = ContentType.objects.get_for_model(Response)
    
    subscribers = Subscription.objects.filter(
        subscribed_to=author,
        content_type=response_content_type,
    ).values_list('subscriber', flat=True)

    for subscriber_id in subscribers:
        subscriber = get_user_model().objects.get(id=subscriber_id)
        
        noti = Notification.objects.create(
            user=subscriber,
            origin=instance,
            target=instance,
            message_ko=f'{author.username}님이 새 답변을 작성했습니다.',
            message_en=f'{author.username} has posted a new response.',
            redirect_url=f'/responses/{instance.id}'
        )
        NotificationActor.objects.create(user=author, notification=noti)
