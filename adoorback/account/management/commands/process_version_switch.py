from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from account.models import VersionSwitchRequest


class Command(BaseCommand):
    help = (
        'List, approve, or reject VersionSwitchRequest entries.\n'
        '  list                — show pending requests\n'
        '  approve <REQ_ID>    — flip user.current_ver and mark approved\n'
        '  reject  <REQ_ID>    — mark rejected (user unchanged)\n'
        'Use --include-user-group to also flip user_group on approve.'
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
            user.current_ver = r.to_version
            update_fields = ['current_ver']
            if include_user_group:
                user.user_group = ('group_q_first' if r.to_version == 'version_q'
                                   else 'group_w_first')
                update_fields.append('user_group')
            user.save(update_fields=update_fields)

            r.status = 'approved'
            r.processed_at = timezone.now()
            r.save(update_fields=['status', 'processed_at'])

        self.stdout.write(self.style.SUCCESS(
            f'Approved #{r.id}: {user.username} {r.from_version} -> {user.current_ver}'
            + (f' (user_group -> {user.user_group})' if include_user_group else '')
        ))

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
