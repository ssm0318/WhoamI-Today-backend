from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.db.models import Q

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
APPROVED_INTERVIEW_EMAILS = STANDARD_INTERVIEW_EMAILS | {REBECCA_INTERVIEW_EMAIL}


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


@dataclass(frozen=True)
class FinalAwardSpec:
    source_kind: str
    source_slug: str
    awarded_points: int
    adjusted_points: int | None
    note: str


@dataclass(frozen=True)
class ReconciliationResult:
    created: int
    updated: int
    unchanged: int
    projected_points: int


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


def participant_queryset():
    from django.contrib.auth import get_user_model
    from surveys.app_usage import (
        PARTICIPANT_ID_MAX, PARTICIPANT_ID_MIN, PARTICIPANT_REPLACED_ID,
        PARTICIPANT_REPLACEMENT_ID,
    )

    return get_user_model().objects.filter(is_superuser=False).filter(
        Q(id__gte=PARTICIPANT_ID_MIN, id__lte=PARTICIPANT_ID_MAX)
        | Q(id=PARTICIPANT_REPLACEMENT_ID)
    ).exclude(id=PARTICIPANT_REPLACED_ID).order_by('id')


def validate_interview_accounts(users: Iterable) -> dict[str, object]:
    matches: dict[str, list] = {email: [] for email in APPROVED_INTERVIEW_EMAILS}
    for user in users:
        normalized = str(user.email or '').strip().lower()
        if normalized in matches:
            matches[normalized].append(user)

    problems = []
    for email in sorted(matches):
        accounts = matches[email]
        if len(accounts) != 1:
            problems.append(f'{email} matched {len(accounts)} accounts')
    if problems:
        raise ValueError('Interview account validation failed: ' + '; '.join(problems))
    return {email: accounts[0] for email, accounts in matches.items()}


def build_final_award_specs(
    user,
    *,
    phase1_database: str = 'default',
    phase2_database: str = 'default',
) -> list[FinalAwardSpec]:
    from chat.models import WitBotConversationState
    from surveys.app_usage import app_usage_metrics_for_user
    from surveys.models import PointAward
    from surveys.points import app_usage_source_for_phase, wit_bot_audit_source_for_phase

    specs = []
    for phase, database in ((1, phase1_database), (2, phase2_database)):
        metrics = app_usage_metrics_for_user(user, phase, using=database)
        source = app_usage_source_for_phase(phase)
        specs.append(FinalAwardSpec(
            source_kind=PointAward.SOURCE_APP_USAGE,
            source_slug=source['source_slug'],
            awarded_points=metrics.points,
            adjusted_points=None,
            note=(
                f'Final app usage phase {phase}: active_days={metrics.active_days}; '
                f'first4_days={metrics.first_four_days}; later_days={metrics.later_days}; '
                f'core_events={metrics.core_event_count}; database={database}.'
            ),
        ))

    state = WitBotConversationState.objects.filter(user_id=user.pk).first()
    context = state.context if state is not None else {}
    for phase in (1, 2):
        outcome = wit_bot_outcome(context or {}, user.user_group, phase)
        source = wit_bot_audit_source_for_phase(phase)
        specs.append(FinalAwardSpec(
            source_kind=PointAward.SOURCE_WIT_BOT_AUDIT,
            source_slug=source['source_slug'],
            awarded_points=outcome.points,
            adjusted_points=None,
            note=outcome.note,
        ))

    User = type(user)
    invitees = [
        InviteeRecord(invitee.id, invitee.username, invitee.is_staff)
        for invitee in User.objects.filter(invited_from_id=user.pk).order_by('id')
    ]
    invite_outcome = friend_invite_outcome(invitees)
    specs.append(FinalAwardSpec(
        source_kind=PointAward.SOURCE_FRIEND_INVITE,
        source_slug=PointAward.SOURCE_FRIEND_INVITE,
        awarded_points=invite_outcome.points,
        adjusted_points=None,
        note=invite_outcome.note,
    ))

    interview_points = interview_points_for_email(user.email)
    if interview_points > 0:
        specs.append(FinalAwardSpec(
            source_kind=PointAward.SOURCE_INTERVIEW_SIGNUP,
            source_slug=PointAward.SOURCE_INTERVIEW_SIGNUP,
            awarded_points=interview_points,
            adjusted_points=None,
            note='Interview completion confirmed by researcher email list.',
        ))
    return specs


def reconcile_user_awards(
    user,
    specs: Iterable[FinalAwardSpec],
    *,
    apply: bool,
) -> ReconciliationResult:
    from surveys.models import PointAward

    created = updated = unchanged = projected_points = 0
    for spec in specs:
        projected_points += (
            spec.adjusted_points
            if spec.adjusted_points is not None
            else spec.awarded_points
        )
        award = PointAward.objects.filter(
            user=user,
            source_kind=spec.source_kind,
            source_slug=spec.source_slug,
            response=None,
            scheduled_survey=None,
        ).first()
        if award is None:
            created += 1
            if apply:
                PointAward.objects.create(
                    user=user,
                    source_kind=spec.source_kind,
                    source_slug=spec.source_slug,
                    awarded_points=spec.awarded_points,
                    adjusted_points=spec.adjusted_points,
                    note=spec.note,
                )
            continue

        intended = (spec.awarded_points, spec.adjusted_points, spec.note)
        current = (award.awarded_points, award.adjusted_points, award.note)
        if intended == current:
            unchanged += 1
            continue

        updated += 1
        if apply:
            award.awarded_points = spec.awarded_points
            award.adjusted_points = spec.adjusted_points
            award.note = spec.note
            award.save(update_fields=[
                'awarded_points', 'adjusted_points', 'note', 'updated_at',
            ])

    return ReconciliationResult(
        created=created,
        updated=updated,
        unchanged=unchanged,
        projected_points=projected_points,
    )
