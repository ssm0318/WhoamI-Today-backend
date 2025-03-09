from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from adoorback.models import AdoorTimestampedModel
from adoorback.utils.content_types import get_response_request_type, get_question_type
from notification.helpers import find_like_noti, construct_message

from firebase_admin.messaging import Message
from firebase_admin.messaging import Notification as FirebaseNotification
from custom_fcm.models import CustomFCMDevice
from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE, HARD_DELETE
from safedelete.managers import SafeDeleteManager


class NotificationManager(SafeDeleteManager):

    def visible_only(self, **kwargs):
        return self.filter(is_visible=True, **kwargs)

    def unread_only(self, **kwargs):
        return self.filter(is_read=False, **kwargs)

    def admin_only(self, **kwargs):
        admin_users = get_user_model().objects.filter(is_superuser=True)
        return self.filter(actors__in=admin_users, **kwargs)

    def create_or_update_notification(self, actor, user, origin, target, noti_type, redirect_url, content_en, content_ko,
                                      emoji=None):
        noti_to_update = None

        if target.type == "Like":
            noti_to_update = find_like_noti(user, origin, noti_type)
            if noti_to_update and hasattr(target, 'deleted') and target.deleted:
                # need to hard delete because if soft deleted, NotificationActor is still accessible through notification.actors field (MTM)
                NotificationActor.objects.filter(user=actor, notification=noti_to_update).delete(force_policy=HARD_DELETE)
                actors = noti_to_update.actors.order_by('-notificationactor__created_at')  # make the most recent actor come first in the notification message
                N = actors.count()

                if N == 0:
                    noti_to_update.delete()
                    return

                first_actor = actors.first()
                second_actor = actors[1] if actors.count() > 1 else None
                updated_message_ko, updated_message_en = construct_message(
                    noti_type,
                    first_actor.username + "님",
                    second_actor.username + "님" if second_actor else None,
                    first_actor.username,
                    second_actor.username if second_actor else None,
                    N,
                    content_en,
                    content_ko,
                    emoji
                )
                
                noti_to_update.message_ko = updated_message_ko
                noti_to_update.message_en = updated_message_en
                noti_to_update.save()

                print(noti_to_update.message_ko)
                print(noti_to_update.message_en)
                return
        elif target.type == "ResponseRequest":
            noti_to_update = Notification.objects.filter(user=user,
                                                         origin_id=target.question.id, origin_type=get_question_type(),
                                                         target_type=get_response_request_type()).first()
        elif target.type == "Reaction":
            notis = Notification.objects.filter(user=user, origin_id=origin.id,
                                                origin_type=ContentType.objects.get_for_model(origin),
                                                target_type=ContentType.objects.get_for_model(target))
            if notis.count() > 0:
                for noti in notis:
                    if noti.target.emoji == emoji:
                        noti_to_update = noti
                        break

        if noti_to_update:
            actors = noti_to_update.actors.order_by('-notificationactor__created_at')
            N = actors.count()
            new_actor = actors.first()
            updated_message_ko, updated_message_en = construct_message(noti_type,
                                                                       actor.username + "님",
                                                                       new_actor.username + "님",
                                                                       actor.username,
                                                                       new_actor.username,
                                                                       N + 1,
                                                                       content_en,
                                                                       content_ko,
                                                                       emoji)

            noti_to_update.message_ko = updated_message_ko
            noti_to_update.message_en = updated_message_en
            noti_to_update.is_visible = True
            noti_to_update.is_read = False
            NotificationActor.objects.create(user=actor, notification=noti_to_update)
            noti_to_update.notification_updated_at = timezone.now()
            noti_to_update.save()
            print(noti_to_update.message_ko)
            print(noti_to_update.message_en)
        else:
            message_ko, message_en = construct_message(noti_type, actor.username + "님", None,
                                                       actor.username, None, 1, content_en, content_ko, emoji)
            noti = Notification.objects.create(user=user, origin=origin, target=target, redirect_url=redirect_url,
                                               message_ko=message_ko, message_en=message_en)
            NotificationActor.objects.create(user=actor, notification=noti)
            print(noti.message_ko)
            print(noti.message_en)


def default_user():
    return get_user_model().objects.filter(is_superuser=True).first()


class Notification(AdoorTimestampedModel, SafeDeleteModel):
    user = models.ForeignKey('account.User', related_name='received_noti_set',
                             on_delete=models.CASCADE, null=True)
    actors = models.ManyToManyField('account.User', through='NotificationActor', related_name='sent_notification_set')

    # target: notification을 발생시킨 직접적인 원인(?)
    target_type = models.ForeignKey(ContentType,
                                    on_delete=models.PROTECT,
                                    null=True,
                                    related_name='targetted_noti_set')
    target_id = models.IntegerField(null=True)
    target = GenericForeignKey('target_type', 'target_id')

    # origin: target의 target (target의 target이 없을 경우 target의 직접적인 발생지)
    origin_type = models.ForeignKey(ContentType,
                                    on_delete=models.SET_NULL,
                                    null=True,
                                    related_name='origin_noti_set')
    origin_id = models.IntegerField(null=True)
    origin = GenericForeignKey('origin_type', 'origin_id')

    # redirect: target의 근원지(?), origin != redirect_url의 모델일 경우가 있음 (e.g. reply)
    redirect_url = models.CharField(max_length=150)
    message = models.CharField(max_length=300)

    is_visible = models.BooleanField(default=True)
    is_read = models.BooleanField(default=False)

    notification_updated_at = models.DateTimeField(auto_now=True, null=True)

    objects = NotificationManager()

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        ordering = ['-notification_updated_at']
        indexes = [
            models.Index(fields=['-notification_updated_at']),
        ]

    def save(self, *args, **kwargs):
        if not self.pk:
            self.notification_updated_at = self.created_at
        super().save(*args, **kwargs)

    def __str__(self):
        return f"@{self.user} {self.message}"


class NotificationActor(AdoorTimestampedModel, SafeDeleteModel):
    user = models.ForeignKey('account.User', on_delete=models.CASCADE)
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"actor {self.user} of notification \"{self.notification.message}\" (id: {self.notification.id})"


@receiver(post_save, sender=Notification)
def send_firebase_notification(created, instance, **kwargs):
    if not created:
        return
    
    devices = CustomFCMDevice.objects.filter(user_id=instance.user.id, active=True)

    for device in devices:
        if device.language == 'ko':
            body = instance.message_ko
        else:
            body = instance.message_en
        
        message = Message(
            notification=FirebaseNotification(
                title='WhoAmI Today',
                body=body
            ),
            data={
                'message_en': instance.message_en,
                'message_ko': instance.message_ko,
                'url': instance.redirect_url,
                'tag': str(instance.id),
                'type': 'new',
                'content-available': '1',  # for ios silent notification
                'priority': 'high',  # for android
            }
        )

        try:
            device.send_message(message)
            print(f"Notification sent to user {instance.user.id} in {device.language}")
        except Exception as e:
            print(f"Error while sending firebase notification to device {device.id}:", e)

@receiver(post_save, sender=Notification)
def cancel_firebase_notification(sender, instance, **kwargs):
    if not instance.deleted:
        return

    message = Message(
        data={
            'body': '삭제된 알림입니다.',
            'url': '/home',
            'tag': str(instance.id),
            'type': 'cancel',
        }
    )

    try:
        CustomFCMDevice.objects.filter(user_id=instance.user.id).send_message(message, False)
    except Exception as e:
        print("error while canceling firebase notification: ", e)
