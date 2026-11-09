"""The bots Concierge made, and the three things you can do to them.

  bots          list them, numbered
  fire <n>      delete that bot's profile
  reset <n>     take back every change Concierge made in that profile

Three rules, enforced here rather than in the text of a card:

  default       never deleted. On it, reset only replays Concierge's own records.
  ownership     a profile is only touchable if Concierge wrote a record for it.
  receipts      every removal is a replay of a record, never a guessed path.

Hire and fire are the two halves of one idea, and undo is not a third: undo takes
back a change, it never deletes a bot that has been lived in. Fire says the name.

Nothing in this module imports core. The profile calls arrive through
`seams`, so a test can watch every one of them.
"""

from __future__ import annotations

from typing import Any, Optional

from . import state

DEFAULT = "default"
BOT = "bot"


class Refused(Exception):
    """An action Concierge will not take, with the reason said in plain words."""


def records(store: Any = None) -> list:
    """Every receipt Concierge has written, oldest first."""
    store = store if store is not None else state.Store()
    return store.all()


def bots(store: Any = None) -> list:
    """The bot records, in the order `bots` numbers them."""
    return [r for r in records(store) if (getattr(r, "kind", "") or "") == BOT]


def name_of(record: Any) -> str:
    """The profile a record belongs to."""
    return getattr(record, "profile", "") or getattr(record, "name", "") or ""


def for_profile(store: Any = None, name: str = "") -> list:
    """Every record Concierge wrote for one profile."""
    return [r for r in records(store) if name_of(r) == name]


def resolve(store: Any, token: Any) -> Optional[str]:
    """Turn `1`, `2`, `inbox-bot` or `default` into a profile name.

    Returns None when the word is not a bot at all, which is how the caller
    tells `fire 2` apart from `fire the intern`.
    """
    text = " ".join(str(token or "").split())
    low = text.lower()
    if not low:
        return None
    if low == DEFAULT:
        return DEFAULT
    if low.isascii() and low.isdigit() and len(low) <= 4:
        items = bots(store)
        index = int(low)
        if 1 <= index <= len(items):
            return name_of(items[index - 1])
        return None
    for record in records(store):
        if low in {(record.name or "").lower(), name_of(record).lower()}:
            return name_of(record)
    return None


def is_selector(store: Any, token: Any) -> bool:
    """True when the word points at something Concierge can name.

    A bare number is always a selector, even when it lands out of range: a typo
    should be answered as a typo, not handed to the catalog as a search.
    """
    word = " ".join(str(token or "").split())
    if word.isdigit():
        return True
    return resolve(store, word) is not None


def card(store: Any = None) -> str:
    """The numbered list. The only place those numbers are handed out."""
    store = store if store is not None else state.Store()
    items = bots(store)
    lines = []
    if not items:
        lines.append("  No bots yet.")
        lines.append("")
        lines.append("  Make one: /concierge create keeps my inbox at zero")
    else:
        lines.append("  Bots  {}".format(len(items)))
        lines.append("")
        width = max(len(name_of(r)) for r in items)
        for index, record in enumerate(items, 1):
            name = name_of(record)
            title = " ".join(str(getattr(record, "title", "") or "").split())
            if len(title) > 46:
                title = title[:43].rstrip() + "..."
            lines.append("  {:>2}  {:<{w}}  {}".format(index, name, title, w=width))
        lines.append("")
        lines.append("  /concierge delete <n>   remove that bot for good")
        lines.append("  /concierge reset <n>    keep it, take back my changes")

    touched = for_profile(store, DEFAULT)
    if touched:
        lines.append("")
        lines.append("  default  {} Concierge change{}   reset default to take them back".format(
            len(touched), "" if len(touched) == 1 else "s"))
    return "\n".join(lines) + "\n"


def _target(store: Any, token: Any, verb: str) -> str:
    """Resolve a selector, or say what a usable one looks like."""
    text = " ".join(str(token or "").split())
    if not text:
        raise Refused("which bot? /concierge {} <n>, and /concierge bots shows the numbers.".format(verb))
    name = resolve(store, text)
    if name is None:
        raise Refused(
            "{} {} is not one of the bots Concierge made. /concierge bots shows the numbers.".format(
                verb.capitalize(), text
            )
        )
    return name


def history_of(name: str, seams: Any = None) -> list:
    """The things a bot has done since it was made, in words, or nothing.

    Empty means the bot is still stock: safe to delete on one word, and safe for
    undo to take back. Anything here means a person would lose it.
    """
    if seams is None:
        from . import seams as seams_mod

        seams = seams_mod
    try:
        counts = seams.profile_history(name)
    except Exception:
        return []
    words = []
    for key, one, many in (
        ("sessions", "session", "sessions"),
        ("memories", "memory file", "memory files"),
        ("cron", "cron job", "cron jobs"),
    ):
        count = int(counts.get(key) or 0)
        if count:
            words.append("{} {}".format(count, one if count == 1 else many))
    return words


def fire(
    store: Any = None,
    token: Any = "",
    *,
    confirm: Any = "",
    seams: Any = None,
) -> str:
    """Delete a bot's profile, then drop every receipt that pointed at it.

    A stock bot goes on one word. A bot that has been lived in needs its own name
    typed back, because that history is the one thing no undo can return.
    """
    store = store if store is not None else state.Store()
    name = _target(store, token, "fire")
    if name == DEFAULT:
        raise Refused(
            "default is never deleted. To take back only what Concierge changed there: "
            "/concierge reset default"
        )

    record = store.find(name, kind="bot") or store.find(name)
    if record is None or (getattr(record, "kind", "") or "") != BOT:
        raise Refused(
            "Concierge did not create {}, so it will not delete it. It only removes bots it made.".format(name)
        )

    history = history_of(name, seams)
    if history and " ".join(str(confirm or "").split()).lower() != name.lower():
        raise Refused(
            "{} has history: {}. Firing it throws that away, and nothing brings it back.\n"
            "  To do it anyway: /concierge fire {} {}".format(name, ", ".join(history), token, name)
        )

    from . import commands

    lines = commands._undo_record(record, seams=seams, guard=False)
    problems = [line for line in lines if line.startswith(("could not", "still there"))]
    if problems:
        return "\n".join(
            ["Not fired: {}".format(name), ""]
            + ["  " + line for line in lines]
            + ["", "  the receipt is kept, so /concierge fire {} tries again".format(name), ""]
        )

    for other in for_profile(store, name):
        store.drop(other.name, other.kind)
    head = "Deleted {}".format(name)
    return "\n".join([head, ""] + ["  " + line for line in lines] + [
        "", "  The profile, its skills and its history are gone. A new one costs one sentence.",
        ""])


def reset(store: Any = None, token: Any = "", *, seams: Any = None) -> str:
    """Replay undo over every record Concierge wrote for one profile."""
    store = store if store is not None else state.Store()
    name = _target(store, token, "reset")
    touched = for_profile(store, name)
    if not touched:
        raise Refused("Concierge has not changed {}, so there is nothing to take back.".format(name))

    from . import commands

    lines: list = []
    failed = 0
    for record in reversed(touched):
        # reset never deletes a profile: it takes back what was written inside it.
        # Removing the bot itself is `fire`, a separate sentence with its own name
        # typed back when the bot has history.
        if (getattr(record, "kind", "") or "") == BOT:
            lines.append("kept: the bot itself (delete it with /concierge fire)")
            continue
        got = commands._undo_record(record, seams=seams)
        problems = [line for line in got if line.startswith(("could not", "still there"))]
        if problems:
            failed += 1
        else:
            store.drop(record.name, record.kind)
        lines.extend(got)

    head = "Reset: {} ({} change{})".format(name, len(touched), "" if len(touched) == 1 else "s")
    tail = ["", "  {} change{} kept, so /concierge reset {} tries again".format(
        failed, "" if failed == 1 else "s", name
    )] if failed else []
    if lines and all(line.startswith("kept:") for line in lines):
        head = "Reset: {}. Nothing inside it to take back yet".format(name)
        tail = []
    return "\n".join([head, ""] + ["  " + line for line in lines] + tail + [""])


__all__ = [
    "DEFAULT",
    "Refused",
    "bots",
    "card",
    "for_profile",
    "history_of",
    "is_selector",
    "name_of",
    "records",
    "fire",
    "reset",
    "resolve",
]
