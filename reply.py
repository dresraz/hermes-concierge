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

# What a reply to a pending card can mean. Vocabulary, not phrasing rules:
# the model picks one of these, and only CONFIRM installs.
OUTCOMES = ("CONFIRM", "DROP", "OTHER")


def _pending_description(session_key: str) -> str:
    """The waiting offer in its own words, whichever shelf holds it."""
    from . import card, market

    slot = (card._PENDING.get(session_key) or {})
    entries = slot.get("entries") or []
    if entries:
        top = entries[0]
        name = str(getattr(top, "name", "") or "")
        desc = str(getattr(top, "description", "") or "")
        if not desc:
            try:
                desc = str(getattr(getattr(top, "entry", None), "description", "") or "")
            except Exception:
                desc = ""
        return "{}: {}".format(name, desc).strip(": ")
    held = (market._PENDING.get(session_key) or {})
    offers = held.get("offers") or []
    if offers:
        top = offers[0]
        return "{}: {}".format(
            getattr(top, "name", ""), getattr(top, "description", ""))
    return ""


def answer_for(text: str, description: str = "", llm: Any = None) -> str:
    """What a bare reply means: CONFIRM, DROP, or OTHER.

    The model reads the whole reply against the pending offer's description.
    Only a bare reply counts: "yes please, and also..." is OTHER, because
    answering it would throw the rest of the sentence away. With no model
    the answer is OTHER and nothing is consumed.
    """
    from .card import decide_answer

    if llm is None:
        return "OTHER"
    text = " ".join(str(text or "").split())
    if not text:
        return "OTHER"
    return decide_answer(text, description, llm)


def waiting(session_key: str) -> bool:
    from . import card, market

    return bool(card.is_waiting(session_key) or market.is_waiting(session_key))


def on_admission(*, text: str = "", session_key: str = "", platform: str = "", **_: Any) -> dict | None:
    """Answer the card this conversation is holding, and nothing else.

    The platform the hook was told about is the surface the command runs on. A
    hook that is not told where it is counts as a shared chat, which is the safe
    side: the owner's own surfaces pass their name.
    """
    if not session_key or not waiting(session_key):
        return None
    from . import commands

    llm = commands._llm()
    verdict = answer_for(text, _pending_description(session_key), llm)
    if verdict not in ("CONFIRM", "DROP"):
        return None
    # Forward the original reply: the command layer hands the same sentence
    # to the model with the same pending description, so it reads the same
    # verdict and carries it out through the code that owns it.
    saved, saved_answer = commands._PLATFORM, commands._PLATFORM_ANSWER
    commands._PLATFORM = (platform or "gateway").lower()
    commands._PLATFORM_ANSWER = True
    try:
        reply_text = commands.handle_concierge(text, session_key=session_key)
    finally:
        commands._PLATFORM, commands._PLATFORM_ANSWER = saved, saved_answer
    return {"action": "handled", "reply": reply_text}
