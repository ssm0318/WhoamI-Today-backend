from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import generics, exceptions, pagination, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from adoorback.utils.validators import adoor_exception_handler
from adoorback.utils.video import validate_video_file, generate_video_thumbnail
from adoorback.utils.publishing import ensure_can_publish

from account.serializers import serialize_check_in_base_for_viewer, viewer_sees_check_in_component

from check_in.models import (
    CHECK_IN_POST_EXPIRY_HOURS,
    CheckIn,
    CheckInComponentEntry,
    CheckInPost,
    PrivateAcknowledgment,
    Song,
    Poke,
    mark_check_in_read,
)
from reaction.models import Reaction
from reaction.serializers import ReactionSerializer
import check_in.serializers as cs

User = get_user_model()


def _history_filter(user):
    """Queryset filter for the owner's history view.

    Returns all entries for the user — both live (superseded_at IS NULL)
    and superseded — so the history feed shows every past and current
    check-in component.
    """
    return CheckInComponentEntry.objects.filter(owner=user)


class ArchiveCursorPagination(pagination.CursorPagination):
    """Cursor-paginated feed for the archive endpoint.

    Ordering by `-id` rather than `-created_at` so the cursor value is
    guaranteed unique (CursorPagination requires strict ordering). For
    append-only entry rows the id order matches the chronological order
    — including the backfilled rows, since they were bulk_create'd in
    ascending created_at order.
    """
    page_size = 20
    ordering = '-id'
    cursor_query_param = 'cursor'


# --- Check-in subscription notification helpers ---

CONTENT_FIELDS = ('mood', 'social_battery', 'thought')


def _has_visible_content(check_in, has_active_song=False):
    """Check if the check-in has any non-empty user-visible content."""
    return (
        bool(check_in.mood)
        or bool(check_in.social_battery)
        or bool(check_in.thought)
        or has_active_song
    )


# content field → (visibility_field, updated_at_field)
CONTENT_TO_VISIBILITY = {
    'social_battery': ('battery_visibility', 'battery_updated_at'),
    'mood': ('mood_visibility', 'mood_updated_at'),
    'thought': ('thought_visibility', 'thought_updated_at'),
    'song': ('song_visibility', 'song_updated_at'),
}

# content field → subscription_type
CONTENT_TO_SUB_TYPE = {
    'social_battery': 'battery',
    'mood': 'mood',
    'thought': 'thought',
    'song': 'song',
}


def _subscriber_sees_changed_component(check_in, subscriber, changed_components):
    """Return True if subscriber can see at least one of the changed components."""
    for component in changed_components:
        vis_field, updated_field = CONTENT_TO_VISIBILITY[component]
        if viewer_sees_check_in_component(check_in, check_in.user, subscriber, vis_field, updated_field):
            return True
    return False


def notify_check_in_subscribers(check_in, changed_components=None):
    """Send notifications to check-in subscribers (version_w only, 5-min batching).

    changed_components: list of component names that changed (e.g. ['mood', 'social_battery']).
                        If None, treats all components as changed (new check-in).
    """
    from adoorback.utils.content_types import get_check_in_type
    from notification.models import Notification, NotificationActor, notify_firebase
    from account.models import Subscription

    if changed_components is None:
        changed_components = list(CONTENT_TO_VISIBILITY.keys())

    user = check_in.user
    if user.current_ver != 'version_w':
        return

    check_in_ct = get_check_in_type()
    # 변경된 컴포넌트에 해당하는 subscription_type으로 필터
    sub_types = [CONTENT_TO_SUB_TYPE[c] for c in changed_components if c in CONTENT_TO_SUB_TYPE]
    subscriber_ids = list(set(Subscription.objects.filter(
        subscribed_to=user, content_type=check_in_ct, subscription_type__in=sub_types,
    ).values_list('subscriber_id', flat=True)))

    if not subscriber_ids:
        return

    blocked_ids = user.user_report_blocked_ids
    subscribers = User.objects.in_bulk(subscriber_ids)

    for subscriber_id in subscriber_ids:
        if subscriber_id in blocked_ids:
            continue

        subscriber = subscribers.get(subscriber_id)
        if not subscriber:
            continue

        # 변경된 컴포넌트 중 구독자가 볼 수 있는 게 없으면 알림 X
        if not _subscriber_sees_changed_component(check_in, subscriber, changed_components):
            continue

        recent_noti = _find_recent_check_in_noti(subscriber_id, user)

        if recent_noti:
            # .update()로 post_save signal 우회 — 중복 push 방지
            check_in_ct_model = ContentType.objects.get_for_model(check_in)
            Notification.objects.filter(pk=recent_noti.pk).update(
                notification_updated_at=timezone.now(),
                target_id=check_in.pk,
                target_type=check_in_ct_model,
            )
            # push는 1회만 직접 발송 (signal 우회했으므로)
            recent_noti.refresh_from_db()
            notify_firebase(recent_noti)
        else:
            noti = Notification.objects.create(
                user_id=subscriber_id,
                origin=user,
                target=check_in,
                message_ko=f"{user.username}님이 체크인을 업데이트했습니다!",
                message_en=f"{user.username} updated their check-in!",
                redirect_url=f"/users/{user.username}",
            )
            NotificationActor.objects.create(user=user, notification=noti)


def _find_recent_check_in_noti(subscriber_id, actor):
    """Find a recent (within 5 min) unread check-in notification from this actor."""
    from notification.models import Notification

    cutoff = timezone.now() - timezone.timedelta(minutes=5)
    check_in_ct = ContentType.objects.get_for_model(CheckIn)
    return Notification.objects.filter(
        user_id=subscriber_id,
        actors__in=[actor],
        target_type=check_in_ct,
        is_read=False,
        is_visible=True,
        notification_updated_at__gte=cutoff,
    ).order_by('-notification_updated_at').first()


# check-in 필드명 → Poke.component_type 역매핑
POKE_COMPONENT_TO_CONTENT = {
    'battery': 'social_battery',
    'mood': 'mood',
    'thought': 'thought',
    'song': 'song',
}

POKE_COMPONENT_LABELS_KO = {
    'song': '노래',
    'mood': '기분',
    'thought': '한마디',
    'battery': '소셜 배터리',
}
POKE_COMPONENT_LABELS_EN = {
    'song': 'song',
    'mood': 'mood',
    'thought': 'thought snippet',
    'battery': 'social battery',
}


def notify_poke_senders(check_in, changed_components):
    """핑 발신자에게 응답 알림 전송 (version_w only, 첫 번째 응답에만).

    changed_components: check-in 필드명 리스트 (예: ['mood', 'social_battery'])
    """
    from notification.models import Notification, NotificationActor
    from account.models import Subscription
    from adoorback.utils.content_types import get_check_in_type

    user = check_in.user
    if user.current_ver != 'version_w':
        return

    changed_poke_types = [
        poke_type for poke_type, content_field in POKE_COMPONENT_TO_CONTENT.items()
        if content_field in changed_components
    ]
    if not changed_poke_types:
        return

    blocked_ids = user.user_report_blocked_ids
    check_in_ct = get_check_in_type()

    pending_pokes = Poke.objects.filter(
        receiver=user,
        component_type__in=changed_poke_types,
        responded_at__isnull=True,
    ).select_related('sender')

    now = timezone.now()
    for poke in pending_pokes:
        sender = poke.sender

        # 첫 응답으로 마크 — 이후 업로드에서 재발동 방지
        Poke.objects.filter(pk=poke.pk).update(responded_at=now)

        if sender.id in blocked_ids:
            continue

        # A가 이미 B의 해당 컴포넌트를 구독 중이면 구독 알림이 따로 가므로 생략
        if Subscription.objects.filter(
            subscriber=sender,
            subscribed_to=user,
            content_type=check_in_ct,
            subscription_type=poke.component_type,
        ).exists():
            continue

        content_field = POKE_COMPONENT_TO_CONTENT[poke.component_type]
        vis_field, updated_field = CONTENT_TO_VISIBILITY[content_field]
        if not viewer_sees_check_in_component(check_in, user, sender, vis_field, updated_field):
            continue

        label_ko = POKE_COMPONENT_LABELS_KO[poke.component_type]
        label_en = POKE_COMPONENT_LABELS_EN[poke.component_type]

        noti = Notification.objects.create(
            user=sender,
            origin=user,
            target=poke,
            message_ko=f"{user.username}님이 회원님의 핑에 응답해서 {label_ko}을(를) 업데이트했어요!",
            message_en=f"{user.username} updated their {label_en} in response to your ping!",
            redirect_url=f"/users/{user.username}",
        )
        NotificationActor.objects.create(user=user, notification=noti)


class CurrentCheckIn(generics.ListCreateAPIView):
    """
    Get current active check-in of request user or create a new check-in.
    """
    serializer_class = cs.MyCheckInSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        current_user = self.request.user
        ensure_can_publish(current_user)

        # Check if there's an active check-in
        existing_checkin = CheckIn.objects.filter(
            user=current_user,
            is_active=True
        ).first()

        if existing_checkin:
            # Snapshot content before update
            old_content = {f: getattr(existing_checkin, f) for f in CONTENT_FIELDS}

            # Update existing check-in
            for field, value in serializer.validated_data.items():
                setattr(existing_checkin, field, value)
            existing_checkin.save()
            serializer.instance = existing_checkin

            # Notify only if content actually changed and result is non-empty
            new_content = {f: getattr(existing_checkin, f) for f in CONTENT_FIELDS}
            if old_content != new_content:
                changed = [f for f in CONTENT_FIELDS if old_content[f] != new_content[f]]
                has_song = Song.objects.filter(user=current_user, is_active=True).exists()
                if _has_visible_content(existing_checkin, has_song):
                    notify_check_in_subscribers(existing_checkin, changed_components=changed)
                notify_poke_senders(existing_checkin, changed_components=changed)
        else:
            # Create new check-in
            serializer.save(user=current_user, is_active=True)
            has_song = Song.objects.filter(user=current_user, is_active=True).exists()
            if _has_visible_content(serializer.instance, has_song):
                notify_check_in_subscribers(serializer.instance)
            notify_poke_senders(serializer.instance, changed_components=list(CONTENT_TO_VISIBILITY.keys()))

        return Response(serializer.data)

    def get_queryset(self):
        current_user = self.request.user
        return CheckIn.objects.filter(user=current_user, is_active=True)


class CheckInDetail(generics.RetrieveUpdateAPIView):
    """
    Get a specific check-in, or update a check-in.
    """
    queryset = CheckIn.objects.all()
    serializer_class = cs.MyCheckInSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler
    
    def get_object(self):
        try:
            check_in = CheckIn.objects.get(id=self.kwargs.get('pk'))
        except CheckIn.DoesNotExist:
            raise exceptions.NotFound("Check-in not found.")
        if not check_in.is_active:
            raise exceptions.PermissionDenied("This check-in has been edited or deleted.")
        if self.request.user != check_in.user:
            raise exceptions.PermissionDenied("Only the author can access check-in details.")
        return check_in

    def patch(self, request, *args, **kwargs):
        '''
        Used when user deletes a check-in, which makes the is_active field of check-in False.
        '''
        instance = self.get_object()
        instance.is_active = False
        instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CheckInRead(generics.UpdateAPIView):
    queryset = CheckIn.objects.all()
    serializer_class = cs.CheckInBaseSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        try:
            check_in = CheckIn.objects.get(id=self.kwargs.get('pk'))
        except CheckIn.DoesNotExist:
            raise exceptions.NotFound("Check-in not found.")
        if not check_in.is_active:
            raise exceptions.PermissionDenied("This check-in has been edited or deleted.")
        if not check_in.is_audience(self.request.user):
            raise exceptions.PermissionDenied("You cannot access this check-in.")
        return check_in
    
    def patch(self, request, *args, **kwargs):
        '''
        Used when user views a friend's check-in. Marks the check-in as read
        in BOTH the legacy `CheckIn.readers` M2M (preserved for the all-content
        `current_user_read` flag and the unread-counts logic) and the new
        per-(user, check_in) `CheckInRead` table whose `read_at` timestamp
        drives the per-component [UP] badge.
        '''
        current_user = self.request.user
        instance = self.get_object()
        instance.readers.add(current_user)
        mark_check_in_read(current_user, instance)
        data = serialize_check_in_base_for_viewer(instance, request)
        return Response(data, status=status.HTTP_200_OK)


def _get_own_entry_or_404(user, pk):
    """Fetch a CheckInComponentEntry scoped to the current user.

    Other users' entries (and deleted rows) come back as 404 rather than
    403 so the endpoint does not leak the existence of foreign rows.
    """
    try:
        return CheckInComponentEntry.objects.get(pk=pk, owner=user)
    except CheckInComponentEntry.DoesNotExist:
        raise exceptions.NotFound("Entry not found.")



class ArchiveEntryPinToggle(APIView):
    """PATCH /api/check_in/entries/<pk>/pin/

    Body (optional): {"pin_visibility": "public|friends|close_friends|only_me"}

    Toggles current pin state. When turning the pin ON, uses
    client-supplied `pin_visibility` if provided, otherwise falls back
    to the entry's original `visibility`. When turning OFF,
    `pin_visibility` is cleared.
    """
    permission_classes = [IsAuthenticated]

    ALLOWED_VISIBILITY = {'public', 'friends', 'close_friends', 'only_me'}

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def patch(self, request, pk):
        entry = _get_own_entry_or_404(request.user, pk)
        if entry.is_pinned:
            entry.is_pinned = False
            entry.pin_visibility = None
        else:
            entry.is_pinned = True
            requested_vis = request.data.get('pin_visibility')
            if requested_vis and requested_vis in self.ALLOWED_VISIBILITY:
                entry.pin_visibility = requested_vis
            else:
                entry.pin_visibility = entry.visibility
        entry.save(update_fields=['is_pinned', 'pin_visibility', 'updated_at'])
        return Response(
            cs.ArchiveEntrySerializer(entry).data,
            status=status.HTTP_200_OK,
        )


class ArchiveEntryPinVisibility(APIView):
    """PATCH /api/check_in/entries/<pk>/pin_visibility/

    Body: {"pin_visibility": "public|friends|close_friends|only_me"}

    Updates only the pin's independent visibility. Entries must already
    be pinned; otherwise 400 so clients can't silently set a value that
    has no effect.
    """
    permission_classes = [IsAuthenticated]

    ALLOWED = {'public', 'friends', 'close_friends', 'only_me'}

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def patch(self, request, pk):
        entry = _get_own_entry_or_404(request.user, pk)
        if not entry.is_pinned:
            return Response(
                {'detail': 'Entry is not pinned.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        value = request.data.get('pin_visibility')
        if value not in self.ALLOWED:
            return Response(
                {'detail': f'pin_visibility must be one of {sorted(self.ALLOWED)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        entry.pin_visibility = value
        entry.save(update_fields=['pin_visibility', 'updated_at'])
        return Response(
            cs.ArchiveEntrySerializer(entry).data,
            status=status.HTTP_200_OK,
        )


class ArchiveEntryDelete(APIView):
    """DELETE /api/check_in/entries/<pk>/

    Soft-deletes a history entry via SafeDeleteModel (matches the rest
    of the codebase). All entries — both live and superseded — can be
    deleted from the history feed.
    """
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def delete(self, request, pk):
        entry = _get_own_entry_or_404(request.user, pk)
        entry.delete()  # SafeDeleteModel soft-delete (sets `deleted` timestamp)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PrivateAcknowledgmentToggle(APIView):
    """PATCH /api/check_in/entries/<pk>/acknowledge/

    Toggle a private acknowledgment on a friend's pinned CheckInComponentEntry.
    Creates on first call, soft-deletes on second (toggle). Returns the new
    state so the frontend can update optimistically.
    """
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def patch(self, request, pk):
        entry = get_object_or_404(CheckInComponentEntry, pk=pk, is_pinned=True)
        viewer = request.user

        if entry.owner == viewer:
            raise exceptions.PermissionDenied("Cannot acknowledge your own entry.")

        existing = PrivateAcknowledgment.objects.filter(entry=entry, user=viewer).first()
        if existing:
            existing.delete()
            acknowledged = False
        else:
            PrivateAcknowledgment.objects.create(entry=entry, user=viewer)
            acknowledged = True

        count = PrivateAcknowledgment.objects.filter(entry=entry).count()
        return Response({'acknowledged': acknowledged, 'count': count})


class ArchiveEntryPrivateComments(generics.ListAPIView):
    """GET /api/check_in/entries/<pk>/private-comments/

    List private comments between the current viewer and the entry owner on a
    pinned CheckInComponentEntry. Only top-level comments are returned here;
    replies are fetched via the existing comment reply endpoint.
    """
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_serializer_class(self):
        from comment.serializers import CommentFriendSerializer
        return CommentFriendSerializer

    def get_queryset(self):
        from comment.models import Comment

        pk = self.kwargs.get('pk')
        viewer = self.request.user

        # Owner can access any entry (pinned or not); friends only see pinned entries.
        entry = get_object_or_404(CheckInComponentEntry, pk=pk)
        owner = entry.owner

        if viewer == owner:
            # Owner sees every private comment on their own entry.
            entry_ct = ContentType.objects.get_for_model(CheckInComponentEntry)
            return Comment.objects.filter(
                content_type=entry_ct,
                object_id=entry.pk,
                is_private=True,
            ).order_by('created_at')

        if not entry.is_pinned:
            raise exceptions.PermissionDenied("You cannot view private comments on this entry.")
        if not owner.is_connected(viewer):
            raise exceptions.PermissionDenied("You cannot view private comments on this entry.")

        participant_ids = {viewer.id, owner.id}
        entry_ct = ContentType.objects.get_for_model(CheckInComponentEntry)

        return Comment.objects.filter(
            content_type=entry_ct,
            object_id=entry.pk,
            is_private=True,
            author_id__in=participant_ids,
        ).order_by('created_at')


class ArchiveEntryAcknowledgments(generics.ListAPIView):
    """GET /api/check_in/entries/<pk>/acknowledgments/

    Returns the list of users who have privately acknowledged a pinned entry.
    Only the entry owner may call this endpoint.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_serializer_class(self):
        from account.serializers import UserMinimalSerializer
        return UserMinimalSerializer

    def get_queryset(self):
        entry = get_object_or_404(CheckInComponentEntry, pk=self.kwargs['pk'])
        viewer = self.request.user
        if viewer != entry.owner:
            raise exceptions.PermissionDenied("Only the entry owner can view acknowledgments.")
        return User.objects.filter(private_acknowledgments__entry=entry)


class OwnHistoryEntries(generics.ListAPIView):
    """GET /check_in/entries/?tab=all|pinned&cursor=...

    Owner-only history feed of per-component entries. Includes all
    entries — both live (current) and superseded (past). The flat list
    is ordered newest-first; the frontend groups by `created_at` date
    to render the section headers (Today / Yesterday / Mar 12 / …). The
    top-level response augments the default paginated payload with
    `pinned_count` and `history_count` so the segmented control can
    render without a second request.
    """
    serializer_class = cs.OwnerArchiveEntrySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = ArchiveCursorPagination

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user = self.request.user
        qs = _history_filter(user)
        tab = self.request.query_params.get('tab', 'all')
        if tab == 'pinned':
            qs = qs.filter(is_pinned=True)
        return qs.order_by('-id')

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        user = request.user
        history_qs = _history_filter(user)
        response.data['history_count'] = history_qs.count()
        response.data['archived_count'] = history_qs.count()  # backward compat
        response.data['pinned_count'] = history_qs.filter(is_pinned=True).count()
        return response


class CurrentUserLatestCheckInVisibility(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get(self, request):
        user = request.user
        latest_check_in = CheckIn.objects.filter(user=user).order_by('-created_at').first()

        if latest_check_in:
            return Response({'visibility': latest_check_in.visibility}, status=status.HTTP_200_OK)
        else:
            return Response({'visibility': ['public']}, status=status.HTTP_200_OK)


class LatestCheckIn(generics.RetrieveAPIView):
    """
    Get the most recent check-in of request user (regardless of is_active).
    Used to pre-fill the create check-in form.
    """
    serializer_class = cs.MyCheckInSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get(self, request):
        latest = CheckIn.objects.filter(user=request.user).order_by('-created_at').first()
        if latest:
            serializer = self.get_serializer(latest)
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response({}, status=status.HTTP_200_OK)


class CurrentSong(generics.ListCreateAPIView):
    """
    Get current active song of request user or create a new song.
    """
    serializer_class = cs.MySongSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        current_user = self.request.user
        ensure_can_publish(current_user)

        # 같은 track_id의 active song이 이미 있으면 skip
        new_track_id = serializer.validated_data.get('track_id', '')
        existing_song = Song.objects.filter(user=current_user, is_active=True).first()
        if existing_song and existing_song.track_id == new_track_id:
            serializer.instance = existing_song
            return Response(serializer.data)

        serializer.save(user=current_user, is_active=True)

        # deactivate previous song
        previous_song = Song.objects.filter(user=current_user, is_active=True) \
                                    .exclude(id=serializer.instance.id).first()
        if previous_song:
            previous_song.is_active = False
            previous_song.save()

        # Mirror the song change to the active check-in's song_updated_at.
        # Use update() to bypass CheckIn.save()'s per-field timestamp logic.
        CheckIn.objects.filter(user=current_user, is_active=True) \
                       .update(song_updated_at=timezone.now())

        # Notify check-in subscribers about song change
        active_check_in = CheckIn.objects.filter(user=current_user, is_active=True).first()
        if active_check_in:
            notify_check_in_subscribers(active_check_in, changed_components=['song'])
            notify_poke_senders(active_check_in, changed_components=['song'])

        return Response(serializer.data)

    def get_queryset(self):
        current_user = self.request.user
        return Song.objects.filter(user=current_user, is_active=True)


class SongDetail(generics.RetrieveUpdateAPIView):
    """
    Get a specific song, or deactivate a song.
    """
    queryset = Song.objects.all()
    serializer_class = cs.MySongSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        try:
            song = Song.objects.get(id=self.kwargs.get('pk'))
        except Song.DoesNotExist:
            raise exceptions.NotFound("Song not found.")
        if not song.is_active:
            raise exceptions.PermissionDenied("This song has been edited or deleted.")
        if self.request.user != song.user:
            raise exceptions.PermissionDenied("Only the author can access song details.")
        return song

    def patch(self, request, *args, **kwargs):
        '''
        Used when user deletes a song, which makes the is_active field of song False.
        '''
        instance = self.get_object()
        instance.is_active = False
        instance.save()

        # Mirror the song removal to the active check-in's song_updated_at.
        CheckIn.objects.filter(user=request.user, is_active=True) \
                       .update(song_updated_at=timezone.now())

        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PokeCreate(generics.CreateAPIView):
    """
    Create a poke (ping) to ask a friend to share a component.
    POST body: { receiver_id, component_type }
    """
    serializer_class = cs.PokeSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def perform_create(self, serializer):
        sender = self.request.user
        receiver_id = serializer.validated_data.pop('receiver_id')
        receiver = get_object_or_404(User, id=receiver_id)

        if sender == receiver:
            raise exceptions.ValidationError("You cannot poke yourself.")

        # Version isolation
        if sender.current_ver != receiver.current_ver:
            raise exceptions.PermissionDenied("Cannot poke a user on a different version.")

        # One pending ping per (sender, receiver, component_type). The previous
        # `created_at__gte=today_start` check used UTC midnight, so pings made
        # earlier in the user's local day got dropped from PokeSent the moment
        # UTC rolled over (5pm PT / 9am KST). Switching to `responded_at` aligns
        # with `notify_poke_senders`: a ping is "open" until the receiver shares
        # the matching component. After the receiver responds (or the sender
        # un-pings), the slot is free again.
        component_type = serializer.validated_data.get('component_type')
        already_pending = Poke.objects.filter(
            sender=sender,
            receiver=receiver,
            component_type=component_type,
            responded_at__isnull=True,
        ).exists()
        if already_pending:
            raise exceptions.ValidationError("You already pinged this component.")

        serializer.save(sender=sender, receiver=receiver)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PokeSent(generics.ListAPIView):
    """
    Get *pending* pings the current user has sent to a specific receiver — i.e.
    pings the receiver hasn't fulfilled yet (no matching component shared since
    the ping landed). Used by the friend-card PokeButton to render the
    "Pinged: <component> ✓" state.
    GET /poke/sent/?receiver_id=X
    """
    serializer_class = cs.PokeSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        sender = self.request.user
        receiver_id = self.request.query_params.get('receiver_id')
        if not receiver_id:
            raise exceptions.ValidationError("receiver_id query parameter is required.")
        # Filter by `responded_at__isnull=True` instead of a "created today"
        # window. The previous `today_start = timezone.now().replace(hour=0, ...)`
        # was UTC midnight (server settings have USE_TZ=True), which silently
        # dropped pings the user had just sent the moment UTC rolled over —
        # 5pm PT / 9am KST every day — even though the ping was still pending
        # in the DB. `notify_poke_senders` already uses the same
        # `responded_at__isnull=True` predicate to find pokes to fulfill, so
        # this lines up the read path with the write path.
        return Poke.objects.filter(
            sender=sender,
            receiver_id=receiver_id,
            responded_at__isnull=True,
        )


class PokeDelete(generics.DestroyAPIView):
    """
    Delete (un-poke) a specific poke. Only the sender can delete their own poke.
    DELETE /poke/<id>/
    """
    serializer_class = cs.PokeSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        try:
            poke = Poke.objects.get(id=self.kwargs.get('pk'))
        except Poke.DoesNotExist:
            raise exceptions.NotFound("Poke not found.")
        if self.request.user != poke.sender:
            raise exceptions.PermissionDenied("Only the sender can delete a poke.")
        return poke


class CheckInReact(APIView):
    """
    POST /api/check_in/<id>/react/
    Toggle a reaction on a check-in.
    Body: { "emoji": "..." }
    If the same user+emoji+checkin combo exists, delete it (toggle off).
    Otherwise create it.
    """
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    VALID_COMPONENTS = {'battery', 'mood', 'thought', 'song'}

    @transaction.atomic
    def post(self, request, pk):
        try:
            check_in = CheckIn.objects.get(id=pk)
        except CheckIn.DoesNotExist:
            raise exceptions.NotFound("Check-in not found.")

        # Version isolation
        if check_in.user.current_ver != request.user.current_ver:
            raise exceptions.PermissionDenied("Cannot interact with a check-in from a user on a different version.")

        if not check_in.is_active:
            raise exceptions.PermissionDenied("This check-in is no longer active.")

        if not check_in.is_audience(request.user):
            raise exceptions.PermissionDenied("You cannot interact with this check-in.")

        emoji = request.data.get('emoji')
        if not emoji:
            raise exceptions.ValidationError("emoji is required.")

        component = request.data.get('component')
        if not component or component not in self.VALID_COMPONENTS:
            raise exceptions.ValidationError("component is required and must be one of: battery, mood, thought, song.")

        content_type = ContentType.objects.get_for_model(CheckIn)

        existing = Reaction.objects.filter(
            user=request.user,
            emoji=emoji,
            content_type=content_type,
            object_id=pk,
            component=component,
        ).first()

        if existing:
            # Delete associated notifications before removing the reaction
            reaction_ct = ContentType.objects.get_for_model(type(existing))
            from notification.models import Notification
            Notification.objects.filter(
                target_type=reaction_ct,
                target_id=existing.id,
            ).delete()
            existing.delete()
            return Response({'toggled': 'off'}, status=status.HTTP_200_OK)
        else:
            reaction = Reaction.objects.create(
                user=request.user,
                emoji=emoji,
                content_type=content_type,
                object_id=pk,
                component=component,
            )
            serializer = ReactionSerializer(reaction, context={'request': request})
            return Response({**serializer.data, 'toggled': 'on'}, status=status.HTTP_201_CREATED)


class CheckInReactions(generics.ListAPIView):
    """
    GET /api/check_in/<id>/reactions/
    List all reactions on a check-in.
    """
    serializer_class = ReactionSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        pk = self.kwargs.get('pk')
        try:
            check_in = CheckIn.objects.get(id=pk)
        except CheckIn.DoesNotExist:
            raise exceptions.NotFound("Check-in not found.")

        if not check_in.is_active:
            raise exceptions.PermissionDenied("This check-in is no longer active.")

        if not check_in.is_audience(self.request.user):
            raise exceptions.PermissionDenied("You cannot access reactions for this check-in.")

        content_type = ContentType.objects.get_for_model(CheckIn)
        blocked_ids = self.request.user.user_report_blocked_ids
        qs = Reaction.objects.filter(
            content_type=content_type,
            object_id=pk,
        ).exclude(user_id__in=blocked_ids)

        component = self.request.query_params.get('component')
        if component:
            qs = qs.filter(component=component)

        return qs.order_by('-created_at')


# ---------------------------------------------------------------------------
# CheckInPost (Ver.Q image+text "check-in") views
# ---------------------------------------------------------------------------


class CheckInPostFeedPagination(pagination.PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 50


def _authors_who_marked_user_close_friend(user):
    """Authors who have marked the given user as close_friend (one-directional).

    Used to filter close_friends-visibility posts: an author's CLOSE_FRIENDS
    post is visible to the viewer iff the author has the viewer in their
    close_friend list.
    """
    from account.models import Connection
    user1_authors = Connection.objects.filter(
        user2=user, user1_choice='close_friend',
    ).values_list('user1_id', flat=True)
    user2_authors = Connection.objects.filter(
        user1=user, user2_choice='close_friend',
    ).values_list('user2_id', flat=True)
    return list(user1_authors) + list(user2_authors)


def _check_in_post_visible_filter(user):
    """Q-filter expressing what a viewer can see across all CheckInPosts.

    Three disjoint slices:
      - LIVE: created within 24h, governed by `visibility`
      - PINNED ARCHIVE: older than 24h but pinned, governed by `pin_visibility`
        (independent of original visibility — author can change after pinning)
      - SELF ARCHIVE: viewer is the author, always visible regardless of age
    """
    threshold = timezone.now() - timedelta(hours=CHECK_IN_POST_EXPIRY_HOURS)
    close_visible_author_ids = _authors_who_marked_user_close_friend(user)

    visible_live = Q(created_at__gte=threshold) & (
        Q(visibility='public') |
        Q(visibility='friends') |
        Q(visibility='close_friends', author_id__in=close_visible_author_ids)
    )
    visible_pinned = Q(created_at__lt=threshold, is_pinned=True) & (
        Q(pin_visibility='public') |
        Q(pin_visibility='friends') |
        Q(pin_visibility='close_friends', author_id__in=close_visible_author_ids)
    )
    visible_self = Q(author=user)
    return visible_live | visible_pinned | visible_self


def _get_own_post_or_404(user, pk):
    """Fetch a CheckInPost scoped to the current user.

    Other users' posts (and soft-deleted rows) come back as 404 rather than
    403 so the endpoint does not leak the existence of foreign rows.
    """
    try:
        return CheckInPost.objects.get(pk=pk, author=user)
    except CheckInPost.DoesNotExist:
        raise exceptions.NotFound("Post not found.")


class CheckInPostFeed(generics.ListCreateAPIView):
    """Feed of CheckInPosts — GET returns viewer-visible posts from connected users
    in latest-first order. POST creates a new post for the current user.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = cs.CheckInPostSerializer
    pagination_class = CheckInPostFeedPagination

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user = self.request.user
        # Filter connected users to same version
        connected_ids = list(User.objects.filter(
            id__in=user.connected_user_ids, current_ver=user.current_ver
        ).values_list('id', flat=True))
        blocked_ids = user.user_report_blocked_ids

        qs = CheckInPost.objects.filter(
            author_id__in=connected_ids + [user.id],
        ).exclude(author_id__in=blocked_ids)

        return qs.filter(_check_in_post_visible_filter(user)).order_by('-created_at')

    @transaction.atomic
    def perform_create(self, serializer):
        ensure_can_publish(self.request.user)
        video_file = self.request.FILES.get('video')
        extra_kwargs = {}

        if video_file:
            duration = validate_video_file(video_file)
            thumbnail = generate_video_thumbnail(video_file)
            extra_kwargs['video'] = video_file
            extra_kwargs['video_duration_seconds'] = duration
            instance = serializer.save(author=self.request.user, **extra_kwargs)
            if thumbnail:
                instance.video_thumbnail.save('thumbnail.jpg', thumbnail, save=True)
        else:
            serializer.save(author=self.request.user)


class CheckInPostDetail(generics.RetrieveDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = cs.CheckInPostSerializer
    queryset = CheckInPost.objects.all()

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_object(self):
        obj = get_object_or_404(CheckInPost, pk=self.kwargs.get('pk'))
        if not obj.is_audience(self.request.user):
            raise exceptions.PermissionDenied("You cannot view this check-in.")
        return obj

    def perform_destroy(self, instance):
        if instance.author != self.request.user:
            raise exceptions.PermissionDenied("You can only delete your own check-in.")
        instance.delete()


class UserCheckInPosts(generics.ListAPIView):
    """List a single user's CheckInPosts visible to the viewer."""
    permission_classes = [IsAuthenticated]
    serializer_class = cs.CheckInPostFriendStorySerializer

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        viewer = self.request.user
        target = get_object_or_404(User, id=self.kwargs.get('pk'))

        if target.id in viewer.user_report_blocked_ids:
            return CheckInPost.objects.none()

        qs = CheckInPost.objects.filter(author=target)
        if target == viewer:
            return qs.order_by('-created_at')

        if viewer.is_connected(target):
            threshold = timezone.now() - timedelta(hours=CHECK_IN_POST_EXPIRY_HOURS)
            return qs.filter(
                _check_in_post_visible_filter(viewer),
                created_at__gte=threshold,
            ).order_by('-created_at')

        # Non-friend: show only public-visibility posts if the account is public
        if target.is_public:
            threshold = timezone.now() - timedelta(hours=CHECK_IN_POST_EXPIRY_HOURS)
            return qs.filter(
                created_at__gte=threshold, visibility='public'
            ).order_by('-created_at')

        return CheckInPost.objects.none()


class CheckInPostStories(generics.ListAPIView):
    """Compact stories strip — one row per author (viewer + connected friends)
    with at least one viewer-visible CheckInPost, ordered by recent activity.
    Returns latest post per author."""
    permission_classes = [IsAuthenticated]
    serializer_class = cs.CheckInPostFriendStorySerializer

    def get_exception_handler(self):
        return adoor_exception_handler

    def _exclude_reported_posts(self, qs, user):
        from content_report.models import ContentReport

        post_ct = ContentType.objects.get_for_model(CheckInPost)
        reported_ids = ContentReport.objects.filter(
            user=user,
            content_type=post_ct,
        ).values_list('object_id', flat=True)
        return qs.exclude(id__in=reported_ids)

    def _latest_post_per_author(self, qs, user):
        # Latest post per author
        latest_ids = (
            qs.order_by('author_id', '-created_at')
              .distinct('author_id')
              .values_list('id', flat=True)
        )

        # Annotate: does this author have any live post not yet read by viewer?
        unread_by_author = qs.filter(
            author_id=OuterRef('author_id'),
        ).exclude(readers=user)
        return (
            CheckInPost.objects.filter(id__in=list(latest_ids))
            .annotate(_has_unread=Exists(unread_by_author))
            .order_by('-_has_unread', '-created_at')
        )

    def get_queryset(self):
        # Include the viewer's own latest post so the feed strip surfaces it
        # right after sharing — otherwise users have to navigate to /my to
        # confirm their post landed.
        user = self.request.user
        # Filter connected users to same version
        connected_ids = list(User.objects.filter(
            id__in=user.connected_user_ids, current_ver=user.current_ver
        ).values_list('id', flat=True))
        blocked_ids = user.user_report_blocked_ids

        author_ids = [uid for uid in connected_ids if uid not in blocked_ids]
        author_ids.append(user.id)

        # Strip is for "today's" snippets only — anything older than the
        # expiry window (incl. pinned archive entries and the viewer's own
        # older posts) is excluded. Older snippets stay reachable via /my and
        # the friend's profile archive.
        threshold = timezone.now() - timedelta(hours=CHECK_IN_POST_EXPIRY_HOURS)

        if self.request.query_params.get('visibility') == 'public':
            qs = CheckInPost.objects.filter(
                visibility='public',
                author__current_ver=user.current_ver,
                created_at__gte=threshold,
            ).exclude(
                author_id__in=blocked_ids + [user.id],
            ).exclude(
                author__is_superuser=True,
            )
            qs = self._exclude_reported_posts(qs, user)
            return self._latest_post_per_author(qs, user)

        qs = CheckInPost.objects.filter(
            author_id__in=author_ids,
            created_at__gte=threshold,
        ).filter(
            Q(author=user) | Q(visibility__in=['friends', 'close_friends']),
        ).filter(
            _check_in_post_visible_filter(user)
        )
        qs = self._exclude_reported_posts(qs, user)
        return self._latest_post_per_author(qs, user)


class CheckInPostRead(generics.UpdateAPIView):
    """PATCH /api/check_in/posts/read/  — batch-mark posts as read."""
    queryset = CheckInPost.objects.all()
    serializer_class = cs.CheckInPostFriendStorySerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def patch(self, request, *args, **kwargs):
        current_user = request.user
        ids = request.data.get('ids', [])
        queryset = CheckInPost.objects.filter(id__in=ids)
        for post in queryset:
            post.readers.add(current_user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CheckInPostComments(generics.ListAPIView):
    """GET /api/check_in/posts/<pk>/comments/

    List visible comments on a CheckInPost. Mirrors NoteComments — viewer
    must be in the post's audience, and comments authored by blocked users
    or comments the viewer reported are filtered out.
    """
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_serializer_class(self):
        from comment.serializers import CommentFriendSerializer
        return CommentFriendSerializer

    def get_queryset(self):
        from comment.models import Comment
        from content_report.models import ContentReport

        current_user = self.request.user
        post = get_object_or_404(CheckInPost, id=self.kwargs.get('pk'))
        if not post.is_audience(current_user):
            raise exceptions.PermissionDenied("You cannot view comments on this post.")

        blocked_comment_ids = ContentReport.objects.filter(
            user=current_user,
            content_type=ContentType.objects.get_for_model(Comment),
        ).values_list('object_id', flat=True)

        return post.check_in_post_comments.exclude(
            Q(id__in=blocked_comment_ids) | Q(author_id__in=current_user.user_report_blocked_ids)
        ).order_by('created_at')


class CheckInPostLikes(generics.ListAPIView):
    """GET /api/check_in/posts/<pk>/likes/

    List users who liked a CheckInPost (any user in the post audience).
    """
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_serializer_class(self):
        from like.serializers import LikeSerializer
        return LikeSerializer

    def get_queryset(self):
        current_user = self.request.user
        post = get_object_or_404(CheckInPost, id=self.kwargs.get('pk'))
        if not post.is_audience(current_user):
            raise exceptions.PermissionDenied("You cannot view likes on this post.")
        blocked_ids = current_user.user_report_blocked_ids
        return post.check_in_post_likes.exclude(
            user_id__in=blocked_ids,
        ).order_by('-created_at')


class CheckInPostPinToggle(APIView):
    """PATCH /api/check_in/posts/<pk>/pin/

    Toggles pin state on the author's own post. When turning the pin ON,
    the post's current `visibility` is copied into `pin_visibility` as the
    default highlight visibility (the author can later narrow it via
    CheckInPostPinVisibility). When turning OFF, `pin_visibility` is cleared.

    Mirrors ArchiveEntryPinToggle for CheckInComponentEntry.
    """
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def patch(self, request, pk):
        post = _get_own_post_or_404(request.user, pk)
        if post.is_pinned:
            post.is_pinned = False
            post.pin_visibility = None
        else:
            post.is_pinned = True
            post.pin_visibility = post.visibility
        post.save(update_fields=['is_pinned', 'pin_visibility', 'updated_at'])
        return Response(
            cs.CheckInPostSerializer(post, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )


class CheckInPostVisibility(APIView):
    """PATCH /api/check_in/posts/<pk>/visibility/

    Body: {"visibility": "public|friends|close_friends"}

    Updates the post's main visibility. If the post is also pinned,
    pin_visibility is updated to match.
    """
    permission_classes = [IsAuthenticated]
    ALLOWED = {'public', 'friends', 'close_friends'}

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def patch(self, request, pk):
        post = _get_own_post_or_404(request.user, pk)
        value = request.data.get('visibility')
        if value not in self.ALLOWED:
            return Response(
                {'detail': f'visibility must be one of {sorted(self.ALLOWED)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        post.visibility = value
        fields = ['visibility', 'updated_at']
        if post.is_pinned:
            post.pin_visibility = value
            fields.append('pin_visibility')
        post.save(update_fields=fields)
        return Response(
            cs.CheckInPostSerializer(post, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )


class CheckInPostPinVisibility(APIView):
    """PATCH /api/check_in/posts/<pk>/pin_visibility/

    Body: {"pin_visibility": "public|friends|close_friends"}

    Updates only the pin's independent visibility. Posts must already be
    pinned; otherwise 400 so clients can't silently set a value that has
    no effect.
    """
    permission_classes = [IsAuthenticated]

    ALLOWED = {'public', 'friends', 'close_friends'}

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def patch(self, request, pk):
        post = _get_own_post_or_404(request.user, pk)
        if not post.is_pinned:
            return Response(
                {'detail': 'Post is not pinned.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        value = request.data.get('pin_visibility')
        if value not in self.ALLOWED:
            return Response(
                {'detail': f'pin_visibility must be one of {sorted(self.ALLOWED)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        post.pin_visibility = value
        post.save(update_fields=['pin_visibility', 'updated_at'])
        return Response(
            cs.CheckInPostSerializer(post, context={'request': request}).data,
            status=status.HTTP_200_OK,
        )
