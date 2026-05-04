"""Builders for outgoing wit_bot `bot_payload` dicts.

Mirror of the frontend `BotPayload` shape in
`WhoamI-Today-frontend/src/models/chat.ts`. Keep these in sync manually —
there's no shared schema.
"""
from __future__ import annotations

from typing import Any


def card_with_buttons(buttons: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a 'card' payload. Each button dict can have either:
      - `payload`: triggers a reply (action='reply')
      - `navigate_to`: triggers navigation (action='navigate')
      - `upload_context`: triggers upload (action='upload')
    """
    out_buttons = []
    for b in buttons:
        if 'payload' in b:
            out_buttons.append({
                'label': b['label'],
                'action': 'reply',
                'payload': b['payload'],
            })
        elif 'navigate_to' in b:
            out_buttons.append({
                'label': b['label'],
                'action': 'navigate',
                'url': b['navigate_to'],
            })
        elif 'upload_context' in b:
            out_buttons.append({
                'label': b['label'],
                'action': 'upload',
                'context': b['upload_context'],
            })
        else:
            raise ValueError(f"Button {b['label']} missing payload/navigate_to/upload_context")
    return {'kind': 'card', 'buttons': out_buttons}


def multi_select(intent: str, options: list[dict[str, Any]],
                 submit_label: str = 'Submit',
                 min_selection: int = 0,
                 max_selection: int | None = None) -> dict[str, Any]:
    """Build a 'multi_select' payload. Frontend renders checkboxes + Submit.
    Response comes back as bot_payload = {kind: 'multi_select_response', intent, selected: [...]}.
    """
    return {
        'kind': 'multi_select',
        'intent': intent,
        'options': [{'label': o['label'], 'value': o['value']} for o in options],
        'submit_label': submit_label,
        'min_selection': min_selection,
        'max_selection': max_selection,
    }


def upload_request(context: str, label: str = 'Upload screenshot') -> dict[str, Any]:
    """Build an 'upload' payload. Frontend renders an image picker. Response
    comes back as a Message with .image set + bot_payload =
    {kind: 'upload_response', context}.
    """
    return {'kind': 'upload', 'context': context, 'label': label}
