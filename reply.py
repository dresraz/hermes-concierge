"""A bare "yes" in a chat that is holding a card becomes ``/concierge yes``.

The CLI has no hook between a line of input and the agent turn, so there the card asks for
``/concierge yes``. The gateway fires ``pre_gateway_dispatch`` before dispatch, so on Telegram,
Discord and friends the answer really is one bare word.
"""

from __future__ import annotations

from typing import Any

from . import card

HOOK = "pre_gateway_dispatch"

ANSWERS = {
    "y": "yes",
    "yeah": "yes",
    "yep": "yes",
    "yes": "yes",
    "n": "no",
    "nope": "no",
    "no": "no",
    "more": "more",
}


def rewrite(text: str, session_key: str = "") -> str | None:
    """The command a bare answer stands for, or None when this chat holds no card.

    Only a bare word counts: "yes please, and also..." is left to the agent, because a rewrite
    would silently throw the rest of the sentence away.
    """

    answer = ANSWERS.get(" ".join(str(text or "").split()).lower())
    if answer is None:
        return None
    from . import market

    # Two shelves can hold a card: the plugin catalog and the skill registries.
    if not (card.is_waiting(session_key) or market.is_waiting(session_key)):
        return None
    return f"/concierge {answer}"


def on_gateway_dispatch(*, event: Any = None, gateway: Any = None, **_: Any) -> dict | None:
    """Rewrite a bare answer from the chat that was shown the card, and no other chat."""

    text = getattr(event, "text", "") or ""
    source = getattr(event, "source", None)
    if source is None or not str(text).strip():
        return None
    # The command dispatch itself keys the conversation with this method; using it here means the
    # card a chat answers is the card that chat was shown.
    key_for = getattr(gateway, "_session_key_for_source", None)
    if key_for is None:
        return None
    command = rewrite(text, key_for(source))
    return {"action": "rewrite", "text": command} if command else None
