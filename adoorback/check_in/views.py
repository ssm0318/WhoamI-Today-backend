from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import generics, exceptions, pagination, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from adoorback.utils.validators import adoor_exception_handler

from account.serializers import serialize_check_in_base_for_viewer

from check_in.models import CheckIn, CheckInComponentEntry, CheckInPost, Song, Poke
from reaction.models import Reaction
from reaction.serializers import ReactionSerializer
import check_in.serializers as cs

User = get_user_model()


CHECKIN_AUTO_ARCHIVE_HOURS = 12


def _archive_filter(user):
    """Queryset filter for the OP's archive view.

    An entry is "archived" (belongs in the feed) when it is no longer live —
    i.e. either it has been superseded by a newer entry for the same
    (owner, component), or its created_at is older than the 12h auto-archive
    window. This mirrors the visibility collapse in CheckInBaseSerializer.
    """
    threshold = timezone.now() - timedelta(hours=CHECKIN_AUTO_ARCHIVE_HOURS)
    return CheckInComponentEntry.objects.filter(owner=user).filter(
        Q(superseded_at__isnull=False) | Q(created_at__lt=threshold)
    )


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


def notify_check_in_subscribers(check_in):
    """Send notifications to check-in subscribers (version_w only, 5-min batching)."""
    from adoorback.utils.content_types import get_check_in_type
    from notification.models import Notification, NotificationActor
    from account.models import Subscription

    user = check_in.user
    if user.current_ver != 'version_w':
        return

    check_in_ct = get_check_in_type()
    subscriber_ids = list(Subscription.objects.filter(
        subscribed_to=user, content_type=check_in_ct
    ).values_list('subscriber_id', flat=True))

    if not subscriber_ids:
        return

    blocked_ids = user.user_report_blocked_ids

    for subscriber_id in subscriber_ids:
        if subscriber_id in blocked_ids:
            continue

        recent_noti = _find_recent_check_in_noti(subscriber_id, user)

        if recent_noti:
            recent_noti.notification_updated_at = timezone.now()
            recent_noti.target = check_in
            recent_noti.save()
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
                has_song = Song.objects.filter(user=current_user, is_active=True).exists()
                if _has_visible_content(existing_checkin, has_song):
                    notify_check_in_subscribers(existing_checkin)
        else:
            # Create new check-in
            serializer.save(user=current_user, is_active=True)
            has_song = Song.objects.filter(user=current_user, is_active=True).exists()
            if _has_visible_content(serializer.instance, has_song):
                notify_check_in_subscribers(serializer.instance)

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
        Used when user views a friend's check-in.
        '''
        current_user = self.request.user
        instance = self.get_object()
        instance.readers.add(current_user)
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


def _is_live_entry(entry):
    """True when the entry is still the live component value for its owner."""
    if entry.superseded_at is not None:
        return False
    return timezone.now() - entry.created_at <= timedelta(hours=CHECKIN_AUTO_ARCHIVE_HOURS)


class ArchiveEntryPinToggle(APIView):
    """PATCH /api/check_in/entries/<pk>/pin/

    Body: none (toggles current pin state). When turning the pin ON the
    entry's current `visibility` — the value the owner explicitly chose
    at save time, not the auto-downgraded only_me — is copied into
    `pin_visibility`. When turning OFF, `pin_visibility` is cleared.
    """
    permission_classes = [IsAuthenticated]

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

    Soft-deletes an archived entry via SafeDeleteModel (matches the rest
    of the codebase). Live entries — superseded_at IS NULL AND created_at
    within the 12h window — are rejected with 400 so the mutation can
    only retire rows that have already aged out or been displaced.
    """
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def delete(self, request, pk):
        entry = _get_own_entry_or_404(request.user, pk)
        if _is_live_entry(entry):
            return Response(
                {'detail': 'Live entries cannot be deleted from the archive.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        entry.delete()  # SafeDeleteModel soft-delete (sets `deleted` timestamp)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ArchiveLiveComponent(APIView):
    """PATCH /api/check_in/components/<component>/archive/

    Archive the user's currently-live entry for `component` without
    replacing it with new content. The component's value on the active
    CheckIn is cleared (or, for `song`, the active Song row is
    deactivated), which routes through the existing CheckIn.save /
    Song post_save diff logic and stamps `superseded_at` on the live
    CheckInComponentEntry. Friend cards immediately show the empty
    placeholder for that component, and the archived entry surfaces
    under "Today" in the owner's archive feed (eligible for pinning).

    Idempotent at the entry level: a 404 is returned when the
    component has no live value to archive.
    """
    permission_classes = [IsAuthenticated]
    ALLOWED = ('battery', 'mood', 'thought', 'song')

    def get_exception_handler(self):
        return adoor_exception_handler

    @transaction.atomic
    def patch(self, request, component):
        if component not in self.ALLOWED:
            return Response(
                {'detail': f'component must be one of {list(self.ALLOWED)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user

        if component == 'song':
            active_songs = list(Song.objects.filter(user=user, is_active=True))
            if not active_songs:
                return Response(
                    {'detail': 'No active song to archive.'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            for song in active_songs:
                song.is_active = False
                song.save()  # post_save signal supersedes the live song entry
            return Response({'archived': component}, status=status.HTTP_200_OK)

        check_in = CheckIn.objects.filter(user=user, is_active=True).first()
        if not check_in:
            return Response(
                {'detail': 'No active check-in.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if component == 'battery':
            if not check_in.social_battery:
                return Response(
                    {'detail': 'No active battery to archive.'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            check_in.social_battery = None
        elif component == 'mood':
            if not check_in.mood:
                return Response(
                    {'detail': 'No active mood to archive.'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            check_in.mood = []
        elif component == 'thought':
            if not check_in.thought:
                return Response(
                    {'detail': 'No active thought to archive.'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            check_in.thought = ''

        check_in.save()  # diff path supersedes the matching live entry
        return Response({'archived': component}, status=status.HTTP_200_OK)


class OwnArchiveEntries(generics.ListAPIView):
    """GET /check_in/entries/?tab=all|pinned&cursor=...

    Owner-only archive feed of per-component entries. Excludes live entries
    (superseded_at IS NULL AND created_at within the 12h window). The flat
    list is ordered newest-first; the frontend groups by `created_at` date
    to render the section headers (Today / Yesterday / Mar 12 / …). The
    top-level response augments the default paginated payload with
    `pinned_count` (OP's total pinned archived entries) and
    `archived_count` (total archived rows, unfiltered by tab) so the
    `[ All (N) | Pinned (M) ]` segmented control can render without a
    second request.
    """
    serializer_class = cs.ArchiveEntrySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = ArchiveCursorPagination

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user = self.request.user
        qs = _archive_filter(user)
        tab = self.request.query_params.get('tab', 'all')
        if tab == 'pinned':
            qs = qs.filter(is_pinned=True)
        return qs.order_by('-id')

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        user = request.user
        archived_qs = _archive_filter(user)
        response.data['archived_count'] = archived_qs.count()
        response.data['pinned_count'] = archived_qs.filter(is_pinned=True).count()
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

        serializer.save(user=current_user, is_active=True)

        # deactivate previous song
        previous_song = Song.objects.filter(user=current_user, is_active=True) \
                                    .exclude(id=serializer.instance.id).first()
        if previous_song:
            previous_song.is_active = False
            previous_song.save()

        # Mirror the song change to the active check-in's song_updated_at so the
        # auto-archive logic (>12h) doesn't hide the just-saved song. Use update()
        # to bypass CheckIn.save()'s per-field timestamp logic.
        CheckIn.objects.filter(user=current_user, is_active=True) \
                       .update(song_updated_at=timezone.now())

        # Notify check-in subscribers about song change
        active_check_in = CheckIn.objects.filter(user=current_user, is_active=True).first()
        if active_check_in:
            notify_check_in_subscribers(active_check_in)

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

        # Mirror the song removal to the active check-in's song_updated_at so the
        # auto-archive logic stays consistent with the song state.
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

        # Check daily poke limit
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        sent_today = Poke.objects.filter(sender=sender, created_at__gte=today_start).count()
        if sent_today >= Poke.DAILY_POKE_LIMIT:
            raise exceptions.Throttled(detail="Daily poke limit reached.")

        # Check duplicate: same sender->receiver->component_type today
        component_type = serializer.validated_data.get('component_type')
        already_poked = Poke.objects.filter(
            sender=sender,
            receiver=receiver,
            component_type=component_type,
            created_at__gte=today_start,
        ).exists()
        if already_poked:
            raise exceptions.ValidationError("You already poked this component today.")

        serializer.save(sender=sender, receiver=receiver)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PokeSent(generics.ListAPIView):
    """
    Get pokes sent by the current user to a specific receiver today.
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
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return Poke.objects.filter(
            sender=sender,
            receiver_id=receiver_id,
            created_at__gte=today_start,
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

    @transaction.atomic
    def post(self, request, pk):
        try:
            check_in = CheckIn.objects.get(id=pk)
        except CheckIn.DoesNotExist:
            raise exceptions.NotFound("Check-in not found.")

        if not check_in.is_active:
            raise exceptions.PermissionDenied("This check-in is no longer active.")

        if not check_in.is_audience(request.user):
            raise exceptions.PermissionDenied("You cannot interact with this check-in.")

        emoji = request.data.get('emoji')
        if not emoji:
            raise exceptions.ValidationError("emoji is required.")

        content_type = ContentType.objects.get_for_model(CheckIn)

        existing = Reaction.objects.filter(
            user=request.user,
            emoji=emoji,
            content_type=content_type,
            object_id=pk,
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
        return Reaction.objects.filter(
            content_type=content_type,
            object_id=pk,
        ).exclude(user_id__in=blocked_ids).order_by('-created_at')


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
        connected_ids = list(user.connected_user_ids)
        close_visible_author_ids = _authors_who_marked_user_close_friend(user)
        blocked_ids = user.user_report_blocked_ids

        qs = CheckInPost.objects.filter(
            author_id__in=connected_ids + [user.id],
        ).exclude(author_id__in=blocked_ids)

        return qs.filter(
            Q(visibility='friends') |
            Q(visibility='close_friends', author_id__in=close_visible_author_ids) |
            Q(author=user)
        ).order_by('-created_at')

    def perform_create(self, serializer):
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

        if not viewer.is_connected(target):
            return CheckInPost.objects.none()

        if hasattr(viewer, 'is_close_friend') and viewer.is_close_friend(target):
            return qs.order_by('-created_at')

        return qs.filter(visibility='friends').order_by('-created_at')


class CheckInPostStories(generics.ListAPIView):
    """Compact stories strip — one row per friend with at least one viewer-visible
    CheckInPost, ordered by recent activity. Returns latest post per author."""
    permission_classes = [IsAuthenticated]
    serializer_class = cs.CheckInPostFriendStorySerializer

    def get_exception_handler(self):
        return adoor_exception_handler

    def get_queryset(self):
        user = self.request.user
        connected_ids = list(user.connected_user_ids)
        close_visible_author_ids = _authors_who_marked_user_close_friend(user)
        blocked_ids = user.user_report_blocked_ids

        author_ids = [uid for uid in connected_ids + [user.id] if uid not in blocked_ids]

        qs = CheckInPost.objects.filter(author_id__in=author_ids).filter(
            Q(visibility='friends') |
            Q(visibility='close_friends', author_id__in=close_visible_author_ids) |
            Q(author=user)
        )

        # Latest post per author
        latest_ids = (
            qs.order_by('author_id', '-created_at')
              .distinct('author_id')
              .values_list('id', flat=True)
        )
        return CheckInPost.objects.filter(id__in=list(latest_ids)).order_by('-created_at')
