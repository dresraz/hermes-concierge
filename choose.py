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
installed, skills are turned on.

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


def _field(row: Any, name: str) -> str:
    if isinstance(row, dict):
        return str(row.get(name, "") or "")
    return str(getattr(row, name, "") or "")


MEMORY_ENTRY_PROMPT = """Does this marketplace entry provide memory: recalling notes across sessions,
a memory provider, a context engine, persistent notes?

Name: {name}
Description: {description}
Requires: {requires}

Answer JSON only: {{"memory": true or false}}"""

MEMORY_ASK_PROMPT = """Does this person ask for memory: remembering across sessions, recalling notes,
a memory provider, persistent notes?

Ask: {ask}

Answer JSON only: {{"memory": true or false}}"""


def asks_about_memory(ask: str, llm: Any = None) -> bool:
    """True when the ask itself requests memory, by the model's reading.

    With no model the answer is False, so a memory provider is still
    flagged rather than installed quietly.
    """
    if llm is None:
        return False
    import json

    try:
        answer = llm.complete_structured(
            instructions=MEMORY_ASK_PROMPT.format(
                ask=" ".join(str(ask or "").split())[:300]),
            input=[{"type": "text", "text": str(ask or "")}],
            json_mode=True,
            max_tokens=30,
            temperature=0,
            timeout=15,
        )
    except Exception:
        return False
    raw = (getattr(answer, "text", "") or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return False
    try:
        return bool(json.loads(raw[start : end + 1]).get("memory"))
    except Exception:
        return False


def is_memory_provider(row: Any, llm: Any = None) -> bool:
    """A thing that replaces how Hermes remembers, by its own metadata.

    Kind is deliberately not consulted: a skill that swaps memory has the
    same cost as a plugin that does. The entry names itself; no name list
    decides. With no model the entry's own name and description are read
    plainly for the word itself.
    """
    name = _field(row, "name")
    description = _field(row, "description") or _field(row, "title")
    requires = ""
    try:
        from . import match as _match

        caps = _match.capabilities(
            row.get("payload") if isinstance(row, dict) and row.get("payload") is not None
            else getattr(row, "payload", row)
        )
        required = caps.get("requires_env") or ()
        if isinstance(required, str):
            required = (required,)
        requires = ", ".join(str(k) for k in required)
    except Exception:
        requires = ""
    if llm is None:
        blob = "{} {} {}".format(name, description, requires)
        return "memory" in blob.lower()
    import json

    try:
        answer = llm.complete_structured(
            instructions=MEMORY_ENTRY_PROMPT.format(
                name=name[:120], description=description[:600],
                requires=requires[:200]),
            input=[{"type": "text", "text": "{} {}".format(name, description)[:600]}],
            json_mode=True,
            max_tokens=30,
            temperature=0,
            timeout=15,
        )
    except Exception:
        return "memory" in "{} {}".format(name, description).lower()
    raw = (getattr(answer, "text", "") or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return "memory" in "{} {}".format(name, description).lower()
    try:
        return bool(json.loads(raw[start : end + 1]).get("memory"))
    except Exception:
        return "memory" in "{} {}".format(name, description).lower()


def caution_for(row: Any, ask: str, llm: Any = None) -> str:
    """Empty when the entry is safe to offer plainly.

    Two things are opt-in rather than automatic: a memory provider (often a paid
    hosted service) and a heavy skill (diffusion models, a GPU). The person may
    still want it - they just have to say so.
    """
    if is_memory_provider(row, llm) and not asks_about_memory(ask, llm):
        return "memory"
    try:
        from . import presets

        if presets.heavy(row, llm):
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
                          row, caution=caution_for(row, ask, llm))
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

    With a model the ranked shortlist comes from the model's own ordering
    of the candidate names. With no model it is plain token overlap between
    the ask and each entry's own name and description: no synonym table, no
    stopword list.
    """
    rows = pool(entries)
    if not rows:
        return []
    if llm is not None:
        ordered = _model_order(ask, rows, llm, limit=max(limit, SHORTLIST))
        if ordered:
            return ordered
    return _lexical_rank(ask, rows, limit=max(limit, SHORTLIST))


ORDER_PROMPT = """You rank marketplace entries for one ask. Order the best fits first.

Ask: {ask}

Candidates (exact names):
{candidates}

Answer JSON only: {{"order": ["<exact name>", ...]}}
List the best fits first, up to {limit} names. Only names from the candidates
list, never a new one. Leave out anything that does not do the job. A shared
word is not a fit."""


def _model_order(ask: str, rows: list, llm: Any, limit: int) -> list:
    """The candidate names in the model's order, best first.

    The model may only choose from the names on the call; anything outside
    the list is refused.
    """
    import json

    by_name = {row.name.lower(): row for row in rows}
    lines = "\n".join(
        "- {}: {}".format(row.name, (row.description or "")[:70]) for row in rows[:400]
    )
    if not lines:
        return []
    try:
        answer = llm.complete_structured(
            instructions=ORDER_PROMPT.format(
                ask=" ".join(str(ask or "").split())[:300],
                candidates=lines,
                limit=limit,
            ),
            input=[{"type": "text", "text": str(ask or "")}],
            json_mode=True,
            max_tokens=min(400, 20 * limit),
            temperature=0,
            timeout=45,
        )
    except Exception:
        return []
    raw = (getattr(answer, "text", "") or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        names = json.loads(raw[start : end + 1]).get("order") or []
    except Exception:
        return []
    out = []
    seen = set()
    for name in names:
        key = str(name or "").strip().lower()
        if not key or key in seen:
            continue
        row = by_name.get(key)
        if row is None:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    for index, row in enumerate(out):
        try:
            row.score = float(len(out) - index)
        except Exception:
            pass
        try:
            row.matched = ["model"]
        except Exception:
            pass
    return out


def _plain_tokens(text: str) -> set:
    """Lower-cased alphanumeric tokens longer than one char, singular-folded."""
    from . import text as _text

    out = set()
    for word in _text.words(text or ""):
        if len(word) <= 1:
            continue
        folded = word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word
        out.add(folded)
    return out


def _lexical_rank(ask: str, rows: list, limit: int) -> list:
    """Plain token overlap, no synonym table and no stopword list.

    The offline fallback: words the ask shares with the entry's own name
    weigh double, description words weigh single. Ties break by name so the
    order is stable.
    """
    asked = _plain_tokens(ask)
    if not asked:
        return []
    scored = []
    for row in rows:
        name_words = _plain_tokens(str(getattr(row, "name", "") or "").replace("-", " "))
        desc_words = _plain_tokens(
            str(getattr(row, "description", "") or "")
            + " " + str(getattr(row, "title", "") or "")
        )
        shared_name = asked & name_words
        shared_desc = asked & desc_words
        score = 2 * len(shared_name) + len(shared_desc)
        if score <= 0:
            continue
        try:
            row.score = float(score)
        except Exception:
            pass
        try:
            row.matched = sorted(shared_name | shared_desc)
        except Exception:
            pass
        scored.append(row)
    scored.sort(key=lambda row: (-getattr(row, "score", 0.0), row.name))
    return scored[:limit]


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


def _bare(ask: str) -> str:
    """The ask with decoration peeled off.

    The head verb is gone already: the command layer strips it before the ask
    gets here, so only articles and shelf words are left to ignore.
    """
    low = " ".join((ask or "").lower().split()).strip(" .!?")
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
    rows = shortlist(ask, entries, llm=llm)
    for row in rows:
        row._ask = ask
    if _decisive(rows):
        rows[0].caution = caution_for(rows[0], ask, llm)
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
            wide.caution = caution_for(wide, ask, llm)
            return wide
    if not rows:
        # Nothing shares a word with the ask. Ask the model whether Hermes
        # already does it before promising that nothing exists.
        tool = _built_in(ask, llm) if llm is not None else ""
        return Option("Hermes itself", tool, "builtin") if tool else None
    if llm is None:
        # No model: fall back to the plain lexical rule. Weaker, but the plugin
        # still works offline and in tests instead of answering nothing. The
        # caution still applies - an offline pick must not skip the warning.
        if not _confident(rows):
            return None
        rows[0].caution = caution_for(rows[0], ask, llm)
        return rows[0]
    chosen = _ask_model(ask, rows, llm)
    if not chosen or chosen.upper() == "NOTHING":
        # The catalogue has no fit. Before saying nothing exists, check whether
        # Hermes already does it: reminders, weather and scores are built in.
        tool = _built_in(ask, llm)
        return Option("Hermes itself", tool, "builtin") if tool else None
    for row in rows:
        if row.name.lower() == chosen.lower():
            row.caution = caution_for(row, ask, llm)
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
