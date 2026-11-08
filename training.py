"""training.py: the one parser `improve` still needs.

Training used to write a SKILL.md of its own. It does not any more: `improve`
installs a real skill from the marketplace, or writes a rule into the bot's
soul. What survives here is the small grammar every improve sentence goes
through, ``<bot>: <what>`` or ``<bot> <what>``.
"""

from __future__ import annotations

from .bots import slugify

DEFAULT_HINT = "usage: /concierge improve <bot>: <what it should always do>"


def guess_bot(text: str) -> tuple[str, str]:
    """Accept ``bot: sentence`` and ``bot sentence``."""
    raw = " ".join((text or "").split())
    name, _, rest = raw.partition(":")
    if rest.strip() and name.strip():
        return slugify(name), rest.strip()
    head, _, tail = raw.partition(" ")
    return slugify(head), tail.strip()


__all__ = ["DEFAULT_HINT", "guess_bot"]
