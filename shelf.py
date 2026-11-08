"""shelf.py: what is installable, read at the moment you look.

Three sources, one list: the skills already shipped on this machine, the plugin
catalog, and the bots this home has. Nothing is stored between sessions, so a
thing you install leaves the shelf and a thing you remove comes back.

The shelf never installs on its own. It is a window: you look, you pick a
number, and the install path you already know runs.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

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
        if wanted and not (wanted & haystack):
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
        not (wanted & discover._words(row["name"].replace("-", " "))),
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
    """Bots to make, then skills already here, then plugins to fetch."""
    return _bot_rows(query, 3) + _skills(query, limit) + _plugins(query, max(2, limit // 2))


def overview() -> str:
    """One screen: what is here, and how to look further."""
    here = _installed()
    bots = []
    from . import improve

    root = improve.resolve("default")
    if root is not None and (root / "profiles").is_dir():
        bots = sorted(p.name for p in (root / "profiles").iterdir() if p.is_dir() and not p.name.startswith("."))
    try:
        total_plugins = len(seams.catalog())
    except Exception:
        total_plugins = 0
    available = len(discover.catalogue())
    lines = [
        "CONCIERGE",
        "",
        "  here     {} skills, {} bots{}".format(
            len(here),
            len(bots),
            ("  " + ", ".join(bots[:4]) + (" +{}".format(len(bots) - 4) if len(bots) > 4 else "")) if bots else "",
        ),
        "  ready    {} skills ship with Hermes, {} plugins in the catalog".format(
            available, total_plugins
        ),
        "",
        "  say what you need, or look first:",
        "  /concierge browse papers     look through it",
        "  /concierge help              every command",
        "",
    ]
    return "\n".join(lines)


def browse(query: str = "", session_key: str = "") -> str:
    """A numbered window. The number is the pick."""
    import time

    rows = items(query)
    if len(_LAST) >= MAX_SESSIONS:
        _LAST.clear()
    _LAST[session_key or ""] = (time.time(), rows)
    head = "  LOOKING FOR  {}".format(query) if query else "  READY TO ADD"
    if not rows:
        return (
            head + "\n\n"
            "  Nothing on this machine matches that.\n"
            "  Try a broader word: /concierge browse notes\n"
        )
    lines = [head, ""]
    for index, row in enumerate(rows, start=1):
        tag = "here" if row.get("installed") else row["weight"]
        lines.append(
            "  {:<2} {:<7} {:<24} {:<7} {}".format(
                index, row["kind"], row["name"], tag, row["why"]
            ).rstrip()
        )
    lines += ["", "  pick a number, or no to drop it", ""]
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
    """Act on one row. A skill installs here; a plugin opens its card."""
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
        return "  {} is already here.\n".format(row["name"])
    if row["kind"] == "plugin":
        from . import card

        forget(session_key)
        return card.handle(row["name"], session_key=session_key)
    from . import improve

    here = _here()
    home = improve.resolve(here)
    if home is None:
        return None
    plan = improve.Plan(bot=here, home=home, sentence=row["name"])
    plan.items.append(
        improve.Item(
            kind="skill",
            name=row["name"],
            kb=0.0,
            path=row.get("path"),
            identifier="official/{}/{}".format(row.get("category", ""), row["name"]),
            source=row.get("source", "optional"),
        )
    )
    forget(session_key)
    return improve.receipt(plan, improve.apply(plan, store=store))
