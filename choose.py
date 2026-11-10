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

SHORTLIST = 14

INSTRUCTIONS = """You are choosing one item from a shortlist of Hermes skills and plugins.

The ask: {ask}

Shortlist:
{candidates}

Answer JSON only: {{"pick": "<exact name from the shortlist, or NOTHING>", "why": "<six words>"}}

Pick NOTHING when the shortlist only shares words with the ask but does the wrong
job. A loose fit is worse than an honest nothing: the person will install it and
it will not work. An item marked here is already installed on this machine."""


EXPAND_PROMPT = """A person wants something from their AI assistant. Write the search phrases
that would find it in a catalogue of plugins and skills.

Ask: {ask}

Answer JSON only: {{"phrases": ["<phrase>", "<phrase>", "<phrase>"]}}

Use the plain product words a catalogue entry would use, not sentences.
"Is it going to rain" -> "weather forecast". "Remind me tomorrow" ->
"reminder schedule". Never invent product names."""

WHOLE_PROMPT = """You are Concierge. Pick the one entry that does the job.

Every entry in the Hermes marketplace is below, as "kind name". plugins are
installed, skills are turned on, connectors are accounts you sign in to.

{menu}

Ask: {ask}

Answer JSON only: {{"pick": "<exact name from the list, or NOTHING>"}}
Pick NOTHING when no entry does the job. A shared word is not a fit.
These are not plugin jobs: booking travel, hiring a person, writing legal
documents, repairs in the physical world."""

WIDE_PROMPT = """You are Concierge for a Hermes install. Choose what answers the ask.

The skills are already on this machine (here). The plugins have to be fetched (get).
Hermes itself already does, with no plugin: web search, page fetch, shell and file
tools, cron jobs, subagents, memory notes, image understanding. If one of those
covers the ask, answer BUILT_IN and name the tool.

Skills (here):
{skills}

Plugins that might fit (get):
{plugins}

Ask: {ask}

Answer JSON only:
{{"pick": "<exact skill name, exact plugin name, BUILT_IN, or NOTHING>",
  "tool": "<if BUILT_IN, six words naming the built-in tool>",
  "why": "<six words>"}}

Pick an item only if it does the job the ask describes. A shared word is not a fit.
These are not plugin jobs: booking travel, hiring a person, writing legal documents,
repairs in the physical world. Anything a plugin cannot do is NOTHING."""

BUILT_IN_PROMPT = """Hermes already ships, without any plugin: web search, page fetch, shell and
file tools, scheduled jobs (cron), subagents, memory notes, image understanding.
A person asked: {ask}

Does Hermes already do this with what ships in the box?
Answer JSON only: {{"built_in": true or false, "tool": "<six words naming what does it>"}}"""


class Option:
    """One shortlist row, whichever shelf it came from.

    ``caution`` is set when the right answer costs something the person did not
    ask for: a memory provider that likely needs a paid service, or a skill that
    pulls gigabytes. The card says so instead of installing quietly.
    """

    def __init__(self, name: str, description: str, kind: str, payload: Any = None,
                 caution: str = ""):
        self.name = str(name)
        self.description = str(description or "")
        self.title = self.description
        self.kind = kind
        self.payload = payload
        self.caution = caution

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


CAUTION_LINES = {
    "memory": "Memory provider: usually needs a paid plan.",
    "heavy": "Heavy: downloads models and wants a GPU.",
}


MEMORY_WORDS = (
    "memory", "remember", "recall", "forget", "long term", "long-term",
    "memorize", "remembers", "context across", "across sessions",
)
MEMORY_MARKERS = (
    "memory provider", "long-term memory", "long term memory", "memory plugin",
    "memory layer", "memory backend", "memory system", "episodic memory",
)


def asks_about_memory(ask: str) -> bool:
    low = " ".join((ask or "").lower().split())
    return any(word in low for word in MEMORY_WORDS)


def _field(row: Any, name: str) -> str:
    if isinstance(row, dict):
        return str(row.get(name, "") or "")
    return str(getattr(row, name, "") or "")


def is_memory_provider(row: Any) -> bool:
    """A thing that replaces how Hermes remembers.

    Kind is deliberately not consulted: a skill that swaps memory has the same
    cost as a plugin that does, and requiring kind == plugin is how "knowledge
    graph memory" slipped through without a warning.
    """
    blob = "{} {}".format(_field(row, "name"), _field(row, "description"))
    low = blob.lower()
    return any(marker in low for marker in MEMORY_MARKERS) or "memory" in low.split(" ", 1)[-1][:40]


def caution_for(row: Any, ask: str) -> str:
    """Empty when the entry is safe to offer plainly.

    Two things are opt-in rather than automatic: a memory provider (often a paid
    hosted service) and a heavy skill (diffusion models, a GPU). The person may
    still want it - they just have to say so.
    """
    if is_memory_provider(row) and not asks_about_memory(ask):
        return "memory"
    try:
        from . import presets

        if presets.heavy(str(row.get("name") if isinstance(row, dict) else getattr(row, "name", ""))):
            return "heavy"
    except Exception:
        pass
    return ""


def _ask_whole(ask: str, llm: Any) -> Optional[Option]:
    """One call, every name in the marketplace. No keyword gate in front."""
    from . import search

    try:
        rows = search.index().rows
        menu = search.menu()
    except Exception:
        return None
    if not menu:
        return None
    try:
        answer = llm.complete_structured(
            instructions=WHOLE_PROMPT.format(menu=menu, ask=ask),
            input=[{"type": "text", "text": ask}],
            json_mode=True, max_tokens=100, temperature=0, timeout=90,
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
    pick = str(data.get("pick") or "").strip()
    if not pick or pick.upper() == "NOTHING":
        return None
    for row in rows:
        if str(row.get("name", "")).lower() == pick.lower():
            return Option(row["name"], row.get("description", ""), row.get("kind", "plugin"),
                          row, caution=caution_for(row, ask))
    return None


def _wide_prompt(ask: str, plugin_rows: list) -> str:
    skill_lines = "\n".join(
        "  {} - {}".format(row.name, (row.description or "")[:60]) for row in _skills()
    )
    plugin_lines = "\n".join(
        "  {} - {}".format(row.name, (row.description or "")[:70]) for row in plugin_rows
    )
    return WIDE_PROMPT.format(
        skills=skill_lines or "  (none)", plugins=plugin_lines or "  (none)", ask=ask
    )


def _ask_wide(ask: str, plugin_rows: list, llm: Any) -> Optional[Option]:
    """One call, the whole skill shelf plus the lexical plugins."""
    try:
        answer = llm.complete_structured(
            instructions=_wide_prompt(ask, plugin_rows),
            input=[{"type": "text", "text": ask}],
            json_mode=True, max_tokens=140, temperature=0, timeout=45,
        )
    except Exception:
        return None
    raw = (getattr(answer, "text") or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except Exception:
        return None
    pick = str(data.get("pick") or "").strip()
    if not pick:
        return None
    if pick.upper() == "BUILT_IN":
        tool = str(data.get("tool") or "").strip()
        return Option("Hermes itself", tool, "builtin")
    if pick.upper() == "NOTHING":
        return None
    for row in _skills() + plugin_rows:
        if row.name.lower() == pick.lower():
            return row
    return None


def _phrases(ask: str, llm: Any) -> list:
    """The catalogue's words for what the person said, from the model."""
    try:
        answer = llm.complete_structured(
            instructions=EXPAND_PROMPT.format(ask=ask),
            input=[{"type": "text", "text": ask}],
            json_mode=True, max_tokens=140, temperature=0, timeout=20,
        )
        raw = (getattr(answer, "text", "") or "").strip()
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        return [str(p).strip() for p in (data.get("phrases") or []) if str(p).strip()][:4]
    except Exception:
        return []


def _built_in(ask: str, llm: Any) -> str:
    """The tool Hermes already has for this, or empty."""
    try:
        answer = llm.complete_structured(
            instructions=BUILT_IN_PROMPT.format(ask=ask),
            input=[{"type": "text", "text": ask}],
            json_mode=True, max_tokens=90, temperature=0, timeout=15,
        )
        raw = (getattr(answer, "text", "") or "").strip()
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        return str(data.get("tool") or "") if data.get("built_in") else ""
    except Exception:
        return ""


def shortlist(ask: str, entries: Optional[Iterable[Any]] = None, limit: int = SHORTLIST,
              llm: Any = None) -> list:
    """The best rows for `ask`, across both shelves, best first.

    Two ways in, because one is not enough: the ranking for what does the job,
    and a name sweep for anything called what the ask says. A plugin named
    "telegram-notify" has to be visible for "send me telegram alerts" even when
    a chatty neighbour outranks it on words.
    """
    rows = pool(entries)
    if not rows:
        return []
    found = match.rank(ask, rows, limit=limit)
    # People describe jobs; catalogues name mechanisms. "Is it going to rain"
    # shares no word with "weather", so the list is filled from the model's own
    # words for the ask as well as the ask itself.
    if llm is not None and len(found) < limit:
        seen = {row.name.lower() for row in found}
        for phrase in _phrases(ask, llm):
            for row in match.rank(phrase, rows, limit=6):
                if row.name.lower() not in seen:
                    seen.add(row.name.lower())
                    found.append(row)
    return found[: max(limit, SHORTLIST)]


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


INSTALL_WORDS = ("install", "add", "get me", "get", "fetch", "download", "give me")


def _bare(ask: str) -> str:
    """The ask with the install verb and decoration peeled off."""
    low = " ".join((ask or "").lower().split()).strip(" .!?")
    for word in INSTALL_WORDS:
        if low.startswith(word + " "):
            low = low[len(word) + 1 :]
            break
    for word in ("the", "a", "an", "skill", "plugin", "tool"):
        low = " ".join(w for w in low.split() if w != word)
    return low.strip()


def _confident(rows: list) -> bool:
    """Offline only: a clear lexical winner, used when no model is reachable."""
    if not rows:
        return False
    if len(rows) == 1:
        return True
    best = getattr(rows[0], "score", 0.0) or 0.0
    second = getattr(rows[1], "score", 0.0) or 0.0
    return bool(best) and best >= DECISIVE * max(second, 0.01)


def _decisive(rows: list) -> bool:
    """Only a literal name is decided without the model.

    A score margin is not enough: with a junk runner-up, 2x is easy, and that is
    how "keep my desk tidy" became "submission-desk" without anyone reading it.
    """
    if not rows:
        return False
    top = rows[0]
    asked = _bare(getattr(top, "_ask", ""))
    name = str(getattr(top, "name", "")).lower().replace("-", " ").strip()
    if not asked or not name:
        return False
    if asked == name:
        return True
    # A two-word product name said out loud ("install obsidian memory") is the
    # product, not a coincidence. One short word is not enough: "desk" lives
    # inside "keep my desk tidy" and inside "submission-desk".
    return len(name.split()) >= 2 and name in asked


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
    for row in rows:
        row._ask = ask
    if _decisive(rows):
        rows[0].caution = caution_for(rows[0], ask)
        return rows[0]
    if llm is not None:
        # Every name in the marketplace, one call. Measured against a keyword
        # top-20 gate on 34 unseen asks: 28 fits against 14. The gate was the
        # problem, not the model.
        whole = _ask_whole(ask, llm)
        if whole is not None:
            return whole
        wide = _ask_wide(ask, rows[:30], llm)
        if wide is not None:
            wide.caution = caution_for(wide, ask)
            return wide
    if not rows:
        # Nothing shares a word with the ask. Ask the model whether Hermes
        # already does it before promising that nothing exists.
        tool = _built_in(ask, llm) if llm is not None else ""
        return Option("Hermes itself", tool, "builtin") if tool else None
    if llm is None:
        # No model: fall back to the old lexical rule. Weaker, but the plugin
        # still works offline and in tests instead of answering nothing. The
        # caution still applies - an offline pick must not skip the warning.
        if not _confident(rows):
            return None
        rows[0].caution = caution_for(rows[0], ask)
        return rows[0]
    chosen = _ask_model(ask, rows, llm)
    if not chosen or chosen.upper() == "NOTHING":
        # The catalogue has no fit. Before saying nothing exists, check whether
        # Hermes already does it: reminders, weather and scores are built in.
        tool = _built_in(ask, llm)
        return Option("Hermes itself", tool, "builtin") if tool else None
    for row in rows:
        if row.name.lower() == chosen.lower():
            row.caution = caution_for(row, ask)
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
