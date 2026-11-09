"""improve.py: make a bot better, out of the marketplace.

Two kinds of improvement, one sentence. A **capability** is a skill that
already exists in the marketplace, installed into that bot. A **rule** is
standing behaviour ("always show the source first"), appended to the bot's
SOUL so it applies on every turn.

Any profile can be improved, not only ones Concierge made: the marketplace is
not a walled garden. Delete and reset stay limited to bots Concierge created,
because removing a stranger's profile is destructive.

Every addition is recorded by path, so undo reverses exactly that and nothing
else. Free text skills need no card: the receipt is the consent. Anything with
a key, a service or a daemon is named with its cost and waits for a yes.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

from . import discover, presets, seams
from .bots import slugify

# "Whatever is necessary" still has a ceiling: three things, each of which has to
# answer a gap in the sentence. Beyond that it is a shopping spree, not a fix.
MAX_ITEMS = 3

# A sentence in this shape is behaviour, not a capability.
RULE_WORDS = ("always", "never", "every time", "each time", "from now on", "don't", "do not")

RULE_HEAD = "\n\n## Learned rules\n\n"


@dataclass
class Item:
    kind: str  # "skill" or "rule"
    name: str
    why: str = ""
    kb: float = 0.0
    path: Path | None = None
    identifier: str = ""
    source: str = ""


@dataclass
class Plan:
    bot: str
    home: Path
    sentence: str
    items: list = field(default_factory=list)

    @property
    def skills(self) -> list:
        return [item for item in self.items if item.kind == "skill"]


def is_rule(sentence: str) -> bool:
    low = " " + " ".join((sentence or "").lower().split()) + " "
    return any(" " + word + " " in low or low.strip().startswith(word) for word in RULE_WORDS)


def resolve(bot: str) -> Optional[Path]:
    """The bot's home, or None. A bot is a directory that looks like one.

    Core's own existence check only sees profiles it registered, and an
    operator-made profile with a hand-written config still counts as a bot, so
    the test here is what a person would use: the folder, a config or a soul.
    """
    name = slugify(bot)
    if not name:
        return None
    try:
        from hermes_constants import get_hermes_home

        root = Path(str(get_hermes_home()))
    except Exception:
        from hermes_constants import get_hermes_home

        root = Path(str(get_hermes_home()))
    # Inside a bot the home is already the profile; its root is one level up.
    if root.parent.name == "profiles":
        root = root.parent.parent
    if name in ("default", "main"):
        return root
    home = root / "profiles" / name
    if not home.is_dir():
        return None
    if (home / "config.yaml").is_file() or (home / "SOUL.md").is_file() or (home / "skills").is_dir():
        return home
    return None


def installed(home: Path) -> set:
    skills = home / "skills"
    if not skills.is_dir():
        return set()
    return {item.parent.name for item in skills.glob("**/SKILL.md")}


def plan(bot: str, sentence: str, *, limit: int = MAX_ITEMS) -> Optional[Plan]:
    """What this sentence needs, or None when the bot does not exist."""
    home = resolve(bot)
    if home is None:
        return None
    text = " ".join((sentence or "").split()).strip()
    if not text:
        return None
    result = Plan(bot=slugify(bot), home=home, sentence=text)

    if is_rule(text):
        result.items.append(Item(kind="rule", name=text, why="standing rule"))
        return result

    have = installed(home)
    picks = discover.suggest(text, skip=have, limit=limit)
    for pick in picks:
        result.items.append(
            Item(
                kind="skill",
                name=pick["name"],
                why=", ".join(pick.get("why") or []),
                kb=pick["kb"],
                path=pick["path"],
                identifier="official/{}/{}".format(pick["category"], pick["name"]),
                source=pick.get("source", "optional"),
            )
        )
    return result


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


MAX_RULE_TEXT = 4000


def add_rule(plan_: Plan, *, home: Optional[Path] = None) -> Optional[dict]:
    """Append the rule to the bot's SOUL, once. Returns what undo needs.

    Three things a standing rule must never do: repeat itself every time it is
    said again, grow the file without end, or write through a symlink to a file
    outside the bot. Each is checked here, and the write goes through the same
    snapshot path every other soul write uses.
    """
    import os
    import shutil
    import uuid

    home = Path(str(home or plan_.home))
    soul = home / "SOUL.md"
    lock = _soul_lock(soul)
    try:
        if soul.is_symlink() and not str(soul.resolve()).startswith(str(home.resolve())):
            return None
        with lock:
            return _append_locked(soul, plan_, uuid)
    except OSError:
        return None


def _soul_lock(soul: Path):
    """One writer per soul, or two rules read the same bytes and one is lost."""
    import contextlib

    @contextlib.contextmanager
    def held():
        handle = None
        try:
            import fcntl

            handle = open(str(soul) + ".lock", "a+")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            if handle is not None:
                try:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
                handle.close()

    return held()


def _append_locked(soul: Path, plan_: Plan, uuid) -> Optional[dict]:
    """Read, append, write. Only ever called with the soul's lock held."""
    import os
    import shutil

    try:
        text = _read(soul)
        bullet = "- {}\n".format(plan_.sentence.rstrip("."))
        if bullet in text:
            return {"path": str(soul), "backup": "", "existed": True, "duplicate": True}
        if len(text) + len(bullet) > MAX_RULE_TEXT * 4:
            return None
        block = RULE_HEAD if RULE_HEAD not in text else "\n"
        backup = ""
        existed = soul.is_file()
        if existed:
            # One backup per rule: a single shared file made every earlier
            # receipt restore the same bytes, which is a lie about the state.
            backup = "{}.{}.concierge-backup".format(soul, uuid.uuid4().hex[:12])
            shutil.copy2(soul, backup)
        tmp = soul.with_name(soul.name + ".tmp")
        tmp.write_text(text + block + bullet, encoding="utf-8")
        os.replace(tmp, soul)
    except OSError:
        return None
    return {"path": str(soul), "backup": backup, "existed": existed}


def _install_one(bot: str, item: Item, *, home: Path, runner=None) -> bool:
    """Install one marketplace skill into that bot, then believe the disk."""
    home = Path(str(home))
    if runner is None and item.path is not None and item.source == "bundled":
        # A skill that already ships with Hermes: copy the folder the marketplace
        # read, not a re-resolved guess at where the tree lives.
        target = home / "skills" / item.path.parent.name / item.name
        try:
            shutil.copytree(item.path, target)
        except Exception:
            return False
    elif runner is not None:
        code, _ = runner(item.identifier)
        if code != 0:
            return False
    else:
        env = {**os.environ, "HERMES_HOME": str(home.parent.parent)}
        code, _ = presets._run(  # same package, one install path
            [presets._which_hermes(), "-p", bot, "skills", "install", item.identifier, "--yes"],
            presets.INSTALL_TIMEOUT,
            env,
        )
        if code != 0:
            return False
    return any((folder / "SKILL.md").is_file() for folder in (home / "skills").glob("**/" + item.name))


def apply(plan_: Plan, *, store: Any = None) -> list:
    """Do the plan. Returns receipt lines; records every path for undo."""
    from . import state

    store = store or state.Store()
    lines = []
    added = []
    for item in plan_.items:
        if item.kind == "rule":
            written = add_rule(plan_)
            if written and written.get("duplicate"):
                lines.append("  rule     already there: " + plan_.sentence)
            elif written:
                lines.append("  rule     " + plan_.sentence)
                store.add(
                    state.Installed(
                        name=plan_.bot,
                        kind="rule",
                        title=plan_.sentence[:120],
                        profile=plan_.bot,
                        soul_path=written["path"],
                        soul_backup=written["backup"],
                        soul_existed=bool(written["existed"]),
                    )
                )
            else:
                lines.append("  rule     could not write SOUL.md, nothing changed")
            continue
        if _install_one(plan_.bot, item, home=plan_.home):
            lines.append("  skill    {}".format(item.name))
            # Record the directory that actually exists: undo removes a path,
            # never a guess at where the skill might be.
            folder = next(
                (p.parent for p in (plan_.home / "skills").glob("**/" + item.name + "/SKILL.md")),
                None,
            )
            added.append(str(folder or plan_.home / "skills"))
            store.add(
                state.Installed(
                    name=item.name,
                    kind="skill",
                    title=plan_.sentence[:120],
                    profile=plan_.bot,
                    skills=[str(folder)] if folder else [],
                    enabled=True,
                )
            )
        else:
            lines.append("  skill    {} did not install".format(item.name))
    return lines


def receipt(plan_: Plan, lines: Sequence[str]) -> str:
    """One short block: what the bot got, and how to take it back."""
    if not plan_.items:
        return (
            "  Nothing in the marketplace fits that yet.\n"
            "  Try naming the job: /concierge improve {}: it needs to read scanned PDFs\n".format(plan_.bot)
        )
    names = ", ".join(item.name for item in plan_.items)
    head = (
        "Added {}".format(names)
        if plan_.bot in ("default", "custom", "main")
        else "Improved {}".format(plan_.bot)
    )
    tail = ["", "  undo     /concierge undo"]
    return "\n".join([head, ""] + list(lines) + tail)
