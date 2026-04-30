from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models, transaction
from django.db.models import Q, F
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.utils import timezone
from safedelete.models import SafeDeleteModel, SOFT_DELETE_CASCADE

from adoorback.models import AdoorTimestampedModel
from notification.models import Notification, NotificationActor


MAX_GROUP_MEMBERS = 10


class ChatRoom(AdoorTimestampedModel, SafeDeleteModel):
    # 1-on-1 fields (kept for backward compat)
    user1 = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name='chat_rooms_as_user1',
        null=True, blank=True,
    )
    user2 = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name='chat_rooms_as_user2',
        null=True, blank=True,
    )

    # Group fields
    is_group = models.BooleanField(default=False)
    name = models.CharField(max_length=100, blank=True, default='')
    members = models.ManyToManyField(get_user_model(), related_name='group_chat_rooms', blank=True)

    # WIT Admin hotfix — see docs/superpowers/specs/2026-04-25-wit-admin-chat-hotfix-design.md
    is_wit_admin_proxy = models.BooleanField(default=False)
    is_wit_admin_blast_room = models.BooleanField(default=False)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user1', 'user2'], condition=Q(deleted__isnull=True, is_group=False), name='unique_chat_room'
            ),
            models.CheckConstraint(check=~Q(user1=F('user2')), name='no_self_chat_room')
        ]
        indexes = [
            models.Index(fields=['user1', 'user2']),
        ]

    def __str__(self):
        if self.is_group:
            return f"Group: {self.name or self.id}"
        return f"ChatRoom between {self.user1} and {self.user2}"

    def get_all_member_ids(self):
        if self.is_group:
            return list(self.members.values_list('id', flat=True))
        return [self.user1_id, self.user2_id]

    def save(self, *args, **kwargs):
        if self.deleted:
            super().save(*args, **kwargs)
            return

        if not self.is_group:
            self.full_clean()
            if self.user1_id and self.user2_id:
                if ChatRoom.objects.filter(user1=self.user2, user2=self.user1).exclude(pk=self.pk).exists():
                    raise ValueError("A reverse ChatRoom already exists.")
                if self.user1.id > self.user2.id:
                    self.user1, self.user2 = self.user2, self.user1

        super().save(*args, **kwargs)


MESSAGE_EMOJI_CHOICES = (
    ('wave', '👋'),
    ('smile', '😊'),
    ('heart', '❤️'),
    ('cry', '😭'),
    ('laugh', '🤣'),
)

MESSAGE_EVENT_CHOICES = (
    ('', 'Message'),
    ('member_added', 'Member Added'),
    ('member_left', 'Member Left'),
)


class Message(AdoorTimestampedModel, SafeDeleteModel):
    chat_room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, related_name='received_messages', null=True, blank=True)
    emoji = models.CharField(max_length=20, choices=MESSAGE_EMOJI_CHOICES, blank=True, null=True)
    content = models.TextField(blank=True, validators=[MaxLengthValidator(10000)])
    image = models.ImageField(upload_to='chat_images/', blank=True, null=True)
    is_read = models.BooleanField(default=False)
    # WIT Admin hotfix loop guard
    is_wit_admin_mirror = models.BooleanField(default=False)
    event_type = models.CharField(
        max_length=32, blank=True, default='', choices=MESSAGE_EVENT_CHOICES,
    )
    event_target_users = models.ManyToManyField(
        get_user_model(), blank=True, related_name='+',
    )
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')

    # Shared content (Note, Response, Question, etc.)
    shared_content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    shared_object_id = models.PositiveIntegerField(null=True, blank=True)
    shared_content = GenericForeignKey('shared_content_type', 'shared_object_id')

    message_notis = GenericRelation(
        Notification, content_type_field='target_type', object_id_field='target_id'
    )

    class Meta:
        indexes = [
            models.Index(fields=['chat_room', 'created_at']),
            models.Index(fields=['receiver', 'is_read']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sender} -> {self.receiver}: {self.content or self.emoji}"

    @property
    def type(self):
        return self.__class__.__name__

    def clean(self):
        if self.event_type:
            return

        if not self.emoji and not self.content and not self.shared_object_id and not self.image:
            raise ValidationError("Either an emoji, content, image, or shared content must be provided.")

        if self.chat_room.is_group:
            return  # Group messages don't validate sender/receiver pair

        if not (
            (self.chat_room.user1 == self.sender and self.chat_room.user2 == self.receiver) or
            (self.chat_room.user1 == self.receiver and self.chat_room.user2 == self.sender)
        ):
            raise ValidationError("The sender and receiver must match the users in the chat room.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class MessageReaction(AdoorTimestampedModel, SafeDeleteModel):
    user = models.ForeignKey(get_user_model(), related_name='message_reactions', on_delete=models.CASCADE)
    message = models.ForeignKey(Message, related_name='reactions', on_delete=models.CASCADE)
    emoji = models.CharField(max_length=20)

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'message', 'emoji'],
                condition=Q(deleted__isnull=True),
                name='unique_message_reaction'
            ),
        ]
        ordering = ['created_at']

    @property
    def type(self):
        return self.__class__.__name__

    def __str__(self):
        return f"{self.user} reacted {self.emoji} to message {self.message_id}"


class GroupReadCursor(models.Model):
    """Tracks the last read message per user per group chat room."""
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, related_name='group_read_cursors')
    chat_room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='read_cursors')
    last_read_message = models.ForeignKey(Message, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'chat_room'], name='unique_group_read_cursor'),
        ]

    def __str__(self):
        return f"{self.user} read up to msg {self.last_read_message_id} in room {self.chat_room_id}"


class WitBotConversationState(AdoorTimestampedModel):
    """Per-user state for the scripted wit_bot conversation engine.

    Tracks the user's current intent/step so multi-turn flows (onboarding,
    awaiting escalation confirmation) can resume across messages.
    """
    user = models.OneToOneField(
        get_user_model(), on_delete=models.CASCADE, related_name='wit_bot_state',
    )
    current_intent = models.CharField(max_length=64, blank=True, default='')
    step = models.IntegerField(default=0)
    context = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"wit_bot state for {self.user}: intent={self.current_intent!r} step={self.step}"


class ChatRequest(AdoorTimestampedModel, SafeDeleteModel):
    """Chat request for non-friends. Must be accepted before messaging is allowed."""
    requester = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name='sent_chat_requests'
    )
    requestee = models.ForeignKey(
        get_user_model(), on_delete=models.CASCADE, related_name='received_chat_requests'
    )
    accepted = models.BooleanField(null=True, default=None)

    chat_request_targetted_notis = GenericRelation(
        "notification.Notification",
        content_type_field='target_type',
        object_id_field='target_id'
    )

    _safedelete_policy = SOFT_DELETE_CASCADE

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['requester', 'requestee'],
                condition=Q(deleted__isnull=True),
                name='unique_chat_request'
            ),
            models.CheckConstraint(
                check=~Q(requester=F('requestee')),
                name='no_self_chat_request'
            )
        ]
        ordering = ['-created_at']

    def __str__(self):
        status = 'pending' if self.accepted is None else ('accepted' if self.accepted else 'declined')
        return f"ChatRequest from {self.requester} to {self.requestee} ({status})"

    @property
    def type(self):
        return self.__class__.__name__


@transaction.atomic
def get_or_create_chat_room(user1, user2):
    if user1.id > user2.id:
        user1, user2 = user2, user1
    chat_room, _ = ChatRoom.objects.get_or_create(user1=user1, user2=user2)
    return chat_room


@transaction.atomic
def get_chat_room(user1, user2):
    if user1.id > user2.id:
        user1, user2 = user2, user1
    return ChatRoom.objects.filter(user1=user1, user2=user2).first()


@transaction.atomic
@receiver(post_save, sender=Message)
def create_message_notification(created, instance, **kwargs):
    if not created:
        return

    # Suppress notifications for the original (non-mirror) message in WIT Admin
    # proxy rooms. The mirror in the user's User↔WIT_Admin chat fires its own
    # notification as `wit_admin`, which is the one the regular user should
    # see. Without this guard the user gets a duplicate "op_jaewon sent you a
    # message" push that links to a chat hidden from them (404).
    if instance.chat_room.is_wit_admin_proxy and not instance.is_wit_admin_mirror:
        return

    receiver_user = instance.receiver
    sender = instance.sender

    # Skip notifications for group messages (no single receiver)
    if receiver_user is None:
        return

    if receiver_user.id in sender.user_report_blocked_ids:
        return

    # Determine notification text based on message type
    if instance.image:
        noti_ko = f"{sender.username}님이 사진을 보냈습니다!"
        noti_en = f"{sender.username} sent you a photo!"
    elif instance.shared_object_id:
        noti_ko = f"{sender.username}님이 게시글을 보냈습니다!"
        noti_en = f"{sender.username} sent you a post!"
    else:
        noti_ko = f"{sender.username}님이 메시지를 보냈습니다!"
        noti_en = f"{sender.username} sent you a message!"

    recent_noti = Notification.objects.find_recent_message(receiver_user, sender)

    if recent_noti:
        current_count = 1
        try:
            part = recent_noti.message_ko.split("님이 ")[1]
            if "개의" in part:
                current_count = int(part.split("개의")[0])
        except (IndexError, ValueError):
            pass

        new_count = current_count + 1
        recent_noti.message_ko = f"{sender.username}님이 {new_count}개의 메시지를 보냈습니다!"
        recent_noti.message_en = f"{sender.username} sent you {new_count} messages!"
        recent_noti.notification_updated_at = timezone.now()
        recent_noti.save()

        NotificationActor.objects.create(user=sender, notification=recent_noti)
    else:
        noti = Notification.objects.create(
            user=receiver_user,
            origin=sender,
            target=instance,
            message_ko=noti_ko,
            message_en=noti_en,
            redirect_url=f"/users/{sender.id}/chat",
            is_visible=False,
        )
        NotificationActor.objects.create(user=sender, notification=noti)


@transaction.atomic
@receiver(post_save, sender=MessageReaction)
def create_message_reaction_notification(created, instance, **kwargs):
    """Push-only notification when someone reacts to your chat message."""
    if not created:
        return

    reactor = instance.user
    message = instance.message
    message_author = message.sender
    chat_room = message.chat_room

    # 자기 메시지에 리액션 → 노티 X
    if reactor.id == message_author.id:
        return

    # 차단된 유저 → 노티 X
    if message_author.id in reactor.user_report_blocked_ids:
        return

    emoji = instance.emoji

    # 같은 메시지에 대한 기존 리액션 노티 찾기 (24시간 내)
    message_ct = ContentType.objects.get_for_model(Message)
    reaction_ct = ContentType.objects.get_for_model(MessageReaction)
    cutoff = timezone.now() - timezone.timedelta(hours=24)

    recent_noti = Notification.objects.filter(
        user=message_author,
        origin_id=message.id,
        origin_type=message_ct,
        target_type=reaction_ct,
        notification_updated_at__gte=cutoff,
    ).order_by('-notification_updated_at').first()

    if recent_noti:
        actors = recent_noti.actors.order_by('-notificationactor__created_at')
        distinct_actor_ids = set(actors.values_list('id', flat=True))
        distinct_actor_ids.add(reactor.id)
        N = len(distinct_actor_ids)

        most_recent = actors.first()
        if most_recent and most_recent.id != reactor.id:
            second_name = most_recent.username
        elif actors.count() > 1:
            second_name = actors[1].username
        else:
            second_name = None

        if N == 1:
            noti_ko = f"{reactor.username}님이 회원님의 메시지에 반응했습니다: {emoji}"
            noti_en = f"{reactor.username} reacted to your message: {emoji}"
        elif N == 2:
            noti_ko = f"{reactor.username}님과 {second_name}님이 회원님의 메시지에 반응했습니다"
            noti_en = f"{reactor.username} and {second_name} reacted to your message"
        else:
            noti_ko = f"{reactor.username}님, {second_name}님, 외 {N - 2}명이 회원님의 메시지에 반응했습니다"
            noti_en = f"{reactor.username}, {second_name}, and {N - 2} other(s) reacted to your message"

        recent_noti.message_ko = noti_ko
        recent_noti.message_en = noti_en
        recent_noti.is_read = False
        recent_noti.notification_updated_at = timezone.now()
        recent_noti.save()
        NotificationActor.objects.create(user=reactor, notification=recent_noti)
    else:
        noti_ko = f"{reactor.username}님이 회원님의 메시지에 반응했습니다: {emoji}"
        noti_en = f"{reactor.username} reacted to your message: {emoji}"

        if chat_room.is_group:
            redirect_url = f"/chats/group/{chat_room.id}"
        else:
            redirect_url = f"/users/{reactor.id}/chat"

        noti = Notification.objects.create(
            user=message_author,
            origin=message,
            target=instance,
            message_ko=noti_ko,
            message_en=noti_en,
            redirect_url=redirect_url,
            is_visible=False,
        )
        NotificationActor.objects.create(user=reactor, notification=noti)


@transaction.atomic
@receiver(post_save, sender=ChatRequest)
def create_chat_request_noti(created, instance, **kwargs):
    if instance.deleted:
        return

    requester = instance.requester
    requestee = instance.requestee

    if requester.id in requestee.user_report_blocked_ids:
        return

    if created:
        noti = Notification.objects.create(
            user=requestee,
            origin=requester,
            target=instance,
            message_ko=f'{requester.username}님이 채팅 요청을 보냈습니다.',
            message_en=f'{requester.username} sent you a chat request.',
            redirect_url='/chat/requests',
        )
        NotificationActor.objects.create(user=requester, notification=noti)
    elif instance.accepted is True:
        noti = Notification.objects.create(
            user=requester,
            origin=requestee,
            target=instance,
            message_ko=f'{requestee.username}님이 채팅 요청을 수락했습니다.',
            message_en=f'{requestee.username} accepted your chat request.',
            redirect_url=f'/users/{requestee.id}/chat',
        )
        NotificationActor.objects.create(user=requestee, notification=noti)


@transaction.atomic
@receiver(post_save, sender=Message)
def fanout_wit_admin_messages(created, instance, **kwargs):
    """WIT Admin hotfix fan-out / fan-in / blast handler.

    Branches:
      1. Inbound user → WIT Admin     → mirror to 3 operator proxy rooms.
      2. Jaewon reply → user proxy    → mirror to user's WIT Admin room as WIT Admin.
      3. Jaewon blast → blast room    → fan out to all users + 2 observer logs.

    See docs/superpowers/specs/2026-04-25-wit-admin-chat-hotfix-design.md.
    """
    if not created:
        return
    if instance.is_wit_admin_mirror:
        return  # loop guard
    if getattr(instance, 'deleted', None) is not None:
        return  # don't fan out tombstones

    # Lazy import to avoid circular module load
    from chat.wit_admin import (
        ensure_wit_admin_user, resolve_operators, _copy_message_fields,
        is_wit_admin, is_replier,
    )
    from chat.views import broadcast_message_for_room

    room = instance.chat_room
    sender = instance.sender

    # Branch 1 — inbound user → WIT Admin
    is_user_to_wit_admin_room = (
        not room.is_group
        and not room.is_wit_admin_proxy
        and not room.is_wit_admin_blast_room
        and (is_wit_admin(room.user1) or is_wit_admin(room.user2))
        and not is_wit_admin(sender)
    )
    if is_user_to_wit_admin_room:
        try:
            operators = resolve_operators()
        except LookupError:
            return
        user = sender  # the regular user
        for op in operators:
            u1, u2 = (user, op) if user.id < op.id else (op, user)
            proxy_room = ChatRoom.objects.filter(
                user1=u1, user2=u2, is_wit_admin_proxy=True,
            ).first()
            if proxy_room is None:
                # Auto-heal best-effort: provision, then re-fetch. If still missing
                # (e.g. transient drift), skip this operator's mirror rather than
                # rolling back the user's original message.
                from chat.wit_admin import provision_user_rooms
                provision_user_rooms(user)
                proxy_room = ChatRoom.objects.filter(
                    user1=u1, user2=u2, is_wit_admin_proxy=True,
                ).first()
                if proxy_room is None:
                    continue
            mirror = Message.objects.create(
                chat_room=proxy_room,
                sender=user,
                receiver=op,
                **_copy_message_fields(instance),
            )
            broadcast_message_for_room(mirror)

    # Branch 2 — jaewon reply in proxy room → mirror to user's WIT Admin room
    if room.is_wit_admin_proxy and is_replier(sender):
        # Identify the regular user as the non-jaewon participant
        user = room.user2 if room.user1_id == sender.id else room.user1
        wit = ensure_wit_admin_user()
        u1, u2 = (user, wit) if user.id < wit.id else (wit, user)
        wit_room = ChatRoom.objects.filter(
            user1=u1, user2=u2, is_wit_admin_proxy=False,
        ).first()
        if wit_room is None:
            from chat.wit_admin import provision_user_rooms
            provision_user_rooms(user)
            wit_room = ChatRoom.objects.filter(
                user1=u1, user2=u2, is_wit_admin_proxy=False,
            ).first()
            if wit_room is None:
                return
        mirror = Message.objects.create(
            chat_room=wit_room,
            sender=wit,
            receiver=user,
            **_copy_message_fields(instance),
        )
        broadcast_message_for_room(mirror)
        return

    # Branch 3 — jaewon blast in his blast room → fan out to all users + 2 observer logs
    if room.is_wit_admin_blast_room and is_replier(sender):
        from chat.wit_admin import (
            regular_recipients, OPERATOR_OBSERVER_EMAILS,
        )
        wit = ensure_wit_admin_user()

        # 3a — every regular user's WIT Admin room
        for user in regular_recipients().iterator(chunk_size=500):
            u1, u2 = (user, wit) if user.id < wit.id else (wit, user)
            wit_room = ChatRoom.objects.filter(
                user1=u1, user2=u2, is_wit_admin_proxy=False,
            ).first()
            if wit_room is None:
                from chat.wit_admin import provision_user_rooms
                provision_user_rooms(user)
                wit_room = ChatRoom.objects.filter(
                    user1=u1, user2=u2, is_wit_admin_proxy=False,
                ).first()
                if wit_room is None:
                    continue
            mirror = Message.objects.create(
                chat_room=wit_room,
                sender=wit,
                receiver=user,
                **_copy_message_fields(instance),
            )
            broadcast_message_for_room(mirror)

        # 3b — observer (koyrkr, njs) blast logs
        UserModel = get_user_model()
        for email in OPERATOR_OBSERVER_EMAILS:
            observer = UserModel.objects.filter(email=email).first()
            if observer is None:
                continue
            u1, u2 = (wit, observer) if wit.id < observer.id else (observer, wit)
            log_room = ChatRoom.objects.filter(
                user1=u1, user2=u2, is_wit_admin_blast_room=True,
            ).first()
            if log_room is None:
                continue
            mirror = Message.objects.create(
                chat_room=log_room,
                sender=wit,
                receiver=observer,
                **_copy_message_fields(instance),
            )
            broadcast_message_for_room(mirror)
        return


@receiver(post_save, sender=Message)
def dispatch_wit_bot_engine(created, instance, **kwargs):
    """Dispatch user messages in a wit_bot 1-on-1 to the scripted engine.

    Stays out of the way for: existing wit_admin proxy/blast rooms (those
    rooms aren't wit_bot rooms), system events (member_added/left), bot's
    own replies, and post-escalation group rooms (engine hands off to humans).
    """
    if not created or instance.deleted or instance.event_type:
        return
    room = instance.chat_room
    if room.is_group:
        return  # post-escalation — humans take over
    if room.is_wit_admin_proxy or room.is_wit_admin_blast_room:
        return  # belt-and-suspenders; wit_bot rooms never carry these flags
    if instance.is_wit_admin_mirror:
        return  # mirrored wit_admin traffic, never wit_bot input

    from chat.wit_bot import is_wit_bot
    if not (is_wit_bot(room.user1) or is_wit_bot(room.user2)):
        return
    if is_wit_bot(instance.sender):
        return  # loop guard

    from chat.wit_bot_engine import handle_user_message
    handle_user_message(instance)
