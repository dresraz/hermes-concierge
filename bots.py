"""bots.py: hiring a bot means creating a Hermes profile with a soul.

One sentence in, one profile out. The sentence becomes:

  name     the last meaningful word, slugged, plus ``-bot``   (``inbox-bot``)
  title    the sentence as a role                             (``a bot that triages my inbox``)
  duties   the sentence split on and / commas / semicolons
  soul     ``effects.soul_text`` rendered into ``SOUL.md``
  home     core's ``create_profile``, so aliases, skills and config stay core's work

The name rule is deliberately mechanical: predictable beats clever when the
result appears on a card the person has to read once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from . import effects
from . import text as _text

NAME_MAX = 40
MAX_DUTIES = 5
MAX_TITLE = 90

BOUNDARIES = (
    "ask before sending anything to a real person",
    "never spend money without asking",
    "say plainly when you do not know something",
)

_DROP = frozenset("""
a an the this that these those bot bots agent agents assistant assistants
i me my we our you your it its of to for and or but with without on in at
by from as is are be been am do does did doing have has had can could should
would will just really very also too please which who whom
""".split())

_TAIL = frozenset("now daily forever always today tonight zero".split())

_FILLER_HEAD = (
    "i want ", "i need ", "i'd like ", "get me ", "give me ", "make me ",
    "build me ", "create ", "hire ", "a bot ", "an agent ", "a helper ",
)


@dataclass
class Spec:
    name: str
    title: str
    named: bool = False
    duties: list[str] = field(default_factory=list)
    boundaries: list[str] = field(default_factory=lambda: list(BOUNDARIES))

    def soul(self) -> str:
        return effects.soul_text(self.title, self.boundaries)


class Collision(Exception):
    """A profile with the derived name already exists."""

    def __init__(self, name: str, known: Sequence[str]):
        super().__init__(name)
        self.name = name
        self.known = list(known)


def slugify(text: str) -> str:
    return _text.slug(text)


def _words(text: str) -> list[str]:
    return _text.words(text)


def _explicit(text: str) -> tuple[str, str]:
    """``inbox-bot: keep my inbox at zero`` names itself."""
    if ":" not in text:
        return "", text
    left, right = text.split(":", 1)
    if not 1 <= len(left.split()) <= 3:
        return "", text
    name = slugify(left)[:NAME_MAX]
    return (name, right.strip()) if name else ("", text)


def _body(text: str) -> str:
    body = text
    lowered = body.lower()
    for filler in _FILLER_HEAD:
        if lowered.startswith(filler):
            body = body[len(filler):]
            break
    stripped = body.strip()
    bits = stripped.split(None, 1)
    if len(bits) == 2 and bits[0].lower() in ("that", "to", "which"):
        stripped = bits[1]
    return stripped.strip(" .!?,")


def _title(body: str) -> str:
    text = (body[:1].upper() + body[1:]) if body else body
    if len(text) > MAX_TITLE:
        text = text[:MAX_TITLE].rsplit(" ", 1)[0].rstrip(" ,.;:") + "..."
    return text


def _split_duties(body: str) -> list[str]:
    """Split on semicolons, commas and the word "and", the way the old split did."""
    parts: list[str] = []
    buf: list[str] = []
    i, n = 0, len(body)
    while i < n:
        char = body[i]
        if char == ";" or char == ",":
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        if body.startswith("and", i):
            left = body[i - 1] if i > 0 else ""
            right = body[i + 3] if i + 3 < n else ""
            if not (left.isalnum() or left == "_") and not (right.isalnum() or right == "_"):
                parts.append("".join(buf))
                buf = []
                i += 3
                continue
        buf.append(char)
        i += 1
    parts.append("".join(buf))
    return parts


def _duties(body: str) -> list[str]:
    parts = _split_duties(body)
    clean = [" ".join(p.split()).strip(" .!?,") for p in parts]
    return [p for p in clean if p][:MAX_DUTIES]


def _derive_name(words: Sequence[str]) -> str:
    head = ""
    for word in reversed(list(words)):
        if word in _TAIL or word in _DROP or len(word) < 3 or word.isdigit():
            continue
        head = word
        break
    return (slugify(head or "helper") + "-bot")[:NAME_MAX]


def spec(sentence: str, llm=None) -> Spec:
    """A name a person can pick out of a list, not a word from their sentence.

    A role sentence names the bot after the role: "make me a researcher that
    reads papers" makes researcher-bot, not papers-bot. The model picks the
    role from the preset names and blurbs; an explicit name still wins. With
    no model the name falls back to the last meaningful word.
    """
    from . import presets

    text = " ".join((sentence or "").split()).strip(" .!")
    name, rest = _explicit(text)
    body = _body(rest or text)
    role = presets.detect(body, llm)
    derived = "{}-bot".format(role.name) if role is not None else _derive_name(_words(body))
    return Spec(
        name=(name or derived)[:NAME_MAX],
        title=_title(body),
        named=bool(name),
        duties=_duties(body),
    )


def names() -> list[str]:
    """Profile names core already knows."""
    from . import seams

    return sorted(seams.profile_names())


def _create(name: str, soul: str, description: str):
    from . import seams

    return seams.create_profile(name, soul=soul, description=description)


def hire(
    sentence: str,
    *,
    known: Sequence[str] | None = None,
    create: Callable[[str, str, str], object] | None = None,
    llm=None,
) -> tuple[Spec, object]:
    """Create the bot. Raises :class:`Collision` when the name is taken."""
    plan = spec(sentence, llm=llm)
    taken = list(known) if known is not None else names()
    if plan.name in taken:
        raise Collision(plan.name, taken)
    soul = plan.soul()
    path = (create or _create)(plan.name, soul, plan.title)
    return plan, path


def _skills_on_disk(home) -> int:
    """Count installed skills, not categories: dot entries are bookkeeping, and a
    skill retired under ``.archive/`` is not installed any more."""
    skills_dir = home / "skills"
    if not skills_dir.is_dir():
        return 0
    found = 0
    for marker in skills_dir.rglob("SKILL.md"):
        rel = marker.relative_to(skills_dir)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if ".archive" in rel.parts:
            continue
        found += 1
    return found


def _soul_gist(soul_text: str) -> str:
    """The first real sentence of the soul: what the bot says about itself."""
    for line in soul_text.splitlines():
        clean = " ".join(line.strip().lstrip("#").split())
        if len(clean) > 12 and not clean.endswith(":") and clean.lower() != "learned rules":
            if len(clean) <= 72:
                return clean
            cut = clean[:72].rsplit(" ", 1)[0].rstrip(",;")
            return cut + "."
    return "a personality"


def receipt(plan: Spec, path: object, known: Sequence[str] | None = None,
            count_skills: bool = True) -> tuple[list[str], bool]:
    """Read the new profile off the disk and report what is really there."""
    from pathlib import Path

    home = Path(str(path))
    soul_file = home / "SOUL.md"
    soul_text = soul_file.read_text(encoding="utf-8") if soul_file.exists() else ""
    skills = _skills_on_disk(home)
    # Ask core whether the profile exists now. Comparing against the list we
    # took before creating it would always say "not listed".
    listed = False
    try:
        from . import seams

        listed = bool(seams.profile_exists(plan.name))
    except Exception:
        listed = plan.name in (list(known) if known is not None else names())
    ok = home.is_dir() and bool(soul_text.strip()) and listed
    lines = ["Soul: " + (_soul_gist(soul_text) if soul_text else "missing")]
    # One count only: when the role line below names the skills, a second
    # number above it reads as a mismatch to anyone who is not the author.
    if count_skills and skills:
        lines.append("{} skills installed.".format(skills))
    if not listed:
        lines.append("The profile is not confirmed yet, but it is there on disk.")
    return lines, ok
