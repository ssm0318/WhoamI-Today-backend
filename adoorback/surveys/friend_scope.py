from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db.models import Q

from account.models import Connection
from surveys.models import ScheduledSurvey
from surveys.scheduling import schedule_routes_to_user


FRIEND_CLOSENESS_MIN_CONNECTION_DAYS = 2
FRIEND_CLOSENESS_SURVEY_SLUGS = frozenset({
    'phase1_friend_closeness',
    'phase2_friend_closeness',
    'phase1_friend_closeness_part2',
})
LA_TZ = ZoneInfo('America/Los_Angeles')


def is_friend_closeness_survey(survey) -> bool:
    return getattr(survey, 'slug', '') in FRIEND_CLOSENESS_SURVEY_SLUGS


def friend_eligibility_date_for_survey(user, survey):
    rows = (
        ScheduledSurvey.objects
        .filter(survey=survey)
        .select_related('survey')
        .order_by('window_start', 'sequence_index')
    )
    for row in rows:
        if schedule_routes_to_user(row, user):
            return row.window_start
    return None


def eligible_friends_for_survey(user, survey):
    cutoff_date = None
    if is_friend_closeness_survey(survey):
        eligibility_date = friend_eligibility_date_for_survey(user, survey)
        if eligibility_date is not None:
            cutoff_date = eligibility_date - timedelta(days=FRIEND_CLOSENESS_MIN_CONNECTION_DAYS)

    friends = []
    connections = (
        Connection.objects
        .filter(Q(user1=user) | Q(user2=user))
        .select_related('user1', 'user2')
    )
    for connection in connections:
        if cutoff_date is not None:
            connected_date = connection.created_at.astimezone(LA_TZ).date()
            if connected_date > cutoff_date:
                continue
        friend = connection.user2 if connection.user1_id == user.id else connection.user1
        friends.append(friend)
    return sorted(friends, key=lambda friend: friend.username)


def eligible_friend_ids_for_survey(user, survey) -> set[int]:
    return {friend.id for friend in eligible_friends_for_survey(user, survey)}
