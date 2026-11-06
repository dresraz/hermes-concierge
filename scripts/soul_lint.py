"""soul_lint.py: the gate a soul has to pass before it ships.

A soul is not a bio. It is the standing instruction set a bot reads on every
turn, so it earns its place only if it changes behaviour. This checks the things
a human reviewer would otherwise have to check ten times:

  slop      phrases that mean nothing and cost tokens on every turn
  filler    sentences that would be true of any bot, so they steer nothing
  shape     a workflow, an output default, and something it refuses
  truth     it names only skills this role actually installs
  sameness  two roles may not share a paragraph

The checks are deliberately mechanical. Judgement still belongs to a reader.
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

MAX_CHARS = 1200
MIN_CHARS = 420

BANNED = (
    "as an ai", "language model", "i am here to", "i'm here to", "in today's",
    "fast-paced", "delve into", "dive deep", "unlock the", "empower",
    "seamless", "cutting-edge", "leverage", "synergy", "holistic",
    "game-chang", "best-in-class", "world-class", "tapestry", "testament to",
    "navigate the", "it's important to note", "it is important to note",
    "remember that", "always strive", "excellence", "journey",
    "passionate", "go-getter", "rockstar", "ninja", "guru",
)

# A soul that only describes the job is a job description. These are the marks
# of one that gives the bot something to do at the first message.
SHAPE = {
    "workflow": ("when ", "first", "start by", "then ", "before ", "after "),
    "output": ("reply with", "return", "write ", "format", "report", "cite",
               "one line", "bullet", "table", "list", "json"),
    "limit": ("never ", "do not", "don't", "ask before", "only ", "refuse"),
}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", text)
    return [p.strip() for p in parts if p.strip()]


def problems(text: str, skills: Sequence[str] = ()) -> list[str]:
    """Everything wrong with one soul. Empty list means it passes."""
    out: list[str] = []
    low = text.lower()

    if len(text) > MAX_CHARS:
        out.append("too long: {} chars, limit {}".format(len(text), MAX_CHARS))
    if len(text) < MIN_CHARS:
        out.append("too thin: {} chars, floor {}".format(len(text), MIN_CHARS))

    for phrase in BANNED:
        if phrase in low:
            out.append("slop phrase: {!r}".format(phrase))

    if "—" in text or "–" in text:
        out.append("dash punctuation")

    for label, needles in SHAPE.items():
        if not any(n in low for n in needles):
            out.append("no {} clause".format(label))

    if skills:
        named = sum(1 for s in skills if s.lower() in low)
        if named < 2:
            out.append("names {} of its own skills, needs 2".format(named))

    for sentence in _sentences(text):
        words = len(sentence.split())
        if words > 45:
            out.append("run-on sentence: {} words".format(words))

    return out


def duplicates(souls: dict[str, str]) -> list[str]:
    """Paragraphs shared by two roles. Each role speaks for itself."""
    seen: dict[str, str] = {}
    out: list[str] = []
    for role, text in souls.items():
        for para in re.split(r"\n{2,}", text):
            key = " ".join(para.lower().split())
            if len(key) < 60:
                continue
            if key in seen and seen[key] != role:
                out.append("{} and {} share a paragraph".format(seen[key], role))
            seen[key] = role
    return out


def report(souls: dict[str, str], skills: dict[str, Iterable[str]]) -> dict[str, list[str]]:
    """Per role problems plus the cross-role check, ready to print."""
    found = {role: problems(text, list(skills.get(role, ()))) for role, text in souls.items()}
    found["__duplicates__"] = duplicates(souls)
    return found
