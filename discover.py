"""discover.py: what else this bot could use, weighed before it is offered.

The preset table is a seed, not a verdict. A role sentence also says something
the table cannot know, and a person's own setup says more, so this module reads
the skill trees that are already on disk and finds two more things that fit.

It weighs before it offers: bytes, file count, helper scripts, and the tells
that mean a service, a daemon or a credential. Heavy skills never make the list,
and nothing here installs anything. The receipt names the picks and the operator
says yes with the same command that installs anything else.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence

from . import text as _text

# Under this, a skill is cheap enough to offer as an extra: a text skill with a
# few references, not an asset tree or a service.
MAX_KB = 130
MAX_FILES = 25

# A skill that needs one of these is not a "nice extra": it is a dependency the
# operator has to agree to on its own card.
# Only a piped download runs code at arrival: never a free extra.
def _has_shell_pipe(text: str) -> bool:
    """A curl piped into sh/bash, the way installers run code on arrival.

    The same shape the old pattern matched: "curl", then a pipe within the
    next 120 characters on the same line, then sh or bash as a whole word.
    """
    start = 0
    while True:
        at = text.find("curl", start)
        if at < 0:
            return False
        window = text[at + 4 : at + 4 + 121].split("\n", 1)[0]
        pipe = window.find("|")
        if pipe >= 0:
            tail = window[pipe + 1 :].lstrip()
            if tail.startswith("sudo"):
                after = len("sudo")
                if after >= len(tail) or not (tail[after].isalnum() or tail[after] == "_"):
                    tail = tail[after:].lstrip()
            for shell in ("sh", "bash"):
                if tail.startswith(shell) and (
                    len(tail) == len(shell) or not (tail[len(shell)].isalnum() or tail[len(shell)] == "_")
                ):
                    return True
        start = at + 4


STOP = frozenset(
    """
    and are but can for from has have into its not our out that the their then
    there these they this use used using very was were what when where which
    with you your all any get got how its just like make more most much need
    only other over same some such than them then they bot bots agent agents
    want wants wanted need needs give please help using read reads reading
    """.split()
)


def _fold(word: str) -> str:
    """One plural rule for both sides: pdfs and pdf are the same word."""
    if len(word) > 3 and word.endswith("es") and not word.endswith("ses"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


# Words that describe the marketplace rather than a job. A sentence asking for
# help with a house shares "skills" and "plugins" with half the catalogue; that
# is not evidence of anything, so these never carry weight.
FILLER = frozenset(
    """
    skill skills plugin plugins tool tools agent agents bot bots
    hermes marketplace catalog install setup use using help looking look find
    get add need want could would should please job work properly thing things
    """.split()
)


def _words(text: str) -> set[str]:
    return {
        _fold(w)
        for w in _text.words(text)
        if len(w) >= 3 and w not in STOP and w not in FILLER
    }


def _roots() -> list[Path]:
    """The two trees Hermes ships: optional first, then the bundled one.

    Every candidate is checked for a SKILL.md before it is trusted: an editable
    install reports a finder path as the package directory, and a bot's own
    HERMES_HOME has no checkout under it, so a path that merely exists is not
    proof that a marketplace is there.
    """
    candidates: list[Path] = []
    try:
        from . import seams

        bundled = Path(str(seams._bundled_root()))
        candidates += [bundled.parent / "optional-skills", bundled]
    except Exception:
        pass
    try:
        from hermes_constants import get_hermes_home

        home = Path(str(get_hermes_home()))
    except Exception:
        from hermes_constants import get_hermes_home

        home = Path(str(get_hermes_home()))
    for base in (home, Path.home() / ".hermes"):
        candidates += [base / "hermes-agent" / "skills", base / "hermes-agent" / "optional-skills"]

    seen: list[Path] = []
    for path in candidates:
        if path in seen:
            continue
        if any(path.glob("**/SKILL.md")) if path.is_dir() else False:
            seen.append(path)
    return seen


def _head(text: str, limit: int = 1200) -> tuple[str, str]:
    """Name and description from the frontmatter, plus the opening prose."""
    name = ""
    desc = ""
    for line in text.splitlines()[:40]:
        low = line.lower().strip()
        if low.startswith("name:") and not name:
            name = line.split(":", 1)[1].strip().strip('"\'')
        elif low.startswith("description:") and not desc:
            desc = line.split(":", 1)[1].strip().strip('"\'')
    return name, desc


def weigh(folder: Path) -> dict:
    """What a skill costs on disk, read off the folder itself."""
    files = 0
    size = 0
    scripts = 0
    for item in folder.rglob("*"):
        if not item.is_file():
            continue
        files += 1
        try:
            size += item.stat().st_size
        except OSError:
            continue
        if "scripts" in item.parts or item.suffix in (".py", ".sh"):
            scripts += 1
    return {"kb": round(size / 1024, 1), "files": files, "scripts": scripts}


def catalogue(roots: Optional[Sequence[Path]] = None) -> list[dict]:
    """Every skill on disk that is small enough to be an extra, with its weight."""
    out: list[dict] = []
    seen: set[str] = set()
    for root in roots or _roots():
        if not root.is_dir():
            continue
        source = "optional" if root.name == "optional-skills" else "bundled"
        for skill_file in root.glob("**/SKILL.md"):
            folder = skill_file.parent
            name = folder.name
            if name in seen or folder.parent.name.startswith("."):
                continue
            weight = weigh(folder)
            if weight["kb"] > MAX_KB or weight["files"] > MAX_FILES:
                continue
            try:
                text = skill_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            head = text.lower()
            if _has_shell_pipe(text):
                continue
            front_name, desc = _head(text)
            seen.add(name)
            out.append({
                "name": name,
                "source": source,
                "category": folder.parent.name,
                "path": folder,
                "description": desc or front_name,
                "text": text[:4000],
                **weight,
            })
    return out


def named_hits(sentence: str) -> list:
    """Skills whose own name is one of the words asked for, installed or not."""
    wanted = {_bare(word) for word in _words(sentence)}
    hits = [
        item["name"] for item in catalogue()
        if {_bare(word) for word in _words(item["name"].replace("-", " "))} & wanted
    ]
    return sorted(hits, key=lambda name: (len(name), name))


def _bare(word: str) -> str:
    """'pdfs' and 'pdf' are the same word to a person."""
    word = _fold(word)
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def suggest(
    sentence: str,
    role: str = "",
    *,
    blurb: str = "",
    skip: Iterable[str] = (),
    limit: int = 2,
) -> list[dict]:
    """Two extras that fit this sentence and this role, cheapest first.

    Only words that are rare in the catalogue count, and a skill needs two of
    them. A word every description carries proves nothing, and a wrong
    suggestion costs more than a quiet receipt.
    """
    from . import match as _match

    # The outcome vocabulary bridges a job to a mechanism ("spreadsheets" ->
    # sheets, excel), which is what makes a suggestion land on the right skill.
    wanted = _words(sentence) | _words(blurb) | _words(role)
    try:
        wanted |= {_fold(word) for word in _match.expand(sentence)}
    except Exception:
        pass
    role_words = _words(blurb) | _words(role)
    if not wanted:
        return []
    items = catalogue()
    if not items:
        return []
    blocked = {s.rsplit("/", 1)[-1] for s in skip}
    # Naming the thing by its own name always wins: "handle pdfs" is the skill
    # called pdf, not a coincidence of shared words.
    named = [
        item for item in items
        if item["name"] not in blocked
        and {_bare(word) for word in _words(item["name"].replace("-", " "))}
        & {_bare(word) for word in wanted}
    ]
    if named:
        named.sort(key=lambda item: (len(item["name"]), item["name"]))
        return named[:limit]
    frequency: dict[str, int] = {}
    for item in items:
        for word in _words(item["name"].replace("-", " ")) | _words(item["description"]):
            frequency[word] = frequency.get(word, 0) + 1
    # Rare enough to discriminate: at most a fifth of the catalogue, and never
    # a word so common that it is effectively filler.
    ceiling = max(3, min(40, len(items) // 50))

    scored: list[tuple[float, float, dict]] = []
    for item in items:
        if item["name"] in blocked:
            continue
        name_words = _words(item["name"].replace("-", " "))
        shared = name_words | _words(item["description"])
        hits = [word for word in wanted & shared if frequency.get(word, 0) <= ceiling]
        # Two rare words is a fit. One is a fit only when it is the skill's own
        # name and that name is rare in the catalogue: "polymarket" is the thing.
        named = [word for word in hits if word in name_words and frequency.get(word, 0) <= 2]
        # Two rare words, or the skill's own rare name. Never a single generic
        # word: that is how a coder bot was offered a skill about writing skills.
        if len(hits) < 2 and not named:
            continue
        # And at least one of those words must belong to the role itself, not
        # only to the sentence: an extra has to fit the job the bot was made for.
        if role_words and not (set(hits) & role_words) and len(hits) < 3:
            continue
        # A skill about Hermes itself is never an upgrade for a working bot.
        if item["name"].startswith("hermes-agent"):
            continue
        # A role suggestion has to be more than adjacent: three rare words, or
        # the skill's own rare name.
        if role_words and not named and len(hits) < 4:
            continue
        weight = sum(1.0 / max(1, frequency.get(word, 1)) for word in hits)
        scored.append((weight, item["kb"], {**item, "why": sorted(hits)[:4]}))
    scored.sort(key=lambda row: (-row[0], row[1], row[2]["name"]))
    return [item for _, _, item in scored[:limit]]
