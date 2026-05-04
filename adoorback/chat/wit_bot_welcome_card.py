"""State-aware welcome card builder for the wit_bot 1-on-1 room."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone

from chat import wit_bot_state as state_mod
from chat.wit_bot_payloads import card_with_buttons


# Study windows (PST). Hardcoded to match
# surveys/migrations/0004_seed_study_schedule.py + spec timeline.
V1_WINDOW_START = timezone.make_aware(datetime(2026, 5, 4, 0, 0))
V2_WINDOW_START = timezone.make_aware(datetime(2026, 5, 18, 0, 0))


def build_welcome_card(user, now: datetime | None = None) -> dict[str, Any]:
    """Return a `bot_payload` dict reflecting the user's current onboarding state."""
    if now is None:
        now = timezone.now()

    state = state_mod.get_or_create_state(user)
    version = user.current_ver
    progress = state_mod.progress_for(state, version)
    kickoff = progress.get('kickoff', {})
    completed = kickoff.get('completed', False)

    # Mid-kickoff (intent set but not yet idle) — takes priority over date checks
    # so a participant who started early can resume.
    if state.current_intent.startswith('kickoff_') and state.current_intent != 'kickoff_complete':
        return {
            **card_with_buttons([
                {'label': 'Resume onboarding', 'payload': 'resume_onboarding'},
            ]),
            'intro': 'we were in the middle of something.',
        }

    # Mid-walkthrough — offer to resume the audit
    if state.current_intent in ('audit', 'walkthrough'):
        return {
            **card_with_buttons([
                {'label': 'Resume', 'payload': 'resume_onboarding'},
                {'label': 'Run audit', 'payload': 'run_audit'},
            ]),
            'intro': "audit in progress. resume or rerun?",
        }

    # Kickoff complete → audit CTA (until V1 fully done)
    if completed and version == 'version_w' and now < V2_WINDOW_START:
        audit = progress.get('audit', {})
        last_missing = audit.get('last_missing_count')
        if last_missing == 0:
            return {
                'kind': 'card',
                'intro': "you've tried everything. see you May 18 for the swap.",
                'buttons': [],
            }
        return {
            **card_with_buttons([
                {'label': 'Run audit', 'payload': 'run_audit'},
            ]),
            'intro': "kickoff done. tap **Run audit** when you've explored more.",
        }

    # Pre-window
    if now < V1_WINDOW_START and not completed:
        return {
            'kind': 'card',
            'intro': "i'll be here when the study starts on May 4 — see you then 👋",
            'buttons': [],
        }

    # Window is open, kickoff not started
    if not kickoff and now >= V1_WINDOW_START:
        version_label = 'version Q' if version == 'version_q' else 'version W'
        intro = f"time to onboard. you're on {version_label}."
        return {
            **card_with_buttons([
                {'label': 'Start onboarding', 'payload': 'start_onboarding'},
            ]),
            'intro': intro,
        }

    # Default: silent
    return {
        'kind': 'card',
        'intro': "all good. see you when needed.",
        'buttons': [],
    }
