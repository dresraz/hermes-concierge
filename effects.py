"""Effects: the side effects Concierge performs, with every core call injected.

This module is pure plumbing. It touches the filesystem, the skills hub and
the cron store only through the arguments a caller hands it, so tests can run
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
from typing import Any, Callable, Sequence

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


def _paragraph(items: Sequence[str]) -> str:
    """Join items into one prose paragraph of clauses."""
    clauses = [clause for clause in (_sentence(i) for i in items) if clause]
    if not clauses:
        return ""
    return ", ".join(clauses) + "."


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


def soul_text(title: str, duties: Sequence[str], boundaries: Sequence[str]) -> str:
    """Build the plain prose soul document.

    The first line names the role. The text is deterministic, uses no dashes
    as punctuation, and stays under the character limit.
    """
    role = _clean_prose(title) or "a concierge"
    parts = ["You are {}.".format(role)]

    duty_paragraph = _paragraph(duties)
    if duty_paragraph:
        parts.append("Your duties are: " + duty_paragraph)

    boundary_paragraph = _paragraph(boundaries)
    if boundary_paragraph:
        parts.append("Your boundaries are: " + boundary_paragraph)

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


def install_skills(names: Sequence[str], installer: Callable[[str], Any]) -> list:
    """Install each skill through the injected installer, in order."""
    records = []
    for name in names:
        result = installer(name)
        records.append({"name": name, "result": result})
    return records


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
    home = os.path.abspath(os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes"))
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


def arm_cron(prompt: str, creator: Callable[..., str], schedule: str = "* * * * *") -> str:
    """Create a scheduled job through the injected creator and return its id."""
    return creator(prompt=prompt, schedule=schedule)


def default_installer(name: str) -> Any:
    """Real skills hub installer, imported lazily so this module stays pure."""
    from hermes_cli.skills_hub import do_install

    return do_install(name)


def default_cron_creator(prompt: str, schedule: str, **kwargs: Any) -> str:
    """Real cron job creator, imported lazily so this module stays pure."""
    from cron.jobs import create_job

    job = create_job(prompt=prompt, schedule=schedule, **kwargs)
    if isinstance(job, dict):
        return str(job.get("id", ""))
    return str(job)
