"""A bare "yes" in a chat that is holding a card answers it.

The gateway fires ``post_gateway_admission`` once per admitted inbound message,
after auth, with the conversation's ``session_key``. That is the public seam: the
hook runs the answer itself and returns the receipt, so the card a chat is
holding is the card that chat sees, and no private session-key derivation is
needed. The CLI has no such hook, so there the card asks for ``/concierge yes``.
"""

from __future__ import annotations

from typing import Any

HOOK = "post_gateway_admission"

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


def answer_for(text: str) -> str:
    """The command word a bare answer stands for, or "".

    Only a bare word counts: "yes please, and also..." is left to the agent,
    because answering it would throw the rest of the sentence away.
    """
    return ANSWERS.get(" ".join(str(text or "").split()).lower(), "")


def waiting(session_key: str) -> bool:
    from . import card, market

    return bool(card.is_waiting(session_key) or market.is_waiting(session_key))


def on_admission(*, text: str = "", session_key: str = "", platform: str = "", **_: Any) -> dict | None:
    """Answer the card this conversation is holding, and nothing else."""
    word = answer_for(text)
    if not word or not session_key or not waiting(session_key):
        return None
    from . import commands

    reply_text = commands.handle_concierge(word, session_key=session_key)
    return {"action": "handled", "reply": reply_text}
