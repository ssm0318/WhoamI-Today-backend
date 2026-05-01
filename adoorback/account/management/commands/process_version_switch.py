from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

<<<<<<< Updated upstream:adoorback/account/management/commands/process_version_switch.py
from account.models import VersionSwitchRequest
=======
from safedelete.models import HARD_DELETE

from account.models import Connection, FriendRequest, Subscription, VersionSwapRequest

User = get_user_model()
>>>>>>> Stashed changes:adoorback/account/management/commands/process_version_swap.py


class Command(BaseCommand):
    help = (
        'List, approve, or reject VersionSwitchRequest entries.\n'
        '  list                — show pending requests\n'
        '  approve <REQ_ID>    — flip user.current_ver and mark approved\n'
        '  reject  <REQ_ID>    — mark rejected (user unchanged)\n'
        'Use --include-user-group to also flip user_group on approve.\n\n'
        'On approve, the following user data is HARD-DELETED before the swap:\n'
        '  • All friendships (Connection) and friend requests\n'
        '  • All subscriptions (both directions)\n'
        '  • All 1-on-1 chat rooms (+ messages); user is removed from group chats\n'
        '  • All notifications\n'
        'A welcome notification is re-sent after the swap.'
    )

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['list', 'approve', 'reject'])
        parser.add_argument('request_id', nargs='?', type=int, default=None,
                            help='VersionSwitchRequest id (required for approve/reject)')
        parser.add_argument('--include-user-group', action='store_true',
                            help='Also flip user_group when approving '
                                 '(only set this if research design needs it; off by default).')

    def handle(self, *args, **opts):
        action = opts['action']
        if action == 'list':
            self._list_pending()
            return

        req_id = opts['request_id']
        if req_id is None:
            raise CommandError(f'{action} requires a request_id')

        if action == 'approve':
            self._approve(req_id, include_user_group=opts['include_user_group'])
        else:
            self._reject(req_id)

    def _list_pending(self):
        qs = (VersionSwitchRequest.objects
              .filter(status='pending')
              .select_related('user')
              .order_by('created_at'))
        if not qs.exists():
            self.stdout.write('No pending requests.')
            return
        for r in qs:
            reason = (r.reason or '').strip() or '(no reason)'
            self.stdout.write(
                f'#{r.id} | {r.user.username} | {r.from_version} -> {r.to_version} '
                f'| {r.created_at:%Y-%m-%d %H:%M} | {reason}'
            )

    def _approve(self, req_id, *, include_user_group):
        with transaction.atomic():
            try:
                r = (VersionSwitchRequest.objects
                     .select_for_update()
                     .select_related('user')
                     .get(id=req_id))
            except VersionSwitchRequest.DoesNotExist:
                raise CommandError(f'Request #{req_id} not found')

            if r.status != 'pending':
                raise CommandError(f'Request #{req_id} is already {r.status}')
            if r.user.current_ver != r.from_version:
                raise CommandError(
                    f'User current_ver ({r.user.current_ver}) does not match '
                    f'request from_version ({r.from_version}); refusing to switch.'
                )

            user = r.user

            # --- Hard-delete user data before swap ---
            self._cleanup_user_data(user)

            # --- Swap version ---
            user.current_ver = r.to_version
            user.ver_changed_at = timezone.now()
            update_fields = ['current_ver', 'ver_changed_at']
            if include_user_group:
                user.user_group = ('group_q_first' if r.to_version == 'version_q'
                                   else 'group_w_first')
                update_fields.append('user_group')
            user.save(update_fields=update_fields)

            r.status = 'approved'
            r.processed_at = timezone.now()
            r.save(update_fields=['status', 'processed_at'])

            # --- Re-send welcome notification ---
            self._send_welcome_notification(user)

        self.stdout.write(self.style.SUCCESS(
            f'Approved #{r.id}: {user.username} {r.from_version} -> {user.current_ver}'
            + (f' (user_group -> {user.user_group})' if include_user_group else '')
        ))

    def _cleanup_user_data(self, user):
        from chat.models import ChatRoom
        from notification.models import Notification

        # 1. Friendships
        conns = Connection.objects.filter(Q(user1=user) | Q(user2=user))
        conn_count = conns.count()
        conns.delete(force_policy=HARD_DELETE)

        # 2. Friend requests
        freq = FriendRequest.objects.filter(Q(requester=user) | Q(requestee=user))
        freq_count = freq.count()
        freq.delete(force_policy=HARD_DELETE)

        # 3. Subscriptions (both directions)
        subs = Subscription.objects.filter(Q(subscriber=user) | Q(subscribed_to=user))
        sub_count = subs.count()
        subs.delete(force_policy=HARD_DELETE)

        # 4. Chat rooms
        # 1-on-1: hard delete (messages cascade via DB FK)
        dm_rooms = ChatRoom.objects.filter(
            Q(user1=user) | Q(user2=user), is_group=False)
        dm_count = dm_rooms.count()
        dm_rooms.delete(force_policy=HARD_DELETE)

        # Group: remove user from members; delete room if <=1 member left
        group_rooms = list(ChatRoom.objects.filter(members=user, is_group=True))
        grp_count = len(group_rooms)
        for room in group_rooms:
            room.members.remove(user)
            if room.members.count() <= 1:
                room.delete(force_policy=HARD_DELETE)

        # 5. Notifications (received by user)
        notis = Notification.objects.filter(user=user)
        noti_count = notis.count()
        notis.delete(force_policy=HARD_DELETE)

        self.stdout.write(
            f'  Cleaned up: {conn_count} connections, {freq_count} friend requests, '
            f'{sub_count} subscriptions, {dm_count} DM rooms, '
            f'{grp_count} group rooms touched, {noti_count} notifications'
        )

    def _send_welcome_notification(self, user):
        from notification.models import Notification, NotificationActor

        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            self.stdout.write(self.style.WARNING('  No superuser found; skipped welcome notification.'))
            return

        noti = Notification.objects.create(
            user=user,
            target=admin,
            origin=admin,
            message_ko=f"{user.username}님, 보다 재밌는 후엠아이 이용을 위해 친구를 추가해보세요!",
            message_en=f"{user.username}, add your friends for a better WIT experience!",
            redirect_url='/friends/explore',
        )
        NotificationActor.objects.create(user=admin, notification=noti)

    def _reject(self, req_id):
        with transaction.atomic():
            try:
                r = VersionSwitchRequest.objects.select_for_update().get(id=req_id)
            except VersionSwitchRequest.DoesNotExist:
                raise CommandError(f'Request #{req_id} not found')
            if r.status != 'pending':
                raise CommandError(f'Request #{req_id} is already {r.status}')
            r.status = 'rejected'
            r.processed_at = timezone.now()
            r.save(update_fields=['status', 'processed_at'])

        self.stdout.write(self.style.SUCCESS(
            f'Rejected #{r.id} ({r.user.username})'
        ))
