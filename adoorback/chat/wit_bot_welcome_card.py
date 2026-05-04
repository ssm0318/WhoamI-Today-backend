"""State-aware welcome card builder for the wit_bot 1-on-1 room."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone

from chat import wit_bot_state as state_mod
from chat.wit_bot_copy import (
    WC_AUDIT_DONE_PRE_BOSS, WC_AUDIT_IN_PROGRESS, WC_BOSS_PASSED_PRE_SWAP,
    WC_BTN_RESUME, WC_BTN_RESUME_ONBOARDING, WC_BTN_RUN_AUDIT,
    WC_BTN_START_ONBOARDING, WC_BTN_START_VERSION_Q, WC_BTN_START_VERSION_W,
    WC_BTN_TAKE_BOSS_QUIZ, WC_DEFAULT_SILENT, WC_KICKOFF_DONE_PRE_AUDIT,
    WC_MID_FLOW, WC_POST_SWAP_Q, WC_POST_SWAP_W, WC_PRE_WINDOW,
    WC_TIME_TO_ONBOARD_Q, WC_TIME_TO_ONBOARD_W, t,
)
from chat.wit_bot_payloads import card_with_buttons


# Study windows (PST). Hardcoded to match
# surveys/migrations/0004_seed_study_schedule.py + spec timeline.
V1_WINDOW_START = timezone.make_aware(datetime(2026, 5, 4, 0, 0))
V2_WINDOW_START = timezone.make_aware(datetime(2026, 5, 18, 0, 0))


def build_welcome_card(user, now: datetime | None = None) -> dict[str, Any]:
    """Return a `bot_payload` dict reflecting the user's current onboarding state.
    Localized to user.language."""
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
                {'label': t(WC_BTN_RESUME_ONBOARDING, user), 'payload': 'resume_onboarding'},
            ]),
            'intro': t(WC_MID_FLOW, user),
        }

    # Mid-walkthrough — offer to resume the audit
    if state.current_intent in ('audit', 'walkthrough'):
        return {
            **card_with_buttons([
                {'label': t(WC_BTN_RESUME, user), 'payload': 'resume_onboarding'},
                {'label': t(WC_BTN_RUN_AUDIT, user), 'payload': 'run_audit'},
            ]),
            'intro': t(WC_AUDIT_IN_PROGRESS, user),
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
                'intro': t(WC_BOSS_PASSED_PRE_SWAP, user),
                'buttons': [],
            }
        if last_missing == 0:
            return {
                **card_with_buttons([
                    {'label': t(WC_BTN_TAKE_BOSS_QUIZ, user), 'payload': 'take_boss_quiz'},
                ]),
                'intro': t(WC_AUDIT_DONE_PRE_BOSS, user),
            }
        return {
            **card_with_buttons([
                {'label': t(WC_BTN_RUN_AUDIT, user), 'payload': 'run_audit'},
            ]),
            'intro': t(WC_KICKOFF_DONE_PRE_AUDIT, user),
        }

    # Post-swap detection: prior version's kickoff is complete, this version's isn't.
    other_version = 'version_q' if version == 'version_w' else 'version_w'
    other_progress = state_mod.progress_for(state, other_version)
    other_kickoff_done = other_progress.get('kickoff', {}).get('completed', False)

    if other_kickoff_done and not kickoff:
        if version == 'version_q':
            cta_label = t(WC_BTN_START_VERSION_Q, user)
            intro = t(WC_POST_SWAP_Q, user)
        else:
            cta_label = t(WC_BTN_START_VERSION_W, user)
            intro = t(WC_POST_SWAP_W, user)
        return {
            **card_with_buttons([
                {'label': cta_label, 'payload': 'start_onboarding'},
            ]),
            'intro': intro,
        }

    # Pre-window
    if now < V1_WINDOW_START and not completed:
        return {
            'kind': 'card',
            'intro': t(WC_PRE_WINDOW, user),
            'buttons': [],
        }

    # Window is open, kickoff not started (fresh user, no prior version progress)
    if not kickoff and now >= V1_WINDOW_START:
        intro_value = WC_TIME_TO_ONBOARD_Q if version == 'version_q' else WC_TIME_TO_ONBOARD_W
        return {
            **card_with_buttons([
                {'label': t(WC_BTN_START_ONBOARDING, user), 'payload': 'start_onboarding'},
            ]),
            'intro': t(intro_value, user),
        }

    # Default: silent
    return {
        'kind': 'card',
        'intro': t(WC_DEFAULT_SILENT, user),
        'buttons': [],
    }
