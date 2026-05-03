import threading
import traceback

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from adoorback.models import AdoorTimestampedModel
from adoorback.utils.content_types import get_response_request_type, get_question_type
from adoorback.utils.alerts import send_msg_to_slack
from notification.helpers import find_like_noti, construct_message

from firebase_admin.messaging import Message
from firebase_admin._messaging_utils import (
    UnregisteredError, WebpushConfig, WebpushNotification,
    APNSConfig, APNSPayload, Aps, AndroidConfig, AndroidNotification,
)
from custom_fcm.models import CustomFCMDevice
from safedelete.models import SafeDeleteModel
from safedelete.models import SOFT_DELETE_CASCADE, HARD_DELETE
from safedelete.managers import SafeDeleteManager


def _should_push_synchronously():
    """Force synchronous Firebase push in test runners so existing mocks +
    assertions work without timing races. The settings flag lets prod opt back
    in if we ever need to (e.g. for one-off scripts)."""
    if getattr(settings, 'FIREBASE_PUSH_SYNCHRONOUS', False):
        return True
    import sys
    return 'test' in sys.argv or 'pytest' in sys.modules


def _push_firebase_async(instance):
    """Fire-and-forget Firebase push so it doesn't block the request thread.

    Each device.send_message() is a synchronous HTTP call to Firebase that can
    take 100-500ms; chained per-device this dominates chat-write latency. A
    daemon thread keeps the process able to exit cleanly. Errors inside
    notify_firebase are already swallowed (logged + Slack alert), so dropping
    the exception path here is fine.
    """
    if _should_push_synchronously():
        notify_firebase(instance)
        return
    threading.Thread(target=notify_firebase, args=(instance,), daemon=True).start()


class NotificationManager(SafeDeleteManager):

    def visible_only(self, **kwargs):
        return self.filter(is_visible=True, **kwargs)

    def unread_only(self, **kwargs):
        return self.filter(is_read=False, **kwargs)

    def admin_only(self, **kwargs):
        admin_users = get_user_model().objects.filter(is_superuser=True)
        return self.filter(actors__in=admin_users, **kwargs)

    def create_or_update_notification(self, actor, user, origin, target, noti_type, redirect_url, content_en, content_ko,
                                      emoji=None, component=None):
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
                noti_to_update._skip_push = True
                noti_to_update.save()
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
                    if emoji is None:
                        # 댓글 리액션: 이모지 상관없이 하나로 합침
                        noti_to_update = noti
                        break
                    elif noti.target.emoji == emoji and noti.target.component == component:
                        noti_to_update = noti
                        break

        if noti_to_update:
            # 이미 같은 유저가 actor로 등록돼있으면 중복 추가하지 않음
            if noti_to_update.actors.filter(id=actor.id).exists():
                return

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
                                                                       emoji,
                                                                       component)

            noti_to_update.message_ko = updated_message_ko
            noti_to_update.message_en = updated_message_en
            noti_to_update.is_visible = True
            noti_to_update.is_read = False
            NotificationActor.objects.create(user=actor, notification=noti_to_update)
            noti_to_update.notification_updated_at = timezone.now()
            noti_to_update.save()
        else:
            message_ko, message_en = construct_message(noti_type, actor.username + "님", None,
                                                       actor.username, None, 1, content_en, content_ko, emoji, component)
            noti = Notification.objects.create(user=user, origin=origin, target=target, redirect_url=redirect_url,
                                               message_ko=message_ko, message_en=message_en)
            NotificationActor.objects.create(user=actor, notification=noti)

    def find_recent_message(self, user, actor):
        cutoff = timezone.now() - timezone.timedelta(minutes=5)
        return self.filter(
            user=user,
            actors__in=[actor],
            target_type__model='message',
            is_read=False,
            notification_updated_at__gte=cutoff
        ).order_by('-notification_updated_at').first()


def default_user():
    return get_user_model().objects.filter(is_superuser=True).first()


class Notification(AdoorTimestampedModel, SafeDeleteModel):
    user = models.ForeignKey('account.User', related_name='received_noti_set',
                             on_delete=models.CASCADE, null=True)
    actors = models.ManyToManyField('account.User', through='NotificationActor', related_name='sent_notification_set')

    # target: direct cause that triggered the notification
    target_type = models.ForeignKey(ContentType,
                                    on_delete=models.PROTECT,
                                    null=True,
                                    related_name='targetted_noti_set')
    target_id = models.IntegerField(null=True)
    target = GenericForeignKey('target_type', 'target_id')

    # origin: target's target (if target's target doesn't exist, the direct source of target)
    origin_type = models.ForeignKey(ContentType,
                                    on_delete=models.SET_NULL,
                                    null=True,
                                    related_name='origin_noti_set')
    origin_id = models.IntegerField(null=True)
    origin = GenericForeignKey('origin_type', 'origin_id')

    # redirect: target's origin source, there are cases where origin != redirect_url's model (e.g. reply)
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


def get_notification_tag(instance):
    """Return a tag that groups related push notifications so newer ones replace older ones.

    Same tag → the service worker replaces the previous notification instead of stacking.
    """
    target_model = instance.target_type.model if instance.target_type else None
    origin_model = instance.origin_type.model if instance.origin_type else None

    if target_model == 'message':
        if instance.origin_id:
            return f"chat_message_{instance.origin_id}"
    elif target_model == 'messagereaction':
        return f"chat_reaction_{instance.origin_id}"
    elif target_model == 'like':
        return f"like_{origin_model}_{instance.origin_id}"
    elif target_model == 'reaction':
        if origin_model == 'checkin':
            return str(instance.id)
        return f"reaction_{origin_model}_{instance.origin_id}"
    elif target_model == 'responserequest':
        return f"response_request_{instance.origin_id}"

    return str(instance.id)


def notify_firebase(instance):
    devices = CustomFCMDevice.objects.filter(user_id=instance.user.id, active=True)
    tag = get_notification_tag(instance)
    print(f"[FCM DEBUG] notify_firebase called: noti_id={instance.id}, user={instance.user_id}, devices={devices.count()}, tag={tag}")
    for device in devices:
        body = instance.message_ko if device.language == 'ko' else instance.message_en
        data = {
            'notification_id': str(instance.id),
            'message_en': instance.message_en or '',
            'message_ko': instance.message_ko or '',
            'url': instance.redirect_url,
            'tag': tag,
            'type': 'new',
            'content-available': '1',  # for ios silent notification
            'priority': 'high',  # for android
        }
        if device.type == 'web':
            message = Message(
                data=data,
                webpush=WebpushConfig(
                    notification=WebpushNotification(
                        title='WhoAmI Today',
                        body=body,
                        tag=tag,
                        renotify=True,
                        icon='/whoami192.png',
                    ),
                ),
            )
        elif device.type == 'ios':
            message = Message(
                data=data,
                apns=APNSConfig(
                    payload=APNSPayload(
                        aps=Aps(
                            alert={'title': 'WhoAmI Today', 'body': body},
                            sound='default',
                            content_available=True,
                        ),
                    ),
                ),
            )
        elif device.type == 'android':
            message = Message(
                data=data,
                android=AndroidConfig(
                    priority='high',
                    notification=AndroidNotification(
                        title='WhoAmI Today',
                        body=body,
                        tag=tag,
                    ),
                ),
            )
        else:
            message = Message(data=data)
        try:
            response = device.send_message(message)
            print(f"[FCM DEBUG] sent to device {device.id} (type={device.type}): {response}")
        except UnregisteredError:
            device.active = False
            device.save()
            print(f"[FCM DEBUG] device {device.id} unregistered, deactivated")
        except Exception as e:
            stack_trace = traceback.format_exc()
            send_msg_to_slack(
                text=f"🚨 Failed to send firebase notification to device {device.id}: {e}\n```{stack_trace}```",
                level="ERROR"
            )
            print(f"[FCM DEBUG] ERROR device {device.id} (type={device.type}): {e}\n{stack_trace}")


@receiver(post_save, sender=Notification, dispatch_uid='send_firebase_notification')
def send_firebase_notification(sender, instance, created, **kwargs):
    print(f"[FCM DEBUG] send_firebase_notification signal: noti_id={instance.id}, created={created}, deleted={instance.deleted}, skip_push={getattr(instance, '_skip_push', False)}")
    if instance.deleted or getattr(instance, '_skip_push', False):
        return
    if created:
        _push_firebase_async(instance)
    elif not instance.is_read:
        is_push_only_chat = (
            not instance.is_visible
            and instance.target_type
            and instance.target_type.model in ('message', 'messagereaction')
        )
        if instance.is_visible or is_push_only_chat:
            is_any_actor_active = instance.actors.filter(deleted__isnull=True).exists()
            if is_any_actor_active:
                _push_firebase_async(instance)


@receiver(post_save, sender=Notification, dispatch_uid='cancel_firebase_notification')
def cancel_firebase_notification(sender, instance, **kwargs):
    if not instance.deleted:
        return

    tag = get_notification_tag(instance)
    message = Message(
        data={
            'body': '삭제된 알림입니다.',
            'url': '/home',
            'tag': tag,
            'type': 'cancel',
        }
    )

    try:
        CustomFCMDevice.objects.filter(user_id=instance.user.id).send_message(message, False)
    except Exception as e:
        print("error while canceling firebase notification: ", e)
