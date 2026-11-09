"""Pick the one entry a person meant.

The matcher is a recall machine: it is good at getting the right answer into a
short list and bad at promising that the top of the list is the answer. This
module splits the two jobs. The list stays lexical and instant; one model call
reads the shortlist and picks, and it is allowed to say nothing fits.

Two rules keep it honest:
  * a decisive lexical lead is taken without a model call, so the obvious
    asks stay instant;
  * the model may only choose from the shortlist, never invent a name, and
    "nothing" is a valid answer.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from . import discover, match, seams

# How much better the top score has to be before the model is skipped.
DECISIVE = 2.0

# Errands a plugin cannot run: somebody has to leave the house or sign
# something. The model is agreeable enough to "help" with a travel search, so
# these are refused before it is asked. Small and explicit on purpose.
ERRANDS = (
    "book me", "book a flight", "book the flight", "book a hotel", "reserve a table",
    "hire a lawyer", "hire an attorney", "hire someone", "hire a person",
    "walk my dog", "fix my car", "fix the brakes", "repair my car",
    "write my will", "sign the contract for me", "pick up my kids",
)

SHORTLIST = 10

INSTRUCTIONS = """You are choosing one item from a shortlist of Hermes skills and plugins.

The ask: {ask}

Shortlist:
{candidates}

Answer JSON only: {{"pick": "<exact name from the shortlist, or NOTHING>", "why": "<six words>"}}

Pick NOTHING when the shortlist only shares words with the ask but does the wrong
job. A loose fit is worse than an honest nothing: the person will install it and
it will not work. An item marked here is already installed on this machine."""


class Option:
    """One shortlist row, whichever shelf it came from."""

    def __init__(self, name: str, description: str, kind: str, payload: Any = None):
        self.name = str(name)
        self.description = str(description or "")
        self.title = self.description
        self.kind = kind
        self.payload = payload

    @property
    def here(self) -> bool:
        return self.kind == "skill"


def _skills() -> list:
    rows = []
    try:
        for item in discover.catalogue():
            rows.append(
                Option(item["name"], item.get("why") or item.get("description") or "", "skill", item)
            )
    except Exception:
        pass
    return rows


def _plugins(entries: Optional[Iterable[Any]]) -> list:
    rows = []
    for entry in entries or ():
        rows.append(
            Option(getattr(entry, "name", ""), getattr(entry, "description", ""), "plugin", entry)
        )
    return rows


def pool(entries: Optional[Iterable[Any]] = None) -> list:
    """Everything installable in one shape: the built-in skills, then the catalog."""
    return _skills() + _plugins(entries if entries is not None else _live())


def _live() -> list:
    try:
        return seams.catalog()
    except Exception:
        return []


def shortlist(ask: str, entries: Optional[Iterable[Any]] = None, limit: int = SHORTLIST) -> list:
    """The best rows for `ask`, across both shelves, best first.

    Two ways in, because one is not enough: the ranking for what does the job,
    and a name sweep for anything called what the ask says. A plugin named
    "telegram-notify" has to be visible for "send me telegram alerts" even when
    a chatty neighbour outranks it on words.
    """
    rows = pool(entries)
    if not rows:
        return []
    return match.rank(ask, rows, limit=limit)


def _fmt(rows: list) -> str:
    lines = []
    for row in rows:
        tag = "here" if getattr(row, "kind", "") == "skill" else "get"
        lines.append("  {} [{}] - {}".format(row.name, tag, (row.description or "")[:110]))
    return "\n".join(lines)


def _ask_model(ask: str, rows: list, llm: Any) -> Optional[str]:
    prompt = INSTRUCTIONS.format(ask=ask, candidates=_fmt(rows))
    try:
        answer = llm.complete_structured(
            instructions=prompt,
            input=[{"type": "text", "text": ask}],
            json_mode=True,
            max_tokens=120,
            temperature=0,
            timeout=20,
        )
    except Exception:
        return None
    raw = (getattr(answer, "text", "") or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except Exception:
        return None
    return str(data.get("pick") or "").strip()


def _decisive(rows: list) -> bool:
    """A clear lexcial winner: no model call needed."""
    if not rows:
        return False
    top = rows[0]
    if len(rows) == 1:
        return True
    second = getattr(rows[1], "score", 0.0) or 0.0
    best = getattr(top, "score", 0.0) or 0.0
    if not best:
        return False
    return best >= DECISIVE * max(second, 0.01)


def pick(ask: str, llm: Any = None, entries: Optional[Iterable[Any]] = None) -> Optional[Any]:
    """The Option that answers `ask`, or None when nothing fits.

    A decisive lexical lead is taken as is. Everything else goes to the model,
    which may only pick from the list. With no model available the best
    lexical row is still better than nothing, but only when it is decisive.
    """
    low = " ".join((ask or "").lower().split())
    if any(phrase in low for phrase in ERRANDS):
        return None
    rows = shortlist(ask, entries)
    if not rows:
        return None
    if _decisive(rows):
        return rows[0]
    if llm is None:
        return None
    chosen = _ask_model(ask, rows, llm)
    if not chosen or chosen.upper() == "NOTHING":
        return None
    for row in rows:
        if row.name.lower() == chosen.lower():
            # A pick that sits far below the lexical top would be the model
            # ignoring the evidence, which is how a "pdf" ask turns into a
            # workspace plugin. It may reorder the leaders; it may not drag in
            # a straggler.
            top = getattr(rows[0], "score", 0.0) or 0.0
            mine = getattr(row, "score", 0.0) or 0.0
            if top and mine < 0.35 * top:
                return rows[0]
            return row
    return None
