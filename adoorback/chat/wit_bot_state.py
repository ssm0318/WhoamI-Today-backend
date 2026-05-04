"""Read/write helpers for WitBotConversationState.

context schema (per user):
  {
    'version_w': {
      'kickoff': { ... per-quiz / per-setup-check progress ... },
    },
    'version_q': { ... },
  }
"""
from __future__ import annotations

from typing import Any

from chat.models import WitBotConversationState


def get_or_create_state(user) -> WitBotConversationState:
    state, _ = WitBotConversationState.objects.get_or_create(user=user)
    return state


def set_intent(state: WitBotConversationState, intent: str, step: int = 0) -> None:
    state.current_intent = intent
    state.step = step
    state.save(update_fields=['current_intent', 'step', 'updated_at'])


def progress_for(state: WitBotConversationState, version: str) -> dict[str, Any]:
    return state.context.get(version, {})


def set_progress(state: WitBotConversationState, version: str,
                 section: str, updates: dict[str, Any]) -> None:
    """Merge `updates` into state.context[version][section] and persist."""
    ctx = state.context or {}
    ver = ctx.setdefault(version, {})
    sec = ver.setdefault(section, {})
    sec.update(updates)
    state.context = ctx
    state.save(update_fields=['context', 'updated_at'])


def clear_intent(state: WitBotConversationState) -> None:
    set_intent(state, '', step=0)
