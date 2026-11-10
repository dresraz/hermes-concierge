"""shelf.py: what is installable, read at the moment you look.

Three sources, one list: the skills already shipped on this machine, the plugin
catalog, and the bots this home has. Nothing is stored between sessions, so a
thing you install leaves the shelf and a thing you remove comes back.

The shelf never installs on its own. It is a window: you look, you pick a
number, and the install path you already know runs.
"""

from __future__ import annotations

import pathlib

from typing import Any, Optional

from . import discover, match, seams

# One screen. A thousand entries in chat is not a shop window.
LIMIT = 8

# The last listing per conversation, so "3" means item 3 of what was just shown.
# A number is only meaningful while the list is still on screen, so entries
# expire, and the map cannot grow with every chat the gateway has ever served.
_LAST: dict = {}
LAST_TTL = 600
MAX_SESSIONS = 32


def _here() -> str:
    name = ""
    try:
        name = seams.current_profile()
    except Exception:
        name = ""
    from . import improve

    return name if improve.resolve(name) else "default"


def _installed() -> set:
    from . import improve

    home = improve.resolve(_here())
    return improve.installed(home) if home is not None else set()


def _plugins(query: str = "", limit: int = LIMIT) -> list:
    try:
        catalog = seams.catalog()
    except Exception:
        return []
    if not query:
        return []
    ranked = match.rank(query, catalog, limit=limit)
    return [
        {
            "kind": "plugin",
            "name": candidate.name,
            "weight": "",
            "why": ", ".join(getattr(candidate, "matched", [])[:3]),
        }
        for candidate in ranked
    ]


def _skills(query: str = "", limit: int = LIMIT) -> list:
    have = _installed()
    rows = []
    wanted = discover._words(query)
    for item in discover.catalogue():
        haystack = discover._words(item["name"].replace("-", " ") + " " + (item["description"] or ""))
        # Two words mean both, not either: "pdf scan" is not "pdf OR scan".
        if wanted and not (wanted <= haystack):
            continue
        rows.append(
            {
                "kind": "skill",
                "name": item["name"],
                "weight": "{} KB".format(int(item["kb"])),
                "why": (item["description"] or "")[:48],
                "path": item["path"],
                "source": item.get("source", "optional"),
                "category": item.get("category", ""),
                "installed": item["name"] in have,
            }
        )
    rows.sort(key=lambda row: (
        row["installed"],
        -len(wanted & discover._words(row["name"].replace("-", " "))),
        row["name"],
    ))
    return rows[:limit]


def _bot_rows(query: str = "", limit: int = 3) -> list:
    """The ten starters, as things you can pick like anything else."""
    from . import presets

    wanted = discover._words(query)
    rows = []
    for role in presets.ROLES:
        haystack = discover._words(role.name + " " + role.blurb)
        if wanted and not (wanted & haystack):
            continue
        rows.append(
            {
                "kind": "bot",
                "name": role.name,
                "weight": "{} skills".format(len(role.picks)),
                "why": role.blurb[:48],
                "sentence": "a {} that {}".format(role.label, role.blurb),
            }
        )
    return rows[:limit]


def items(query: str = "", limit: int = LIMIT) -> list:
    """Bots to make, then skills already here, then plugins to fetch.

    The marketplace rows come from the same ranked list install offers, so
    the same words show the same names in both places.
    """
    return _bot_rows(query, 3) + _ranked(query, limit)


def _ranked(query: str = "", limit: int = LIMIT) -> list:
    """Marketplace rows off the shared search, or the local shelves offline."""
    try:
        from . import search as _search

        ranked = _search.candidates(query, limit=200)
    except Exception:
        ranked = []
    if ranked:
        have = _installed()
        out = []
        for row in ranked:
            name = str(row.get("name", "") or "")
            if not name:
                continue
            if row.get("kind") == "skill":
                payload = row.get("payload") or {}
                out.append(
                    {
                        "kind": "skill",
                        "name": name,
                        "weight": "",
                        "why": str(row.get("description", "") or "")[:48],
                        "path": payload.get("path", "") if isinstance(payload, dict) else "",
                        "source": payload.get("source", "") if isinstance(payload, dict) else "",
                        "category": payload.get("category", "") if isinstance(payload, dict) else "",
                        "installed": name in have,
                    }
                )
            else:
                out.append(
                    {
                        "kind": "plugin",
                        "name": name,
                        "weight": "",
                        "why": str(row.get("description", "") or "")[:48],
                    }
                )
        return out[:limit]
    return _skills(query, limit) + _plugins(query, max(2, limit // 2))


def _build() -> str:
    """The commit answering this card, so a stale session is obvious at a glance."""
    try:
        import subprocess

        here = pathlib.Path(__file__).resolve().parent
        sha = subprocess.run(
            ["git", "-C", str(here), "rev-parse", "--short=7", "HEAD"],
            capture_output=True, text=True, timeout=2,
        ).stdout.strip()
        if sha:
            return "{} {}".format(_version(), sha)
    except Exception:
        pass
    return _version()


def _version() -> str:
    try:
        text = (pathlib.Path(__file__).resolve().parent / "plugin.yaml").read_text()
        for line in text.splitlines():
            if line.startswith("version:"):
                parts = line[len("version:"):].split()
                if parts:
                    return parts[0]
        return "?"
    except Exception:
        return "?"


def overview() -> str:
    """One screen: what is here, and how to look further."""
    here = _installed()
    bots = []
    from . import improve

    root = improve.resolve("default")
    if root is not None and (root / "profiles").is_dir():
        bots = sorted(p.name for p in (root / "profiles").iterdir() if p.is_dir() and not p.name.startswith("."))
    # Count what the search actually reads, not what happens to be on this disk.
    # The shelf said "144 skills" while a search could reach 711, which is the
    # kind of number a reader checks once and stops trusting.
    try:
        from . import search

        total_plugins = len(search._plugins_meta().get("rows") or []) or len(seams.catalog())
        available = len(search._skills_meta().get("rows") or [])
        if not available:
            # A bot profile keeps its own cache and starts empty; the owner's list
            # is the same marketplace, so read it instead of claiming 144.
            import json
            import pathlib as _pl

            from hermes_constants import get_hermes_home

            home_now = _pl.Path(str(get_hermes_home()))
            owner = home_now.parent.parent if home_now.parent.name == "profiles" else home_now
            meta = owner / "cache" / "concierge" / "skills-meta.json"
            try:
                available = len(json.loads(meta.read_text()).get("rows") or [])
            except Exception:
                available = 0
        available = available or len(discover.catalogue())
    except Exception:
        total_plugins = 0
        available = len(discover.catalogue())
    def _n(count: int, word: str) -> str:
        return "{} {}".format(count, word if count == 1 else word + "s")

    # A profile that carries the whole shipped tree should not read as 258
    # "installed" skills: that is the tree, not a choice the person made.
    if not here:
        here_bit = ""
    elif len(here) >= 60:
        here_bit = "The full skill tree is available here."
    else:
        here_bit = "{} added.".format(_n(len(here), "skill"))
    if bots:
        shown = ", ".join(bots[:3])
        if len(bots) > 3:
            shown += " and {} more".format(len(bots) - 3)
        bot_bit = "{}: {}.".format(_n(len(bots), "bot"), shown)
    else:
        bot_bit = "No bots yet."
    lines = [
        "Concierge",
        "",
        bot_bit,
        here_bit,
        "On the shelf: {} and {}.".format(
            _n(available, "skill"), _n(total_plugins, "plugin")
        ),
        "",
        "Build {}.".format(_build()),
        "",
        "Say what you need in one sentence, or look first:",
        "/concierge browse pdf looks through what is available.",
        "/concierge help lists the commands.",
        "",
    ]
    return "\n".join(lines)


def _rank(rows: list, query: str) -> list:
    """A row named after the word beats a row that merely mentions it."""
    word = (query or "").strip().lower()
    if not word:
        return rows
    def key(row: dict) -> tuple:
        name = str(row.get("name", "")).lower()
        return (0 if word in name else 1, 0 if word in str(row.get("why", "")).lower() else 1)
    return sorted(rows, key=key)


def browse(query: str = "", session_key: str = "", page: int = 1) -> str:
    """A numbered window. The number is the pick. Page 2 is the next window."""
    import time

    everything = _rank(items(query, limit=200), query)
    page = max(1, int(page or 1))
    start = (page - 1) * LIMIT
    rows = everything[start:start + LIMIT]
    if len(_LAST) >= MAX_SESSIONS:
        oldest = min(_LAST, key=lambda key: _LAST[key][0])
        _LAST.pop(oldest, None)
    _LAST[session_key or ""] = (time.time(), rows)
    pages = max(1, (len(everything) + LIMIT - 1) // LIMIT)
    if not rows:
        if everything:
            return "\n".join([
                "There {} only {} page{}. You asked for page {}.".format(
                    "is" if pages == 1 else "are", pages, "" if pages == 1 else "s", page,
                ),
                "Back to the start: /concierge browse {}".format(query),
                "",
            ])
        return "\n".join([
            "Nothing matches {}.".format(query),
            "See everything: /concierge browse",
            "",
        ])
    lines = []
    for index, row in enumerate(rows, start=1):
        bits = ["a " + row["kind"]]
        if row.get("installed"):
            bits.append("already here")
        elif row["weight"]:
            bits.append(row["weight"])
        why = row["why"]
        line = "{}. {}, {}".format(index, row["name"], ", ".join(bits))
        if why:
            line += ": {}".format(why)
        else:
            line += "."
        lines.append(line)
    if pages > 1:
        if page < pages:
            nxt = "Next: /concierge browse {} {}.".format(query, page + 1)
        else:
            nxt = "That is the last page."
        lines += ["", "Page {} of {}. {}".format(page, pages, nxt)]
    lines += ["", "Reply with a number to install one, or say the job in one sentence.", ""]
    return "\n".join(lines)


def pending(session_key: str = "") -> bool:
    return bool(_rows(session_key))


def _rows(session_key: str = "") -> list:
    import time

    entry = _LAST.get(session_key or "")
    if not entry:
        return []
    stamp, rows = entry
    if time.time() - stamp > LAST_TTL:
        _LAST.pop(session_key or "", None)
        return []
    return rows


def forget(session_key: str = "") -> None:
    _LAST.pop(session_key or "", None)


def pick(number: int, *, session_key: str = "", store: Any = None) -> Optional[str]:
    """Act on one row. A bot row creates that bot; anything else opens its card.

    A skill row asks first through the market card, the same yes/no as an
    install, instead of installing on the number.
    """
    rows = _rows(session_key)
    if number < 1 or number > len(rows):
        return None
    row = rows[number - 1]
    if row["kind"] == "bot":
        from . import commands

        forget(session_key)
        return commands.handle_concierge(
            row.get("sentence", "a " + row["name"]), session_key=session_key, store=store
        )
    if row.get("installed"):
        forget(session_key)
        return "{} is already here. Nothing was installed.\n".format(row["name"])
    if row["kind"] == "plugin":
        from . import card

        forget(session_key)
        return card.handle(row["name"], session_key=session_key)
    from . import market as market_mod

    forget(session_key)
    return market_mod.handle(row["name"], session_key=session_key, store=store)
