"""training.py: training a bot means writing a skill into that bot's profile.

A profile's skills live in ``<profile home>/skills/<name>/SKILL.md``, the same
path ``hermes skills install`` writes to, so a trained skill is an ordinary
skill: it shows up in that bot's skill list, its slash command and its prompt
index. Nothing new is invented, and ``/concierge undo`` can remove it by path.

The frontmatter is the two fields the loader needs. The body is the sentence in
the person's own words, wrapped in the four sections the curator looks for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from .bots import slugify

DESC_MAX = 60
SLUG_MAX = 40

_BODY = """\
---

# {title}

## When to use

Every reply from this bot, unless the person says otherwise for that turn.

## What to do

{instruction}

## How to check you did it

Before you send a reply, read it back once. If it does not match the
instruction above, rewrite it. Say what you changed in one line.

## Standing rules

- Show the work, not just the claim.
- Never send anything to a real person without asking first.
- Say plainly when you do not know something.
"""


@dataclass
class Trained:
    bot: str
    home: Path
    slug: str
    path: Path
    instruction: str
    created: bool = True

    @property
    def dir(self) -> Path:
        return self.path.parent


def _description(instruction: str) -> str:
    text = " ".join((instruction or "").split()).strip(" .")
    text = text[0].upper() + text[1:] if text else "A skill this bot learned"
    if len(text) <= DESC_MAX:
        return text
    cut = text[: DESC_MAX - 3].rsplit(" ", 1)[0]
    return cut + "..."


def _skill_slug(instruction: str) -> str:
    words = slugify(instruction).split("-")
    out = ""
    for word in words:
        candidate = f"{out}-{word}" if out else word
        if len(candidate) > SLUG_MAX:
            break
        out = candidate
    return out or "learned-skill"


def _free_slug(skills_dir: Path, base: str) -> str:
    slug = base
    n = 2
    while (skills_dir / slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def skill_text(slug: str, instruction: str) -> str:
    text = " ".join((instruction or "").split()).strip().rstrip(".")
    front = f"---\nname: {slug}\ndescription: {_description(text)}\n---\n\n"
    title = text[0].upper() + text[1:] if text else "Learned skill"
    return front + _BODY.format(title=title, instruction=text + ".")


def skills_dir(bot: str) -> Path:
    """Where core puts this profile's skills."""
    from . import seams

    return seams.profile_home(bot) / "skills"


def bots() -> list[str]:
    from . import seams

    return sorted(seams.profile_names())


def train(
    bot: str,
    instruction: str,
    *,
    home: Path | None = None,
    known: Sequence[str] | None = None,
    write: Callable[[Path, str], object] | None = None,
) -> Trained:
    """Write the skill. Raises :class:`UnknownBot` when the bot is not a profile."""
    name = slugify(bot)
    taken = list(known) if known is not None else bots()
    if name not in taken:
        raise UnknownBot(name, taken)
    instruction = " ".join((instruction or "").split()).strip()
    if not instruction:
        raise ValueError("training needs a sentence after the bot name")

    root = Path(home) if home is not None else skills_dir(name)
    slug = _free_slug(root, _skill_slug(instruction))
    path = root / slug / "SKILL.md"
    text = skill_text(slug, instruction)
    (write or _write)(path, text)
    return Trained(bot=name, home=root.parent, slug=slug, path=path, instruction=instruction)


class UnknownBot(Exception):
    def __init__(self, name: str, known: Sequence[str]):
        super().__init__(name)
        self.name = name
        self.known = list(known)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def receipt(result: Trained) -> tuple[list[str], bool]:
    """Read the skill back off the disk."""
    text = result.path.read_text(encoding="utf-8") if result.path.exists() else ""
    front_ok = text.startswith("---\n") and "\nname: " in text and "\ndescription: " in text
    desc = ""
    for line in text.splitlines()[1:]:
        if line.startswith("description: "):
            desc = line[len("description: "):]
            break
    listed = result.slug in [p.name for p in result.dir.parent.iterdir() if p.is_dir()] \
        if result.dir.parent.is_dir() else False
    ok = bool(text) and front_ok and listed and 0 < len(desc) <= DESC_MAX
    lines = [
        "  skill    " + str(result.path),
        "  front    " + ("name and description parse" if front_ok else "BROKEN"),
        "  listed   " + (f"{result.slug} is in {result.bot}'s skills" if listed else "NOT listed"),
        "  next     start a session as " + result.bot + " and it is in the prompt index",
    ]
    return lines, ok


def _plural(count: int) -> str:
    return f"{count} bot" + ("" if count == 1 else "s")


DEFAULT_HINT = "usage: /concierge train <bot>: <what it should always do>"


def guess_bot(text: str) -> tuple[str, str]:
    """Accept ``bot: sentence`` and ``bot sentence``."""
    raw = " ".join((text or "").split())
    name, _, rest = raw.partition(":")
    if rest.strip() and name.strip():
        return slugify(name), rest.strip()
    head, _, tail = raw.partition(" ")
    return slugify(head), tail.strip()


__all__ = [
    "Trained", "UnknownBot", "DEFAULT_HINT", "guess_bot", "receipt",
    "skill_text", "skills_dir", "train",
]
