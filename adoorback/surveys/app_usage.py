from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from account.models import FriendEvaluation, FriendRequest, Subscription
from chat.models import Message
from check_in.models import CheckInComponentEntry, CheckInPost
from comment.models import Comment
from note.models import Note
from reaction.models import Reaction
from surveys.models import PointAward
from surveys.points import app_usage_source_for_phase
from surveys.reimbursement_config import APP_USAGE_PHASE_PARTIAL_POINTS


LA_TZ = ZoneInfo('America/Los_Angeles')
PHASE_WINDOWS = {
    1: (date(2026, 5, 4), date(2026, 5, 18)),
    2: (date(2026, 5, 18), date(2026, 6, 1)),
}
CORE_KINDS = {
    'chat',
    'checkin',
    'checkinpost',
    'comment',
    'note',
    'reaction',
    'subscription',
}


@dataclass(frozen=True)
class AppUsageMetrics:
    phase: int
    active_days: int
    core_active_days: int
    first_four_days: int
    later_days: int
    event_count: int
    core_event_count: int
    points: int


def _phase_bounds(phase: int) -> tuple[datetime, datetime]:
    start, end = PHASE_WINDOWS[phase]
    return (
        datetime.combine(start, time.min, tzinfo=LA_TZ),
        datetime.combine(end, time.min, tzinfo=LA_TZ),
    )


def _la_date(value: datetime) -> date:
    return timezone.localtime(value, LA_TZ).date()


def _events_for_user(user, phase: int) -> list[tuple[datetime, str]]:
    start, end = _phase_bounds(phase)
    user_filter = {'created_at__gte': start, 'created_at__lt': end}
    events: list[tuple[datetime, str]] = []

    def add(queryset, kind: str, field: str = 'created_at'):
        events.extend((moment, kind) for moment in queryset.values_list(field, flat=True))

    add(Note.objects.filter(author=user, **user_filter), 'note')
    add(Comment.objects.filter(author=user, **user_filter), 'comment')
    add(Reaction.objects.filter(user=user, **user_filter), 'reaction')
    add(CheckInComponentEntry.objects.filter(owner=user, **user_filter), 'checkin')
    add(CheckInPost.objects.filter(author=user, **user_filter), 'checkinpost')
    add(
        Message.objects
        .filter(sender=user, **user_filter)
        .exclude(Q(chat_room__user1_id=7) | Q(chat_room__user2_id=7) | Q(chat_room__members__id=7))
        .distinct(),
        'chat',
    )
    add(FriendEvaluation.objects.filter(evaluator=user, **user_filter), 'friend_eval')
    add(FriendRequest.objects.filter(requester=user, **user_filter), 'friend_request')
    add(
        FriendRequest.objects.filter(requestee=user, accepted=True, updated_at__gte=start, updated_at__lt=end),
        'friend_accept',
        'updated_at',
    )
    add(Subscription.objects.filter(subscriber=user, **user_filter), 'subscription')
    return events


def app_usage_metrics_for_user(user, phase: int) -> AppUsageMetrics:
    events = _events_for_user(user, phase)
    start, _end = PHASE_WINDOWS[phase]
    first_four_end = start.toordinal() + 4

    all_days = {_la_date(created_at) for created_at, _kind in events}
    core_days = {_la_date(created_at) for created_at, kind in events if kind in CORE_KINDS}
    first_four_days = {
        day for day in all_days
        if start.toordinal() <= day.toordinal() < first_four_end
    }
    later_days = {day for day in all_days if day.toordinal() >= first_four_end}
    core_event_count = sum(1 for _created_at, kind in events if kind in CORE_KINDS)

    full_points = app_usage_source_for_phase(phase)['max_points']
    if len(first_four_days) >= 4 and len(later_days) >= 2 and len(core_days) >= 2:
        points = full_points
    elif len(all_days) >= 2 and core_event_count >= 2:
        points = APP_USAGE_PHASE_PARTIAL_POINTS
    else:
        points = 0

    return AppUsageMetrics(
        phase=phase,
        active_days=len(all_days),
        core_active_days=len(core_days),
        first_four_days=len(first_four_days),
        later_days=len(later_days),
        event_count=len(events),
        core_event_count=core_event_count,
        points=points,
    )


def sync_app_usage_award_for_user(user, phase: int, *, dry_run: bool = False):
    metrics = app_usage_metrics_for_user(user, phase)
    source = app_usage_source_for_phase(phase)
    if metrics.points <= 0:
        return None, metrics, 'skipped'

    note = (
        f'Rule-based app usage phase {phase}: active_days={metrics.active_days}, '
        f'first4_days={metrics.first_four_days}, later_days={metrics.later_days}, '
        f'core_events={metrics.core_event_count}.'
    )
    if dry_run:
        return None, metrics, 'would_credit'

    award, created = PointAward.objects.get_or_create(
        user=user,
        source_kind=PointAward.SOURCE_APP_USAGE,
        source_slug=source['source_slug'],
        response=None,
        scheduled_survey=None,
        defaults={
            'awarded_points': metrics.points,
            'note': note,
        },
    )
    if created:
        return award, metrics, 'created'
    if metrics.points > award.awarded_points:
        award.awarded_points = metrics.points
        award.note = note
        award.save(update_fields=['awarded_points', 'note', 'updated_at'])
        return award, metrics, 'upgraded'
    return award, metrics, 'unchanged'


def sync_app_usage_awards(*, phase: int | None = None, username: str | None = None, dry_run: bool = False):
    User = get_user_model()
    users = User.objects.filter(id__gte=8, id__lte=87, is_superuser=False)
    if username:
        users = users.filter(username=username)
    phases = [phase] if phase else sorted(PHASE_WINDOWS)

    rows = []
    for user in users.order_by('id'):
        for current_phase in phases:
            award, metrics, status = sync_app_usage_award_for_user(
                user,
                current_phase,
                dry_run=dry_run,
            )
            rows.append({
                'user': user,
                'phase': current_phase,
                'points': metrics.points,
                'status': status,
                'award': award,
                'metrics': metrics,
            })
    return rows
