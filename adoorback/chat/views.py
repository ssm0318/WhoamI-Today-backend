from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import F, OuterRef, Prefetch, Subquery, Count, Q
from rest_framework import generics, exceptions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from adoorback.utils.alerts import send_msg_to_slack
from adoorback.utils.validators import adoor_exception_handler
from django.contrib.contenttypes.models import ContentType
from .models import Message, ChatRoom, ChatRequest, MessageReaction, GroupReadCursor, MAX_GROUP_MEMBERS, OnboardingEvent, get_or_create_chat_room, get_chat_room
from .serializers import (
    MessageSerializer, ChatRoomSerializer,
    ChatRequestSerializer, ChatRequestUpdateSerializer,
    MessageReactionSerializer,
)

User = get_user_model()


class ChatRoomListPagination(PageNumberPagination):
    """Chat rooms per user are bounded (one per peer, plus operator/admin
    surfaces) so a single page covers virtually every realistic case. The
    frontend chat list does not implement infinite scroll, so a too-small
    page size silently hides rooms past the first 10."""
    page_size = 200
    max_page_size = 500


def _get_chat_group_name(user_id_1, user_id_2):
    ids = sorted([user_id_1, user_id_2])
    return f"chat_{ids[0]}_{ids[1]}"


def _get_message_preview_text(response_data):
    """Extract a preview string from serialized message data for chat list display."""
    event_type = response_data.get('event_type')
    if event_type:
        return _get_system_event_preview_text(event_type)
    content = response_data.get('content') or response_data.get('emoji') or ''
    if not content:
        if response_data.get('image'):
            content = '📷 Photo'
        elif response_data.get('shared_content_preview'):
            content = '📎 Shared post'
    return content


def _get_system_event_preview_text(event_type):
    """English fallback preview text for system events. Frontend re-localizes
    via the API response on next refresh."""
    if event_type == 'member_added':
        return 'A member was added'
    if event_type == 'member_left':
        return 'A member left'
    return ''


def _broadcast_system_message(room, message, chat_list_recipients=None):
    """Broadcast a system event Message via the existing chat.message channel
    and update each recipient's chat list. Reuses the regular group message
    broadcast pattern so the frontend doesn't need a new socket event type.

    chat_list_recipients defaults to current room members. Pass an explicit list
    to avoid sending chat.list.update to a user who just left.
    """
    serialized = MessageSerializer(message).data
    channel_layer = get_channel_layer()
    try:
        async_to_sync(channel_layer.group_send)(
            f"chat_group_{room.id}",
            {"type": "chat.message", "data": serialized},
        )
    except Exception:
        pass

    preview = _get_system_event_preview_text(message.event_type)
    timestamp = serialized.get('created_at', '')
    if chat_list_recipients is None:
        chat_list_recipients = list(room.members.all())

    for member in chat_list_recipients:
        cursor = GroupReadCursor.objects.filter(user=member, chat_room=room).first()
        if cursor and cursor.last_read_message:
            unread = room.messages.exclude(sender=member).filter(
                created_at__gt=cursor.last_read_message.created_at
            ).count()
        else:
            unread = room.messages.exclude(sender=member).count()
        try:
            async_to_sync(channel_layer.group_send)(
                f"user_{member.id}_chat_list",
                {
                    "type": "chat.list.update",
                    "data": {
                        "room_id": int(room.id),
                        "is_group": True,
                        "group_name": room.name,
                        "last_message": preview,
                        "last_message_time": timestamp,
                        "unread_count": unread,
                    },
                },
            )
        except Exception:
            pass


def broadcast_message_for_room(message):
    """Broadcast a 1:1 Message to its chat room WebSocket group and update both
    participants' chat lists.

    Used by:
    - `MessageList.create` (via inline code; could be refactored later).
    - `fanout_wit_admin_messages` signal (mirror message broadcast).

    Silently skips group rooms (not supported here) and best-effort on WS errors.
    """
    chat_room = message.chat_room
    if chat_room.is_group:
        return
    if chat_room.user1_id is None or chat_room.user2_id is None:
        return

    serialized = MessageSerializer(message).data
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    group_name = _get_chat_group_name(chat_room.user1_id, chat_room.user2_id)
    try:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {"type": "chat.message", "data": serialized},
        )
    except Exception as e:
        print(f"[CHAT BROADCAST ERROR] room={chat_room.id}: {e}")

    content = serialized.get('content') or serialized.get('emoji') or ''
    timestamp = serialized.get('created_at', '')

    sender_id = message.sender_id
    receiver_id = message.receiver_id
    if receiver_id is None:
        return

    receiver_unread = chat_room.messages.filter(receiver_id=receiver_id, is_read=False).count()

    for target_id, opponent_id, unread in (
        (receiver_id, sender_id, receiver_unread),
        (sender_id, receiver_id, 0),
    ):
        if target_id is None:
            continue
        try:
            async_to_sync(channel_layer.group_send)(
                f"user_{target_id}_chat_list",
                {"type": "chat.list.update", "data": {
                    "opponent_id": opponent_id,
                    "last_message": content,
                    "last_message_time": timestamp,
                    "unread_count": unread,
                }},
            )
        except Exception as e:
            print(f"[CHAT LIST BROADCAST ERROR] user={target_id}: {e}")


class ChatRoomList(generics.ListAPIView):
    serializer_class = ChatRoomSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = ChatRoomListPagination

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        user = self.request.user
        ctx['close_friend_ids'] = set(user.close_friend_ids)
        # Pre-load relationship + chat-request data ONCE so the per-room
        # serializer methods don't run N+1 queries. Each cache is one query
        # (or in the request_map case, two filtered selects merged).
        ctx['connected_user_ids'] = set(user.connected_user_ids)
        from chat.models import ChatRequest
        from django.db.models import Q as _Q
        request_map = {}
        for req in ChatRequest.objects.filter(_Q(requester=user) | _Q(requestee=user)):
            peer_id = req.requestee_id if req.requester_id == user.id else req.requester_id
            # Keep the most-recently created request per peer if multiple exist.
            existing = request_map.get(peer_id)
            if existing is None or req.id > existing.id:
                request_map[peer_id] = req
        ctx['chat_requests_by_peer'] = request_map
        return ctx

    def get_queryset(self):
        from django.db.models import Case, When, Value, IntegerField
        from chat.wit_admin import WIT_ADMIN_USERNAME, ALL_OPERATOR_EMAILS
        from chat.wit_bot import WIT_BOT_USERNAME

        user = self.request.user
        blocked_ids = user.user_report_blocked_ids

        latest_msg = Message.objects.filter(
            chat_room=OuterRef('pk')
        ).order_by('-created_at')

        # Pin tier: wit_admin (0) above wit_bot (1) above everything else (2).
        # The members__username arm on each system user covers post-escalation
        # promoted groups where the room is_group=True but the original user1/
        # user2 fields still point at the pre-promotion pair.
        pin_rank = Case(
            When(
                Q(user1__username=WIT_ADMIN_USERNAME)
                | Q(user2__username=WIT_ADMIN_USERNAME)
                | Q(members__username=WIT_ADMIN_USERNAME),
                then=Value(0),
            ),
            When(
                Q(user1__username=WIT_BOT_USERNAME)
                | Q(user2__username=WIT_BOT_USERNAME)
                | Q(members__username=WIT_BOT_USERNAME),
                then=Value(1),
            ),
            default=Value(2),
            output_field=IntegerField(),
        )

        # select_related the 1-on-1 user FKs so opponent/user1/user2 access in
        # the serializer doesn't fire two queries per row. prefetch_related
        # `members` so group-room renders don't fire one query per row, and
        # prefetch the requesting user's GroupReadCursor so unread-count for
        # groups doesn't either. Combined: kills the largest N+1 on chat-list.
        qs = ChatRoom.objects.filter(
            Q(user1=user) | Q(user2=user) | Q(members=user)
        ).distinct().select_related('user1', 'user2').prefetch_related(
            'members',
            Prefetch(
                'read_cursors',
                queryset=GroupReadCursor.objects.filter(user=user).select_related('last_read_message'),
                to_attr='_user_cursors',
            ),
        )

        if blocked_ids:
            qs = qs.exclude(
                Q(is_group=False) & (
                    (Q(user1=user) & Q(user2_id__in=blocked_ids)) |
                    (Q(user2=user) & Q(user1_id__in=blocked_ids))
                )
            )

        # Hide WIT Admin proxy rooms from non-operator viewers. From a regular
        # user's perspective the operator-side proxy chat shouldn't appear in
        # their chat list — they only see their User↔WIT_Admin chat.
        if user.email not in ALL_OPERATOR_EMAILS:
            qs = qs.exclude(is_wit_admin_proxy=True)

        # Version isolation: hide 1-on-1 rooms where the other user is on a different version.
        # System users (wit_admin, wit_bot) are version-agnostic — exempt them.
        qs = qs.exclude(
            Q(is_group=False) & ~Q(
                Q(user1__username__in=[WIT_ADMIN_USERNAME, WIT_BOT_USERNAME])
                | Q(user2__username__in=[WIT_ADMIN_USERNAME, WIT_BOT_USERNAME])
            ) & (
                (Q(user1=user) & ~Q(user2__current_ver=user.current_ver)) |
                (Q(user2=user) & ~Q(user1__current_ver=user.current_ver))
            )
        )

        annotated = qs.annotate(
            last_message_time=Subquery(latest_msg.values('created_at')[:1]),
            last_message_content=Subquery(latest_msg.values('content')[:1]),
            last_message_emoji=Subquery(latest_msg.values('emoji')[:1]),
            last_message_image=Subquery(latest_msg.values('image')[:1]),
            last_message_shared_type=Subquery(latest_msg.values('shared_content_type')[:1]),
            last_message_event_type=Subquery(latest_msg.values('event_type')[:1]),
            unread_cnt=Count(
                'messages',
                filter=Q(messages__receiver=user, messages__is_read=False)
            ),
            pin_rank=pin_rank,
        )

        # Surface system-user rooms (pin_rank < 2) and operator proxy rooms
        # in the relevant lists even when there's no traffic yet.
        if user.email in ALL_OPERATOR_EMAILS:
            visibility = (
                Q(last_message_time__isnull=False)
                | Q(pin_rank__lt=2)
                | Q(is_wit_admin_proxy=True)
            )
        else:
            visibility = Q(last_message_time__isnull=False) | Q(pin_rank__lt=2)

        return annotated.filter(visibility).order_by(
            'pin_rank',
            F('last_message_time').desc(nulls_last=True),
        )


class MessageList(generics.ListCreateAPIView):
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user = self.request.user
        try:
            connected_user = User.objects.get(id=self.kwargs.get('pk'))
        except User.DoesNotExist:
            raise exceptions.NotFound("Connected user not found")

        if connected_user.id in user.user_report_blocked_ids:
            raise exceptions.PermissionDenied("This user is blocked.")

        chat_room = get_chat_room(connected_user, user)
        if not chat_room:
            self.oldest_unread_page = 1
            return Message.objects.none()

        qs = chat_room.messages.select_related(
            'sender', 'parent', 'parent__sender'
        ).prefetch_related('reactions').all()

        oldest_unread = chat_room.messages.filter(receiver=user, is_read=False).order_by('id').first()

        if oldest_unread:
            oldest_position = Message.objects.filter(chat_room=chat_room, id__gte=oldest_unread.id).count()
            pagination_size = getattr(settings, 'REST_FRAMEWORK', {}).get('PAGE_SIZE', 10)
            page_number = (oldest_position - 1) // pagination_size + 1
        else:
            page_number = 1
        self.oldest_unread_page = page_number

        return qs

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)

        try:
            connected_user = User.objects.get(id=self.kwargs.get('pk'))
        except User.DoesNotExist:
            raise exceptions.NotFound("Connected user not found")

        # Cache the chat_room lookup once for both branches below.
        chat_room = get_chat_room(request.user, connected_user)

        # Rebrand the blast room header as "Announcements" so the chat detail
        # view matches the chat-list label.
        from chat.wit_admin import is_wit_admin
        display_username = connected_user.username
        if chat_room and chat_room.is_wit_admin_blast_room and is_wit_admin(connected_user):
            display_username = 'Announcements'
        response.data['username'] = display_username
        response.data['oldest_unread_page'] = self.oldest_unread_page

        paginated_queryset = self.paginator.paginate_queryset(self.get_queryset(), request)
        if paginated_queryset and chat_room:
            msg_ids = [msg.id for msg in paginated_queryset]
            marked = Message.objects.filter(id__in=msg_ids, receiver=request.user, is_read=False).update(is_read=True)
            # Only fire the chat-list WS update when at least one message
            # actually flipped to read — otherwise we burn a Redis pub for a
            # no-op every time the user re-opens an already-read chat.
            if marked > 0:
                remaining = chat_room.messages.filter(receiver=request.user, is_read=False).count()
                channel_layer = get_channel_layer()
                try:
                    async_to_sync(channel_layer.group_send)(
                        f"user_{request.user.id}_chat_list",
                        {
                            "type": "chat.list.update",
                            "data": {
                                "opponent_id": connected_user.id,
                                "unread_count": remaining,
                            },
                        },
                    )
                except Exception:
                    pass

        return response

    def perform_create(self, serializer):
        from chat.wit_admin import is_wit_admin
        from chat.wit_bot import is_wit_bot

        user = self.request.user
        try:
            connected_user = User.objects.get(id=self.kwargs.get('pk'))
        except User.DoesNotExist:
            raise exceptions.NotFound("Connected user not found")

        if connected_user.id in user.user_report_blocked_ids:
            raise exceptions.PermissionDenied("This user is blocked.")

        # Skip the ChatRequest gate for WIT-Admin-related chats. The support
        # persona, the per-user operator proxy chats, and the operator blast
        # rooms are all known operational surfaces — friend-consent rules don't
        # apply. See docs/superpowers/specs/2026-04-25-wit-admin-chat-hotfix-design.md.
        # wit_bot also gets the same carve-out: it's a single bot account that
        # talks to participants on both versions, and version-isolation would
        # otherwise 403 every Q user out of the onboarding flow since wit_bot
        # is created with current_ver=version_w.
        is_system_bot_surface = (
            is_wit_admin(user)
            or is_wit_admin(connected_user)
            or is_wit_bot(user)
            or is_wit_bot(connected_user)
            or ChatRoom.objects.filter(
                (Q(user1=user, user2=connected_user) | Q(user1=connected_user, user2=user)),
            ).filter(
                Q(is_wit_admin_proxy=True) | Q(is_wit_admin_blast_room=True)
            ).exists()
        )

        # Version isolation: block messaging across different versions
        if not is_system_bot_surface and user.current_ver != connected_user.current_ver:
            raise exceptions.PermissionDenied("Cannot message users on a different version.")

        if not is_system_bot_surface and not user.is_connected(connected_user):
            req = ChatRequest.objects.filter(
                Q(requester=user, requestee=connected_user) |
                Q(requester=connected_user, requestee=user)
            ).first()

            if req is None:
                ChatRequest.objects.create(requester=user, requestee=connected_user)
            elif req.accepted is False:
                raise exceptions.PermissionDenied("This chat request was declined.")
            elif req.accepted is None and req.requester != user:
                raise exceptions.PermissionDenied(
                    "You have a pending chat request from this user. Accept it first."
                )

        chat_room = get_or_create_chat_room(user, connected_user)

        parent_id = self.request.data.get('parent')
        parent = None
        if parent_id:
            parent = Message.objects.filter(id=parent_id, chat_room=chat_room).first()

        # Shared content
        extra = {}
        shared_type = self.request.data.get('shared_content_type')
        shared_id = self.request.data.get('shared_object_id')
        if shared_type and shared_id:
            try:
                ct = ContentType.objects.get(model=shared_type)
                extra['shared_content_type'] = ct
                extra['shared_object_id'] = int(shared_id)
            except ContentType.DoesNotExist:
                pass

        serializer.save(sender=user, receiver=connected_user, chat_room=chat_room, parent=parent, **extra)

    def create(self, request, *args, **kwargs):
        from chat.wit_bot import is_wit_bot

        response = super().create(request, *args, **kwargs)

        user = request.user
        try:
            connected_user = User.objects.get(id=self.kwargs.get('pk'))
            chat_room = get_or_create_chat_room(user, connected_user)
            unread_count = chat_room.messages.filter(receiver=user, is_read=False).count()
        except User.DoesNotExist:
            raise exceptions.NotFound("Connected user not found")

        response.data['unread_count'] = unread_count

        # wit_bot fast path: when the room is a 1-on-1 with the bot, the
        # dispatch_wit_bot_engine signal has already created the bot's reply
        # synchronously inside super().create(). Pick up everything created
        # since the user's message and ride it back inline so the frontend
        # doesn't need a WebSocket hop. Skip the WS broadcasts entirely for
        # this path — bot has no WS client and the user's own message is
        # already in the response.
        if not chat_room.is_group and is_wit_bot(connected_user):
            user_msg_id = response.data.get('id')
            if user_msg_id:
                bot_replies_qs = chat_room.messages.filter(
                    id__gt=user_msg_id,
                ).exclude(
                    event_type='wit_welcome_card',
                ).order_by('id')
                response.data['bot_replies'] = MessageSerializer(
                    bot_replies_qs, many=True, context={'request': request},
                ).data
            return response

        # Broadcast via WebSocket to the chat room
        group_name = _get_chat_group_name(user.id, connected_user.id)
        channel_layer = get_channel_layer()
        try:
            async_to_sync(channel_layer.group_send)(
                group_name,
                {"type": "chat.message", "data": response.data},
            )
        except Exception as e:
            print(f"[CHAT BROADCAST ERROR] room={group_name}: {e}")
            send_msg_to_slack(
                text=f"*💬 Chat broadcast failed*\nRoom: `{group_name}`\nSender: {user.username} (ID: {user.id}) → Receiver: {connected_user.username} (ID: {connected_user.id})\n```{e}```",
                level="ERROR",
            )

        # Broadcast to both users' chat list so the list page updates
        content = _get_message_preview_text(response.data)
        timestamp = response.data.get('created_at', '')
        receiver_unread = chat_room.messages.filter(receiver=connected_user, is_read=False).count()
        for target_user, unread in [(connected_user, receiver_unread), (user, 0)]:
            try:
                async_to_sync(channel_layer.group_send)(
                    f"user_{target_user.id}_chat_list",
                    {
                        "type": "chat.list.update",
                        "data": {
                            "opponent_id": user.id if target_user == connected_user else connected_user.id,
                            "last_message": content,
                            "last_message_time": timestamp,
                            "unread_count": unread,
                        },
                    },
                )
            except Exception as e:
                print(f"[CHAT LIST BROADCAST ERROR] user={target_user.id}: {e}")

        return response


class MarkMessagesRead(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def post(self, request, pk):
        user = request.user
        try:
            connected_user = User.objects.get(id=pk)
        except User.DoesNotExist:
            raise exceptions.NotFound("Connected user not found")

        chat_room = get_chat_room(user, connected_user)
        if chat_room:
            count = chat_room.messages.filter(receiver=user, is_read=False).update(is_read=True)
            if count > 0:
                channel_layer = get_channel_layer()
                try:
                    async_to_sync(channel_layer.group_send)(
                        f"user_{user.id}_chat_list",
                        {
                            "type": "chat.list.update",
                            "data": {
                                "opponent_id": connected_user.id,
                                "unread_count": 0,
                            },
                        },
                    )
                except Exception:
                    pass
            return Response({'marked_read': count})
        return Response({'marked_read': 0})


class MarkGroupMessagesRead(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def post(self, request, pk):
        user = request.user
        try:
            room = ChatRoom.objects.get(id=pk, is_group=True)
        except ChatRoom.DoesNotExist:
            raise exceptions.NotFound("Group not found.")

        if not room.members.filter(id=user.id).exists():
            raise exceptions.PermissionDenied("You are not a member of this group.")

        last_msg = room.messages.order_by('-created_at').first()
        if last_msg:
            cursor, _ = GroupReadCursor.objects.get_or_create(user=user, chat_room=room)
            cursor.last_read_message = last_msg
            cursor.save()

        return Response({'status': 'ok'})


class MessageReactionCreate(generics.CreateAPIView):
    serializer_class = MessageReactionSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def _check_participant(self, user, chat_room):
        if chat_room.is_group:
            if not chat_room.members.filter(id=user.id).exists():
                raise exceptions.PermissionDenied("You are not a participant in this chat.")
        elif user != chat_room.user1 and user != chat_room.user2:
            raise exceptions.PermissionDenied("You are not a participant in this chat.")

    def _broadcast_reactions(self, request, message, chat_room):
        serializer = MessageSerializer(message, context={'request': request})
        channel_layer = get_channel_layer()

        if chat_room.is_group:
            group_name = f"chat_group_{chat_room.id}"
        else:
            group_name = _get_chat_group_name(request.user.id,
                (chat_room.user2 if chat_room.user1 == request.user else chat_room.user1).id)

        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "chat.reaction",
                "data": {
                    "action": "reaction",
                    "message_id": message.id,
                    "reactions": serializer.data['reactions'],
                },
            },
        )

    def create(self, request, *args, **kwargs):
        user = request.user
        message = Message.objects.get(id=self.kwargs.get('message_id'))
        chat_room = message.chat_room
        emoji = request.data.get('emoji', '')

        self._check_participant(user, chat_room)

        # Idempotent create: if reaction already exists, just return it
        _, created = MessageReaction.objects.get_or_create(
            user=user, message=message, emoji=emoji,
        )

        self._broadcast_reactions(request, message, chat_room)

        reactions_serializer = MessageSerializer(message, context={'request': request})
        return Response(
            {'reactions': reactions_serializer.data['reactions']},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class MessageReactionDestroy(generics.DestroyAPIView):
    serializer_class = MessageReactionSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        try:
            reaction = MessageReaction.objects.get(id=self.kwargs.get('pk'), user=self.request.user)
        except MessageReaction.DoesNotExist:
            raise exceptions.NotFound("Reaction not found.")
        return reaction

    def perform_destroy(self, instance):
        message = instance.message
        instance.delete()

        chat_room = message.chat_room

        # Broadcast reaction removal via WebSocket
        channel_layer = get_channel_layer()

        if chat_room.is_group:
            group_name = f"chat_group_{chat_room.id}"
        else:
            other_user = chat_room.user2 if chat_room.user1 == self.request.user else chat_room.user1
            group_name = _get_chat_group_name(self.request.user.id, other_user.id)

        serializer = MessageSerializer(message, context={'request': self.request})
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "chat.reaction",
                "data": {
                    "action": "reaction",
                    "message_id": message.id,
                    "reactions": serializer.data['reactions'],
                },
            },
        )


class ChatRequestCreate(generics.ListCreateAPIView):
    serializer_class = ChatRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        return ChatRequest.objects.filter(
            requestee=self.request.user, accepted__isnull=True
        )

    def create(self, request, *args, **kwargs):
        self._auto_accepted = False
        self._auto_accepted_request = None

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        if self._auto_accepted:
            response_serializer = ChatRequestSerializer(
                self._auto_accepted_request, context={'request': request}
            )
            data = response_serializer.data
            data['auto_accepted'] = True
            return Response(data, status=status.HTTP_200_OK)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        user = self.request.user
        requestee_id = serializer.validated_data['requestee_id']
        requestee = User.objects.get(id=requestee_id)

        # Version isolation
        if user.current_ver != requestee.current_ver:
            raise exceptions.PermissionDenied("Cannot send chat request to a user on a different version.")

        if user.is_connected(requestee):
            raise exceptions.ValidationError("You are already friends. No request needed.")

        existing = ChatRequest.objects.filter(
            Q(requester=user, requestee=requestee) |
            Q(requester=requestee, requestee=user)
        ).first()

        if existing:
            if existing.requester == user:
                if existing.accepted is None:
                    raise exceptions.ValidationError("You already have a pending chat request to this user.")
                elif existing.accepted is True:
                    raise exceptions.ValidationError("A chat request between you has already been accepted.")
                else:
                    existing.delete()
                    serializer.save(requester=user, requestee=requestee)
                    return
            else:
                if existing.accepted is None:
                    existing.accepted = True
                    existing.save()
                    get_or_create_chat_room(user, requestee)
                    self._auto_accepted = True
                    self._auto_accepted_request = existing
                    return
                elif existing.accepted is True:
                    raise exceptions.ValidationError("A chat request between you has already been accepted.")
                else:
                    existing.delete()
                    serializer.save(requester=user, requestee=requestee)
                    return

        serializer.save(requester=user, requestee=requestee)


class ChatRequestSentList(generics.ListAPIView):
    serializer_class = ChatRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        return ChatRequest.objects.filter(requester=self.request.user)


class ChatRequestUpdate(generics.UpdateAPIView):
    serializer_class = ChatRequestUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        try:
            return ChatRequest.objects.get(
                id=self.kwargs.get('pk'),
                requestee=self.request.user
            )
        except ChatRequest.DoesNotExist:
            raise exceptions.NotFound("Chat request not found.")

    def perform_update(self, serializer):
        instance = serializer.save()
        if instance.accepted:
            get_or_create_chat_room(instance.requester, instance.requestee)


class ChatRequestCancel(generics.DestroyAPIView):
    serializer_class = ChatRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        try:
            return ChatRequest.objects.get(
                requester=self.request.user,
                requestee_id=self.kwargs.get('requestee_id'),
                accepted__isnull=True,
            )
        except ChatRequest.DoesNotExist:
            raise exceptions.NotFound("Pending chat request not found.")


class MessageSearch(generics.ListAPIView):
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user = self.request.user
        blocked_ids = user.user_report_blocked_ids
        query = self.request.query_params.get('q', '').strip()
        if not query:
            return Message.objects.none()

        user_rooms = ChatRoom.objects.filter(Q(user1=user) | Q(user2=user))
        if blocked_ids:
            user_rooms = user_rooms.exclude(
                (Q(user1=user) & Q(user2_id__in=blocked_ids)) |
                (Q(user2=user) & Q(user1_id__in=blocked_ids))
            )
        return Message.objects.filter(
            chat_room__in=user_rooms,
            content__icontains=query,
        ).select_related('sender', 'chat_room', 'chat_room__user1', 'chat_room__user2').order_by('-created_at')[:50]

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        user = request.user

        # Add opponent info to each result
        for msg_data in response.data.get('results', response.data if isinstance(response.data, list) else []):
            msg = Message.objects.select_related('chat_room__user1', 'chat_room__user2').filter(id=msg_data['id']).first()
            if msg:
                room = msg.chat_room
                opponent = room.user2 if room.user1 == user else room.user1
                msg_data['opponent'] = {'id': opponent.id, 'username': opponent.username}

        return response


# ---- Group Chat Views ----

class GroupChatCreate(generics.CreateAPIView):
    """POST /chat/groups/ — create a group chat with name + member IDs."""
    serializer_class = ChatRoomSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def create(self, request, *args, **kwargs):
        user = request.user
        name = request.data.get('name', '')
        member_ids = request.data.get('member_ids', [])

        if not member_ids or len(member_ids) < 1:
            raise exceptions.ValidationError("At least one other member is required.")

        all_member_ids = list(set([user.id] + [int(m) for m in member_ids]))
        if len(all_member_ids) > MAX_GROUP_MEMBERS:
            raise exceptions.ValidationError(f"Group cannot exceed {MAX_GROUP_MEMBERS} members.")

        members = User.objects.filter(id__in=all_member_ids)
        if members.count() != len(all_member_ids):
            raise exceptions.NotFound("One or more users not found.")

        # Version isolation: all members must be on the same version
        if members.exclude(current_ver=user.current_ver).exists():
            raise exceptions.ValidationError("Cannot create a group with members on a different version.")

        room = ChatRoom.objects.create(is_group=True, name=name)
        room.members.set(members)

        serializer = ChatRoomSerializer(room, context={'request': request})
        return Response(serializer.data, status=201)


class GroupChatUpdate(generics.GenericAPIView):
    """GET/PATCH /chat/groups/{id}/ — get or update group chat."""
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get(self, request, pk):
        user = request.user
        try:
            room = ChatRoom.objects.get(id=pk, is_group=True)
        except ChatRoom.DoesNotExist:
            raise exceptions.NotFound("Group not found.")

        if not room.members.filter(id=user.id).exists():
            raise exceptions.PermissionDenied("You are not a member of this group.")

        serializer = ChatRoomSerializer(room, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, pk):
        user = request.user
        try:
            room = ChatRoom.objects.get(id=pk, is_group=True)
        except ChatRoom.DoesNotExist:
            raise exceptions.NotFound("Group not found.")

        if not room.members.filter(id=user.id).exists():
            raise exceptions.PermissionDenied("You are not a member of this group.")

        # Update name
        name = request.data.get('name')
        if name is not None:
            room.name = name
            room.save()

        # Add members
        add_ids = request.data.get('add_member_ids', [])
        if add_ids:
            current_count = room.members.count()
            if current_count + len(add_ids) > MAX_GROUP_MEMBERS:
                raise exceptions.ValidationError(f"Group cannot exceed {MAX_GROUP_MEMBERS} members.")
            new_members = list(User.objects.filter(id__in=add_ids))
            # Version isolation: new members must be on the same version
            diff_ver = [m for m in new_members if m.current_ver != user.current_ver]
            if diff_ver:
                raise exceptions.ValidationError("Cannot add members on a different version.")
            room.members.add(*new_members)
            if new_members:
                added_msg = Message.objects.create(
                    chat_room=room, sender=user, receiver=None,
                    event_type='member_added',
                )
                added_msg.event_target_users.set(new_members)
                _broadcast_system_message(room, added_msg)

        # Remove members
        remove_ids = request.data.get('remove_member_ids', [])
        if remove_ids:
            removed_members = list(User.objects.filter(id__in=remove_ids))
            room.members.remove(*removed_members)
            if removed_members:
                removed_msg = Message.objects.create(
                    chat_room=room, sender=user, receiver=None,
                    event_type='member_left',
                )
                removed_msg.event_target_users.set(removed_members)
                _broadcast_system_message(room, removed_msg)

        serializer = ChatRoomSerializer(room, context={'request': request})
        return Response(serializer.data)


class GroupChatLeave(generics.GenericAPIView):
    """POST /chat/groups/{id}/leave/ — leave a group chat."""
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def post(self, request, pk):
        user = request.user
        try:
            room = ChatRoom.objects.get(id=pk, is_group=True)
        except ChatRoom.DoesNotExist:
            raise exceptions.NotFound("Group not found.")

        if not room.members.filter(id=user.id).exists():
            raise exceptions.PermissionDenied("You are not a member of this group.")

        leave_msg = Message.objects.create(
            chat_room=room, sender=user, receiver=None,
            event_type='member_left',
        )
        leave_msg.event_target_users.set([user])

        remaining_members = list(room.members.exclude(id=user.id))
        room.members.remove(user)

        if remaining_members:
            _broadcast_system_message(room, leave_msg, chat_list_recipients=remaining_members)
            return Response({'status': 'left'})

        # No members left — clean up room and the system message we just created
        # (the room is going away, so the message has no audience).
        leave_msg.delete()
        room.delete()
        return Response({'status': 'left'})


class GroupChatDismissAdmin(generics.GenericAPIView):
    """POST /chat/groups/{id}/dismiss-admin/ — for the user who triggered a
    wit_bot escalation, dismiss wit_admin (and any other operators) and demote
    the room back to a 1-on-1 with the bot. Only the original user (the non-bot
    user1/user2 of the room) may call this."""
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def post(self, request, pk):
        user = request.user
        try:
            room = ChatRoom.objects.get(id=pk, is_group=True)
        except ChatRoom.DoesNotExist:
            raise exceptions.NotFound("Group not found.")

        bot, evictees = _wit_bot_escalation_evictees(room, user)
        if bot is None:
            raise exceptions.PermissionDenied(
                "This action is only available in your own wit_bot support thread."
            )

        if evictees:
            evict_msg = Message.objects.create(
                chat_room=room, sender=user, receiver=None,
                event_type='member_left',
            )
            evict_msg.event_target_users.set(evictees)
            # Notify evictees (so the room disappears from their chat list) and
            # the user (so their list shows the demoted shape).
            _broadcast_system_message(
                room, evict_msg, chat_list_recipients=evictees + [user],
            )
            for evictee in evictees:
                room.members.remove(evictee)

        room.is_group = False
        room.name = ''
        room.save(update_fields=['is_group', 'name'])
        room.members.clear()
        GroupReadCursor.objects.filter(chat_room=room).delete()

        return Response({
            'status': 'admin_dismissed',
            'redirect_user_id': bot.id,
        })


def _wit_bot_escalation_evictees(room, user):
    """If `room` is the escalated wit_bot 1-on-1 between `user` and the bot,
    return (bot_user, [members_to_evict]). Otherwise return (None, [])."""
    from chat.wit_bot import is_wit_bot
    bot = None
    if room.user1_id and is_wit_bot(room.user1) and room.user2_id == user.id:
        bot = room.user1
    elif room.user2_id and is_wit_bot(room.user2) and room.user1_id == user.id:
        bot = room.user2
    if bot is None:
        return (None, [])
    evictees = list(room.members.exclude(id__in=[user.id, bot.id]))
    return (bot, evictees)


class GroupMessageList(generics.ListCreateAPIView):
    """GET/POST /chat/groups/{id}/messages/ — list/send messages in a group."""
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user = self.request.user
        room_id = self.kwargs.get('pk')
        try:
            room = ChatRoom.objects.get(id=room_id, is_group=True)
        except ChatRoom.DoesNotExist:
            raise exceptions.NotFound("Group not found.")

        if not room.members.filter(id=user.id).exists():
            raise exceptions.PermissionDenied("You are not a member of this group.")

        return room.messages.select_related(
            'sender', 'parent', 'parent__sender'
        ).prefetch_related('reactions').all()

    def perform_create(self, serializer):
        user = self.request.user
        room_id = self.kwargs.get('pk')
        room = ChatRoom.objects.get(id=room_id, is_group=True)

        if not room.members.filter(id=user.id).exists():
            raise exceptions.PermissionDenied("You are not a member of this group.")

        # Version isolation: block if group has members on different versions
        if room.members.exclude(current_ver=user.current_ver).exists():
            raise exceptions.PermissionDenied("Cannot send messages in a group with members on different versions.")

        parent_id = self.request.data.get('parent')
        parent = None
        if parent_id:
            parent = Message.objects.filter(id=parent_id, chat_room=room).first()

        serializer.save(sender=user, receiver=None, chat_room=room, parent=parent)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)

        room_id = self.kwargs.get('pk')
        room = ChatRoom.objects.get(id=room_id, is_group=True)

        # Broadcast to group WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"chat_group_{room_id}",
            {"type": "chat.message", "data": response.data},
        )

        # Broadcast to all members' chat list (per-user unread count)
        content = _get_message_preview_text(response.data)
        timestamp = response.data.get('created_at', '')
        for member in room.members.exclude(id=request.user.id):
            cursor = GroupReadCursor.objects.filter(user=member, chat_room=room).first()
            if cursor and cursor.last_read_message:
                unread = room.messages.exclude(sender=member).filter(
                    created_at__gt=cursor.last_read_message.created_at
                ).count()
            else:
                unread = room.messages.exclude(sender=member).count()
            try:
                async_to_sync(channel_layer.group_send)(
                    f"user_{member.id}_chat_list",
                    {
                        "type": "chat.list.update",
                        "data": {
                            "room_id": int(room_id),
                            "is_group": True,
                            "group_name": room.name,
                            "last_message": content,
                            "last_message_time": timestamp,
                            "unread_count": unread,
                        },
                    },
                )
            except Exception:
                pass

        return response


class OnboardingEventCreate(generics.CreateAPIView):
    """Frontend mirror of Firebase Analytics events for the wit_bot audit.

    POST /api/chat/onboarding-events/
    {
        "event_key": "browse_mode_toggled",
        "payload": {"new_state": "social"}  # optional
    }

    Server fills `user` (from session) and `version` (from user.current_ver).
    Fire-and-forget; returns 201 with the created row.
    """
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        event_key = request.data.get('event_key')
        if not event_key or not isinstance(event_key, str):
            return Response(
                {'error': 'event_key is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = request.data.get('payload', {}) or {}
        if not isinstance(payload, dict):
            return Response(
                {'error': 'payload must be an object'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        OnboardingEvent.objects.create(
            user=request.user,
            version=request.user.current_ver,
            event_key=event_key[:64],
            payload=payload,
        )
        return Response({'ok': True}, status=status.HTTP_201_CREATED)
