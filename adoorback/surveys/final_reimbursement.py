from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from surveys.reimbursement_config import (
    FRIEND_INVITE_MAX_POINTS, FRIEND_INVITE_POINTS_PER_FRIEND,
    INTERVIEW_COMPLETED_POINTS, INTERVIEW_REBECCA_POINTS,
    WIT_BOT_AUDIT_PARTIAL_POINTS, WIT_BOT_AUDIT_PHASES,
)


STANDARD_INTERVIEW_EMAILS = frozenset({
    'jennylninh@gmail.com',
    'siddhub2001@gmail.com',
    'yixin7@uw.edu',
    'pinkchloeko@gmail.com',
    'ole2@uw.edu',
    'sai.yakumo770@gmail.com',
    'superlegos113@gmail.com',
    'anh.n.personal@gmail.com',
    'sklein3@uw.edu',
    'aishani.rao22@gmail.com',
})
REBECCA_INTERVIEW_EMAIL = 'rebecca.laba@gmail.com'


@dataclass(frozen=True)
class WitBotOutcome:
    phase: int
    version: str
    best_score: float | None
    audit_engaged_count: int | None
    audit_missing_count: int | None
    points: int
    note: str


@dataclass(frozen=True)
class InviteeRecord:
    user_id: int
    username: str
    is_staff: bool


@dataclass(frozen=True)
class FriendInviteOutcome:
    eligible_count: int
    credited_count: int
    points: int
    note: str


def best_boss_quiz_score(progress: dict) -> float | None:
    scores = []
    for attempt in progress.get('attempts_history') or []:
        score = attempt.get('score') if isinstance(attempt, dict) else None
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            scores.append(float(score))
    final_score = progress.get('final_score')
    if isinstance(final_score, (int, float)) and not isinstance(final_score, bool):
        scores.append(float(final_score))
    return max(scores) if scores else None


def wit_bot_points_for_score(score: float | None) -> int:
    if score is not None and score > 0.85:
        return WIT_BOT_AUDIT_PHASES[1]['max_points']
    if score is not None and score > 0.60:
        return WIT_BOT_AUDIT_PARTIAL_POINTS
    return 0


def wit_bot_outcome(context: dict, user_group: str, phase: int) -> WitBotOutcome:
    from surveys.points import wit_bot_audit_version_for_group

    version = wit_bot_audit_version_for_group(user_group, phase)
    progress = (context or {}).get(version) or {}
    final_quiz = progress.get('final_quiz') or {}
    audit = progress.get('audit') or {}
    score = best_boss_quiz_score(final_quiz)
    engaged_count = audit.get('last_engaged_count')
    missing_count = audit.get('last_missing_count')
    score_label = 'none' if score is None else f'{score:.6f}'
    note = (
        f'Boss quiz best score={score_label}; '
        f'audit engaged={engaged_count}; audit missing={missing_count}.'
    )
    return WitBotOutcome(
        phase=phase,
        version=version,
        best_score=score,
        audit_engaged_count=engaged_count,
        audit_missing_count=missing_count,
        points=wit_bot_points_for_score(score),
        note=note,
    )


def friend_invite_outcome(invitees: Iterable[InviteeRecord]) -> FriendInviteOutcome:
    eligible = sorted(
        (invitee for invitee in invitees if not invitee.is_staff),
        key=lambda invitee: invitee.user_id,
    )
    credited_count = min(
        len(eligible),
        FRIEND_INVITE_MAX_POINTS // FRIEND_INVITE_POINTS_PER_FRIEND,
    )
    points = credited_count * FRIEND_INVITE_POINTS_PER_FRIEND
    invitee_list = ', '.join(
        f'{invitee.user_id}:{invitee.username}' for invitee in eligible
    ) or 'none'
    note = (
        f'Eligible invites={len(eligible)}; credited invites={credited_count}; '
        f'invitees={invitee_list}.'
    )
    return FriendInviteOutcome(len(eligible), credited_count, points, note)


def interview_points_for_email(email: str) -> int:
    normalized = str(email or '').strip().lower()
    if normalized == REBECCA_INTERVIEW_EMAIL:
        return INTERVIEW_REBECCA_POINTS
    if normalized in STANDARD_INTERVIEW_EMAILS:
        return INTERVIEW_COMPLETED_POINTS
    return 0
