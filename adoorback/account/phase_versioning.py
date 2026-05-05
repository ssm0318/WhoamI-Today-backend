"""Phase-aware Ver.W / Ver.Q assignment for the 4-week crossover study.

The study assigns each user a stable `user_group` (set at signup):
  - group_w_first → uses Ver.W in Phase 1, Ver.Q in Phase 2
  - group_q_first → uses Ver.Q in Phase 1, Ver.W in Phase 2

`User.current_ver` (the runtime feature flag the frontend / friend-filter
queries / ExperimentLoggingMiddleware all read) needs to flip on the
phase boundary so the correct UI surfaces. This module owns the
date logic; `account.cron.CrossoverPhaseFlipCronJob` runs daily and
calls `flip_users_to_expected_version` to enforce the assignment.

Pre-Phase-1 days (May 4 onward but before the boundary) and the
window before the study starts both behave as Phase 1 so the initial
signup-time defaults remain correct.
"""
from __future__ import annotations

from datetime import date

from django.db.models import Q
from django.utils import timezone
from zoneinfo import ZoneInfo


# Phase 2 starts on study Day 15 (Monday of week 3). The biweekly
# crossover lines up with the W/Q `mid_study_*` opening on Day 14 — by
# the morning of Day 15 (LA-7am boundary, same convention as the
# survey scheduling layer) every user is on the other version.
PHASE_2_START = date(2026, 5, 18)


def la_today() -> date:
    """Return the current logical date in America/Los_Angeles, using the
    same 7 AM boundary as `surveys.scheduling._today_la_7am` so the
    survey schedule and the version flip stay aligned.

    Before 7 AM LA, this returns yesterday's date.
    """
    from datetime import timedelta
    return (timezone.now().astimezone(ZoneInfo('America/Los_Angeles'))
            - timedelta(hours=7)).date()


def expected_version_for(user_group: str, today: date) -> str:
    """Return the version a user in `user_group` should be on for `today`.

    Phase 1 (today < PHASE_2_START):
      - group_w_first → 'version_w'
      - group_q_first → 'version_q'

    Phase 2 (today >= PHASE_2_START):
      - group_w_first → 'version_q' (crossover)
      - group_q_first → 'version_w' (crossover)

    Unknown / blank user_group falls back to Phase-1 group_w_first
    behavior — matches the model default and is what
    `account.views.signup` would have produced for a solo signup.
    """
    is_phase_2 = today >= PHASE_2_START
    if user_group == 'group_q_first':
        return 'version_w' if is_phase_2 else 'version_q'
    return 'version_q' if is_phase_2 else 'version_w'


def flip_users_to_expected_version(today: date | None = None) -> dict:
    """Idempotently flip every User row whose `current_ver` doesn't match
    the phase-aware expected version for their `user_group`.

    Returns a summary dict {group: rows_updated} — useful for cron logs
    and the manual-trigger management command.

    Safe to call repeatedly: after both groups land on their Phase 2
    versions, subsequent calls find zero rows to update and no-op.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    if today is None:
        today = la_today()

    summary: dict[str, int] = {}
    now = timezone.now()
    for group in ('group_w_first', 'group_q_first'):
        expected = expected_version_for(group, today)
        # Exclude rows already on the right version so ver_changed_at
        # only updates on actual flips. `is_superuser=False` keeps admin
        # accounts out of the experiment population — they shouldn't be
        # treated as study participants.
        updated = (
            User.objects
            .filter(user_group=group, is_superuser=False)
            .exclude(current_ver=expected)
            .update(current_ver=expected, ver_changed_at=now)
        )
        summary[group] = updated
    return summary
