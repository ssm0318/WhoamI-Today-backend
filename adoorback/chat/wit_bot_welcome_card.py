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
        final_quiz = progress.get('final_quiz', {})
        passed_final = final_quiz.get('passed', False)

        if passed_final:
            return {
                'kind': 'card',
                'intro': "you survived. see you May 18 for the swap.",
                'buttons': [],
            }
        if last_missing == 0:
            return {
                **card_with_buttons([
                    {'label': 'Take the boss quiz', 'payload': 'take_boss_quiz'},
                ]),
                'intro': "audit done. final quiz time?",
            }
        return {
            **card_with_buttons([
                {'label': 'Run audit', 'payload': 'run_audit'},
            ]),
            'intro': "kickoff done. tap **Run audit** when you've explored more.",
        }

    # Post-swap detection: prior version's kickoff is complete, this version's isn't.
    # Fires regardless of date — once V1 is done and current_ver flipped, the V2
    # CTA should be visible immediately.
    other_version = 'version_q' if version == 'version_w' else 'version_w'
    other_progress = state_mod.progress_for(state, other_version)
    other_kickoff_done = other_progress.get('kickoff', {}).get('completed', False)

    if other_kickoff_done and not kickoff:
        version_label = 'version Q' if version == 'version_q' else 'version W'
        return {
            **card_with_buttons([
                {'label': f'Start {version_label} onboarding', 'payload': 'start_onboarding'},
            ]),
            'intro': f"the swap happened. you're now on {version_label}.\nready for round 2?",
        }

    # Pre-window
    if now < V1_WINDOW_START and not completed:
        return {
            'kind': 'card',
            'intro': "i'll be here when the study starts on May 4 — see you then 👋",
            'buttons': [],
        }

    # Window is open, kickoff not started (fresh user, no prior version progress)
    if not kickoff and now >= V1_WINDOW_START:
        version_label = 'version Q' if version == 'version_q' else 'version W'
        return {
            **card_with_buttons([
                {'label': 'Start onboarding', 'payload': 'start_onboarding'},
            ]),
            'intro': f"time to onboard. you're on {version_label}.",
        }

    # Default: silent
    return {
        'kind': 'card',
        'intro': "all good. see you when needed.",
        'buttons': [],
    }
