"""Effects: the side effects Concierge performs, with every core call injected.

This module is pure plumbing. It touches the filesystem, the skills hub and
the filesystem only through the arguments a caller hands it, so tests can run
against temporary directories and fake installers without importing core.

The real runtime bindings live in lazy factory functions at the bottom of this
file. Those functions import core inside their bodies, which keeps this
module importable with the standard library alone.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from typing import Any, Sequence

BACKUP_SUFFIX = ".concierge-backup"
MAX_SOUL_CHARS = 1200

_DASH_PUNCTUATION = re.compile(r"\s+[-]{1,2}\s+")
_DASH_CHARS = ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015", "\u2212")


@dataclass(frozen=True)
class Snapshot:
    """What a soul write changed, so the write can be undone exactly."""

    path: str
    backup: str  # empty when the file did not exist
    existed: bool


def _clean_prose(text: str) -> str:
    """Normalise whitespace and remove dashes used as punctuation."""
    out = " ".join(str(text).split())
    for dash in _DASH_CHARS:
        out = out.replace(dash, " ")
    out = _DASH_PUNCTUATION.sub(", ", out)
    return " ".join(out.split())


def _sentence(item: str) -> str:
    """Turn one duty or boundary into a single plain clause, text kept as given."""
    text = _clean_prose(item)
    if not text:
        return ""
    return text.rstrip(". ")


def _cap(text: str, limit: int = MAX_SOUL_CHARS) -> str:
    """Keep the text under the character limit, cutting on a sentence end."""
    if len(text) < limit:
        return text
    window = text[: limit - 1]
    cut = window.rfind(". ")
    if cut > 0:
        window = window[: cut + 1]
    window = window.rstrip()
    if len(window) >= limit:
        window = window[: limit - 1].rstrip()
    return window


def _base_verb(word: str) -> str:
    """Third person to base form: advertises -> advertise, sells -> sell.

    Only verbs can carry a trailing s here, so the check is the shape of the
    word, not a dictionary. Irregulars are the four that show up in a job
    sentence.
    """
    low = word.lower()
    irregular = {"is": "be", "has": "have", "does": "do", "goes": "go"}
    if low in irregular:
        return irregular[low]
    if low.endswith("ies") and len(low) > 4:
        return low[:-3] + "y"
    if low.endswith(("ches", "shes", "sses", "xes", "zes", "oes")):
        return low[:-2]
    if low.endswith("s") and not low.endswith(("ss", "us", "is")):
        return low[:-1]
    return low


def _is_noun_phrase(phrase: str) -> bool:
    """``a tutor for biology`` is a role; ``sells my house`` is a job."""
    first = phrase.split()[0].lower().strip(",.") if phrase.split() else ""
    return first in ("a", "an", "the")


def soul_text(title: str, boundaries: Sequence[str]) -> str:
    """Build the soul a bot without a preset role reads on every turn.

    The owner's sentence is a job, not the bot's name, so it never lands after
    "You are". A job sentence becomes "You help <base verb> ..." and a noun
    phrase becomes "You are <phrase>". Nothing here is a guess about names,
    and no clause is split at "and", which is how a duty line used to end up
    holding a bare verb.
    """
    phrase = _clean_prose(title).rstrip(" .!?,")
    if not phrase:
        phrase = "with the work in front of you"
    if _is_noun_phrase(phrase):
        words = [phrase.split()[0].lower()] + phrase.split()[1:]
        head = "You are {}.".format(" ".join(words))
    else:
        words = phrase.split()
        words[0] = _base_verb(words[0])
        for index in range(1, len(words)):
            if words[index - 1].lower() in ("and", "or", "then"):
                token = words[index]
                if token.isalpha() and token.endswith("s") and not token.endswith(("ss", "us", "is")):
                    words[index] = _base_verb(token)
        head = "You help {}.".format(" ".join(words))

    limits = [_sentence(item) for item in boundaries if _sentence(item)]
    parts = [
        head,
        "How you work\n"
        "- Answer first: the first line of every reply is the answer, then the detail.\n"
        "- Ask one short question when the request is ambiguous instead of guessing.\n"
        "- Read the real thing before you answer: the file, the page, the number.",
    ]
    if limits:
        caps = [item[:1].upper() + item[1:] + "." for item in limits]
        parts.append("Limits\n" + "\n".join("- " + item for item in caps))
    return _cap("\n\n".join(parts))


def write_soul(path: str, text: str) -> Snapshot:
    """Write the soul file, backing up an existing one before overwriting."""
    existed = os.path.exists(path)
    backup = ""
    if existed:
        backup = path + BACKUP_SUFFIX
        shutil.copy2(path, backup)
    else:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(text.encode("utf-8"))
    return Snapshot(path=path, backup=backup, existed=existed)


def restore_soul(snapshot: Snapshot) -> None:
    """Undo a soul write: put the backup back, or remove the new file."""
    if snapshot.existed:
        shutil.copy2(snapshot.backup, snapshot.path)
        return
    try:
        os.remove(snapshot.path)
    except FileNotFoundError:
        pass


def remove_skill_dir(path: str) -> bool:
    """Take a skill directory away. True when nothing is left at that path.

    `/train` writes a plain directory into a profile's skills folder, so undo is
    a delete of that one directory and no core call. A directory that is already
    gone counts as removed: undo must be safe to run twice.

    A receipt is data, and data can be wrong, so the path is checked before it is
    deleted: it must still look like one skill, which means a SKILL.md inside it
    and no skills inside that. Refusing is loud on purpose, because the caller
    turns the exception into "could not remove" and keeps the receipt.
    """
    target = os.path.abspath(path)
    try:
        from hermes_constants import get_hermes_home

        home = os.path.abspath(str(get_hermes_home()))
    except Exception:
        home = os.path.abspath(os.path.expanduser("~/.hermes"))
    roots = (os.path.join(home, "profiles"), os.path.join(home, "skills"))
    if not any((target + os.sep).startswith(root + os.sep) for root in roots):
        raise ValueError("refusing to delete {}: not inside a profile".format(target))
    if not os.path.exists(target):
        return True  # already undone is undone, not an error
    if not os.path.isdir(target) or os.path.islink(target):
        raise ValueError("refusing to delete {}: not a directory".format(target))
    if not os.path.isfile(os.path.join(target, "SKILL.md")):
        raise ValueError("refusing to delete {}: no SKILL.md, so it is not a skill".format(target))
    for entry in os.listdir(target):
        if os.path.isdir(os.path.join(target, entry)) and os.path.isfile(
            os.path.join(target, entry, "SKILL.md")
        ):
            raise ValueError("refusing to delete {}: it holds other skills".format(target))
    shutil.rmtree(target)
    return not os.path.exists(target)

