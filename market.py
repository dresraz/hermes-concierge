"""market.py: the other shelf, and where the install lands.

The plugin catalog is one shelf in the marketplace. Skills are the other. This
module answers what the plugin card cannot: is the thing a skill, and which
profile does it go into. Both answers come back on one card with one yes, so a
skill install is as visible and as undoable as a plugin install.

Nothing here re-implements core's gate. Skills go through
`hermes -p <profile> skills install`, which runs the same scan, trust check and
admission core runs for the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .card import NO, YES, _fit

# A skills search is a network call, so it is spent once per sentence and never
# on a yes. The pending offer holds the identifier the search already returned.
_PENDING: dict = {}
_STAMP: dict = {}
MARKET_TTL = 600
MARKET_MAX = 32


@dataclass
class Offer:
    """One skill from a registry, described the way the card describes plugins."""

    name: str
    identifier: str
    description: str = ""
    source: str = ""
    trust: str = ""

    @property
    def where(self) -> str:
        return ", ".join(part for part in (self.source, self.trust) if part) or "registry"


def split_target(text: str) -> tuple[str, str]:
    """Split "… into <bot>" into (request, bot). No bot named means no target.

    Only a single word after "into" counts, and only when a profile answers to
    it, so "install a plugin into my workflow" stays one sentence and a typo
    ends up on a card that says where it is going, never in a silent install.
    """
    from . import seams

    raw = (text or "").strip()
    low = raw.lower()
    head, sep, tail = low.rpartition(" into ")
    if not sep:
        # "add pdf to inbox-bot" says the destination just as plainly. Only a
        # single word that is really a profile counts, so "pdf for research"
        # stays one sentence.
        head, sep, tail = low.rpartition(" to ")
        if not sep or len(tail.split()) != 1:
            return raw, ""
    bot = raw[len(head) + len(sep):].strip()
    if not bot or len(bot.split()) != 1:
        return raw, ""
    try:
        known = seams.profile_exists(bot)
    except Exception:
        known = False
    if not known:
        return raw, ""
    return raw[: len(head)].strip(), bot


def search(query: str, *, limit: int = 2,
           search: Optional[Callable[[str, int], list]] = None) -> list:
    """Skill registry hits for *query*, best trust first. Empty on any failure."""
    try:
        results = (search or _hub_search)(query, limit)
    except Exception:  # offline, no credentials, registry down: an empty shelf
        return []
    offers = []
    for hit in results or []:
        name = str(getattr(hit, "name", "") or "")
        identifier = str(getattr(hit, "identifier", "") or name)
        if not name or not identifier:
            continue
        offers.append(Offer(
            name=name,
            identifier=identifier,
            description=" ".join(str(getattr(hit, "description", "") or "").split()),
            source=str(getattr(hit, "source", "") or ""),
            trust=str(getattr(hit, "trust_level", "") or ""),
        ))
    return offers[:limit]


def _hub_search(query: str, limit: int) -> list:
    """Registry hits through the public CLI, parsed into the shape the card wants."""
    import json
    import subprocess
    from types import SimpleNamespace

    from . import seams

    try:
        done = subprocess.run(
            [seams._hermes(), "skills", "search", query, "--json", "--limit", str(limit)],
            capture_output=True, text=True, timeout=60,
        )
        rows = json.loads(done.stdout or "[]")
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    return [
        SimpleNamespace(
            name=str(row.get("name") or row.get("identifier") or ""),
            identifier=str(row.get("identifier") or row.get("name") or ""),
            description=str(row.get("description") or ""),
            source=str(row.get("source") or ""),
            trust_level=str(row.get("trust_level") or ""),
        )
        for row in rows
        if isinstance(row, dict)
    ]


def _shipped_line(name: str) -> str:
    """What the skill does, from the skill itself, not the registry's blurb."""
    try:
        from . import discover

        for item in discover.catalogue():
            if item["name"] == name:
                return str(item.get("why") or item.get("description") or "")
    except Exception:
        pass
    return ""


def _caution_for(name: str, description: str = "") -> str:
    """What a card should say before you say yes, worked out from the entry.

    It lives here, at the card, because the card is the last place every path
    passes through: the model pick, the offline fallback and a direct install by
    name all end up rendering it. A warning that only some paths reach is a
    warning that will be missing one day.
    """
    from . import presets

    if presets.heavy(name):
        return "heavy"
    low = "{} {}".format(name, description or "").lower()
    for marker in ("memory provider", "long-term memory", "long term memory",
                   "memory plugin", "memory layer", "memory backend"):
        if marker in low:
            return "memory"
    return ""


def _caution_line(caution: str) -> str:
    if caution == "memory":
        return "  Memory provider: usually needs a paid plan."
    if caution == "heavy":
        return "  Heavy: downloads models and wants a GPU."
    return ""


def render(text: str, offers: list, target: str, caution: str = "") -> str:
    """The skill card: a name, one line, two words."""
    top = offers[0]
    caution = caution or _caution_for(top.name, top.description)
    lines = ["", "Install {}?".format(top.name)]
    body = []
    # A registry blurb ("Indexed by skills.sh · 225,675 installs") tells a
    # stranger nothing about what the thing does. The skill's own one-liner
    # is already on this machine.
    described = top.description
    if not described or described.lower().startswith("indexed by"):
        described = _shipped_line(top.name) or ""
    if described:
        line = " ".join(described.split())
        cut = line.find(". ")
        if 0 < cut < 96:
            line = line[: cut + 1]
        elif len(line) > 96:
            line = _fit(line, 96)
        elif not line.endswith("."):
            line += "."
        body.append("  " + line)
    if target:
        body.append("  It goes into {}.".format(target))
    if body:
        lines += [""] + body
    line = _caution_line(caution)
    if line:
        lines.append(line)

    rival = next((offer for offer in offers[1:] if offer.name != top.name), None)
    if rival is not None:
        lines += ["", "  Another option: {}.".format(rival.name)]
    lines += ["", "  yes     no", ""]
    return "\n".join(lines)


def _hint(text: str) -> str:
    """A word to browse for, taken from the ask itself."""
    from . import match

    words = [w for w in match.tokens(text) if len(w) > 2]
    return words[0] if words else "plugins"


def nothing(text: str, target: str = "") -> str:
    """The honest no, in the same shape as the plugin card's."""
    said = " ".join((text or "").split())[:80]
    where = " into {}".format(target) if target else ""
    head = 'Nothing here fits "{}". Nothing was installed{}.'.format(said, where) if said else "Nothing here fits that. Nothing was installed."
    hint = _hint(text)
    try:
        from . import shelf

        nxt = "  Next: /concierge browse {}".format(hint) if shelf.items(hint, limit=2) else "  Next: /concierge create a bot that does it"
    except Exception:
        nxt = "  Next: /concierge create a bot that does it"
    return "\n".join([head, "", nxt, ""])


def handle(text: str, *, target: str = "", session_key: str = "",
           search_fn: Optional[Callable[[str, int], list]] = None,
           install: Optional[Callable] = None, store=None, caution: str = "") -> str:
    """One request in, one skill card or one receipt out."""
    text = (text or "").strip()
    if not text:
        return "Concierge\n\n  Say what you want, like: /concierge install stripe payments\n"

    lowered = text.lower()
    if lowered in NO:
        _PENDING.pop(session_key, None)
        _STAMP.pop(session_key, None)
        return "Nothing installed.\n"
    if lowered in YES:
        return _answer(session_key=session_key, install=install, store=store)
    if lowered == "2":
        # The card describes one offer and may name a runner-up; a number is not
        # a choice between two cards. Refuse it without dropping the offer.
        return "One install at a time. Say yes for the top match, or name the other one.\n"

    query, named = split_target(text)
    if named and not target:
        target = named

    offers = search(query, search=search_fn)
    if not offers:
        _PENDING.pop(session_key, None)
        _STAMP.pop(session_key, None)
        return nothing(query, target)

    import time

    now = time.time()
    for key in [k for k, when in _STAMP.items() if now - when > MARKET_TTL]:
        _PENDING.pop(key, None)
        _STAMP.pop(key, None)
    while len(_STAMP) > MARKET_MAX:
        oldest = min(_STAMP, key=_STAMP.get)
        _PENDING.pop(oldest, None)
        _STAMP.pop(oldest, None)
    _STAMP[session_key] = now
    _PENDING[session_key] = {"query": query, "offers": offers, "target": target}
    return render(query, offers, target, caution=caution)


def _answer(*, session_key: str = "", install=None, store=None) -> str:
    from . import seams, state

    held = _PENDING.get(session_key) or {}
    offers = held.get("offers") or []
    if not offers:
        return "Nothing is waiting. Start with: /concierge install <what you want>\n"

    offer = offers[0]
    target = held.get("target") or ""
    profile = target or seams.current_profile()

    if install is not None:
        ok, folder, message = install(offer, profile)
    else:
        ok, folder, message = seams.install_skill_in(profile, offer.identifier, name=offer.name)

    _PENDING.pop(session_key, None)
    if not ok:
        return f"Not installed: {message or 'core refused the install'}\n"

    record = state.Installed(
        name=offer.name, kind="skill", title=offer.description,
        target=folder, profile=profile, skills=[folder],
    )
    saved = _remember(record, store)
    return receipt(record, offer, saved=saved)


def receipt(record, offer: Offer, *, saved: bool = True) -> str:
    """What landed, read off the disk rather than assumed."""
    folder = Path(record.target) if record.target else None
    lines = [f"Installed skill {record.name}", ""]
    if folder is not None and folder.is_dir():
        files = sum(1 for item in folder.rglob("*") if item.is_file())
        lines.append(f"  on disk     {folder} ({files} files)")
    else:
        lines.append("  on disk     not found, core reported a path that is not there")
    lines.append(f"  into        {record.profile}")
    if offer.where:
        lines.append(f"  source      {offer.where}")
    if saved:
        lines += ["", "Undo it with /concierge undo", ""]
    else:
        lines += ["", "Undo is off for this one: the record could not be saved.", ""]
    return "\n".join(lines)


def _remember(record, store) -> bool:
    if store is None:
        from . import state

        store = state.Store()
    try:
        store.add(record)
    except Exception:
        return False
    return True


def is_waiting(session_key: str = "") -> bool:
    slot = _PENDING.get(session_key) or {}
    return bool(slot.get("offers"))


def forget(session_key: str = "") -> None:
    _PENDING.pop(session_key, None)
