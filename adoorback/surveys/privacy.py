"""
Two-layer privacy thresholds for survey result distributions.

Layer 1 (BeReal gate, enforced in views): viewer must have submitted AND
the survey's day must have elapsed before any bucket is exposed.

Layer 2 (per-bucket gates, enforced here): k-anonymity (MIN_GROUP_SIZE) on
each bucket, plus an anti-subtraction delta gate (MIN_GROUP_DELTA) between
the friends and close-friends responder counts to prevent backing out the
average of non-close-friend friends.
"""
from __future__ import annotations

from typing import Optional, TypedDict

from django.contrib.auth import get_user_model

from chat.wit_admin import ALL_OPERATOR_EMAILS, WIT_ADMIN_USERNAME
from chat.wit_bot import WIT_BOT_USERNAME
from surveys.models import Survey, SurveyResponse


MIN_GROUP_SIZE = 5      # k-anonymity threshold
MIN_GROUP_DELTA = 5     # min (friend_responders - close_friend_responders)


User = get_user_model()


class BucketReport(TypedDict, total=False):
    available: bool
    suppressed_reason: Optional[str]
    required_n: int


def _exclude_system_users_qs(qs):
    return qs.exclude(username__in=[WIT_BOT_USERNAME, WIT_ADMIN_USERNAME]).exclude(
        email__in=ALL_OPERATOR_EMAILS
    )


def get_visible_friend_ids(viewer) -> list[int]:
    """All connected users, excluding system users.

    The Connection model's ``user_choice`` enum is disjoint ('friend' vs 'close_friend'),
    but the spec's privacy logic treats close_friends as a strict subset of friends so
    the anti-subtraction delta gate is meaningful. We therefore use ``connected_users``
    (all tiers) here rather than ``User.friend_ids`` (only the 'friend' tier).
    """
    return list(_exclude_system_users_qs(viewer.connected_users).values_list('id', flat=True))


def get_visible_close_friend_ids(viewer) -> list[int]:
    return list(
        _exclude_system_users_qs(
            User.objects.filter(id__in=viewer.close_friend_ids)
        ).values_list('id', flat=True)
    )


def compute_bucket_eligibility(viewer, survey: Survey) -> dict:
    """
    Compute eligibility (without aggregating) for population/friends/close_friends.
    The view layer calls this to decide which buckets to aggregate; aggregation.py
    computes distributions only for available buckets.

    Returns a dict with three BucketReport entries plus three underscore-prefixed
    responder-id lists used downstream by aggregation.py.
    """
    response_qs = SurveyResponse.objects.filter(survey=survey)
    population_responder_ids = list(
        _exclude_system_users_qs(User.objects.filter(id__in=response_qs.values('user_id')))
        .values_list('id', flat=True)
    )

    friend_ids = get_visible_friend_ids(viewer)
    close_friend_ids = get_visible_close_friend_ids(viewer)
    friend_responder_ids = [uid for uid in population_responder_ids if uid in friend_ids]
    close_friend_responder_ids = [uid for uid in population_responder_ids if uid in close_friend_ids]

    population: BucketReport = {
        'available': len(population_responder_ids) >= MIN_GROUP_SIZE,
        'suppressed_reason': None if len(population_responder_ids) >= MIN_GROUP_SIZE else 'too_few_responders',
        'required_n': MIN_GROUP_SIZE,
    }

    friends_reason: Optional[str] = None
    if len(friend_ids) < MIN_GROUP_SIZE:
        friends_reason = 'too_few_friends'
    elif len(friend_responder_ids) < MIN_GROUP_SIZE:
        friends_reason = 'too_few_responders'
    friends: BucketReport = {
        'available': friends_reason is None,
        'suppressed_reason': friends_reason,
        'required_n': MIN_GROUP_SIZE,
    }

    cf_reason: Optional[str] = None
    if len(close_friend_ids) < MIN_GROUP_SIZE:
        cf_reason = 'too_few_close_friends'
    elif len(close_friend_responder_ids) < MIN_GROUP_SIZE:
        cf_reason = 'too_few_responders'
    elif (len(friend_responder_ids) - len(close_friend_responder_ids)) < MIN_GROUP_DELTA:
        cf_reason = 'delta_too_small'
    close_friends: BucketReport = {
        'available': cf_reason is None,
        'suppressed_reason': cf_reason,
        'required_n': MIN_GROUP_SIZE,
    }

    return {
        'population': population,
        'friends': friends,
        'close_friends': close_friends,
        '_population_ids': population_responder_ids,
        '_friend_ids': friend_responder_ids,
        '_close_friend_ids': close_friend_responder_ids,
    }
