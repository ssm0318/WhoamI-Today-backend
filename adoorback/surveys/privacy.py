"""
Two-layer privacy thresholds for survey result distributions.

Layer 1 (BeReal gate, enforced in views): viewer must have submitted AND
the survey's day must have elapsed before any bucket is exposed.

Layer 2 (per-bucket gates, enforced here): k-anonymity (MIN_GROUP_SIZE) on
each bucket, plus an anti-subtraction delta gate (MIN_GROUP_DELTA) between
the friends and close-friends responder counts to prevent backing out the
average of non-close-friend friends.

Friend / close-friend buckets are additionally suppressed when:
  - Survey-level: ``Survey.friend_visible`` is False (kill switch for all panels), or
  - Per-panel: the panel's render kind is in ``PRIVACY_FRIEND_DISABLED_KINDS``
    (e.g. wordcloud — token-level k-anonymity isn't enough in small friend pools).
"""
from __future__ import annotations

from typing import Optional, TypedDict

from django.contrib.auth import get_user_model

from chat.wit_admin import ALL_OPERATOR_EMAILS, WIT_ADMIN_USERNAME
from chat.wit_bot import WIT_BOT_USERNAME
from surveys.models import PRIVACY_FRIEND_DISABLED_KINDS, Survey, SurveyResponse


MIN_GROUP_SIZE = 5      # k-anonymity threshold for bucket-level visibility
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


def _friend_buckets_disabled(survey: Survey, panel_kind: str) -> bool:
    if not survey.friend_visible:
        return True
    return panel_kind in PRIVACY_FRIEND_DISABLED_KINDS


class ResponderIds(TypedDict):
    population: list[int]
    friend: list[int]
    close_friend: list[int]


def compute_responder_ids(viewer, survey: Survey) -> ResponderIds:
    """One-shot lookup of who responded to this survey within each visibility tier.

    Returned IDs are reused across panels — a SurveyResponse exists at the survey
    level, not per-panel, so the responder set is identical for every panel.
    """
    response_qs = SurveyResponse.objects.filter(survey=survey)
    population = list(
        _exclude_system_users_qs(User.objects.filter(id__in=response_qs.values('user_id')))
        .values_list('id', flat=True)
    )
    friend_ids = set(get_visible_friend_ids(viewer))
    close_friend_ids = set(get_visible_close_friend_ids(viewer))
    friend = [uid for uid in population if uid in friend_ids]
    close_friend = [uid for uid in population if uid in close_friend_ids]
    return {
        'population': population,
        'friend': friend,
        'close_friend': close_friend,
    }


def compute_panel_eligibility(
    viewer,
    survey: Survey,
    panel_kind: str,
    ids: ResponderIds,
) -> dict:
    """Eligibility report for one panel. Returns three BucketReport entries."""
    pop_n = len(ids['population'])
    population: BucketReport = {
        'available': pop_n >= MIN_GROUP_SIZE,
        'suppressed_reason': None if pop_n >= MIN_GROUP_SIZE else 'too_few_responders',
        'required_n': MIN_GROUP_SIZE,
    }

    if _friend_buckets_disabled(survey, panel_kind):
        friends: BucketReport = {
            'available': False,
            'suppressed_reason': 'view_friend_disabled',
            'required_n': MIN_GROUP_SIZE,
        }
        close_friends: BucketReport = {
            'available': False,
            'suppressed_reason': 'view_friend_disabled',
            'required_n': MIN_GROUP_SIZE,
        }
        return {'population': population, 'friends': friends, 'close_friends': close_friends}

    friend_ids = set(get_visible_friend_ids(viewer))
    close_friend_ids = set(get_visible_close_friend_ids(viewer))

    friends_reason: Optional[str] = None
    if len(friend_ids) < MIN_GROUP_SIZE:
        friends_reason = 'too_few_friends'
    elif len(ids['friend']) < MIN_GROUP_SIZE:
        friends_reason = 'too_few_responders'
    friends = {
        'available': friends_reason is None,
        'suppressed_reason': friends_reason,
        'required_n': MIN_GROUP_SIZE,
    }

    cf_reason: Optional[str] = None
    if len(close_friend_ids) < MIN_GROUP_SIZE:
        cf_reason = 'too_few_close_friends'
    elif len(ids['close_friend']) < MIN_GROUP_SIZE:
        cf_reason = 'too_few_responders'
    elif (len(ids['friend']) - len(ids['close_friend'])) < MIN_GROUP_DELTA:
        cf_reason = 'delta_too_small'
    close_friends = {
        'available': cf_reason is None,
        'suppressed_reason': cf_reason,
        'required_n': MIN_GROUP_SIZE,
    }

    return {'population': population, 'friends': friends, 'close_friends': close_friends}


# Back-compat shim for callers expecting the old single-panel API.
# Deprecated; new callers should call compute_responder_ids + compute_panel_eligibility per panel.
def compute_bucket_eligibility(viewer, survey: Survey) -> dict:  # pragma: no cover
    ids = compute_responder_ids(viewer, survey)
    # Use the survey's "primary" kind from its first non-hidden question, or option_counts.
    first = survey.questions.filter(result_hidden=False).order_by('order').first()
    from surveys.models import RESULT_OPTION_COUNTS
    panel_kind = first.effective_result_kind if first else RESULT_OPTION_COUNTS
    report = compute_panel_eligibility(viewer, survey, panel_kind, ids)
    return {
        **report,
        '_population_ids': ids['population'],
        '_friend_ids': ids['friend'],
        '_close_friend_ids': ids['close_friend'],
    }
