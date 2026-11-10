"""training.py: the one parser `improve` still needs.

Training used to write a SKILL.md of its own. It does not any more: `improve`
installs a real skill from the marketplace, or writes a rule into the bot's
soul. What survives here is the small grammar every improve sentence goes
through, ``<bot>: <what>`` or ``<bot> <what>``.
"""

from __future__ import annotations

from .bots import slugify


def guess_bot(text: str, known: object = None) -> tuple[str, str]:
    """Accept ``bot: sentence`` and ``bot sentence``.

    A spoken name uses spaces where the profile uses hyphens. When the
    real names are given, the longest leading words that slug to one of
    them win, so "writer bot always cite" reads as writer-bot.
    """
    raw = " ".join((text or "").split())
    name, _, rest = raw.partition(":")
    if rest.strip() and name.strip():
        return slugify(name), rest.strip()
    if known:
        try:
            wanted = {slugify(str(item)): str(item) for item in known}  # type: ignore[union-attr]
        except Exception:
            wanted = {}
        if wanted:
            words = raw.split()
            for size in (min(3, len(words)), 2, 1):
                if size <= 0:
                    continue
                cand = slugify(" ".join(words[:size]))
                if cand and cand in wanted:
                    return wanted[cand], " ".join(words[size:]).strip()
    head, _, tail = raw.partition(" ")
    return slugify(head), tail.strip()


__all__ = ["guess_bot"]
