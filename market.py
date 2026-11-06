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
    from hermes_cli.skills_hub import _sources
    from tools.skills_hub_search import unified_search

    return unified_search(query, _sources(), source_filter="all", limit=limit)


def render(text: str, offers: list, target: str) -> str:
    """The skill card. Same shape as the plugin card, one yes, one install."""
    from . import seams

    top = offers[0]
    profile = target or seams.current_profile()
    lines = [
        "Concierge",
        "",
        f"  you said    {text.strip()}",
        f"  best match  {top.name}  ({top.where})",
    ]
    if top.description:
        lines.append(f"  what        {_fit(top.description, 160)}")
    lines.append(f"  adds        a skill: SKILL.md and its files")
    if target:
        lines.append(f"  into        bot {target}  (not this profile)")
    else:
        lines.append(f"  into        this profile ({profile})")
    lines.append(f"  install     hermes -p {profile} skills install {top.identifier}")
    if len(offers) > 1:
        lines += ["", f"  also        {offers[1].name}  ({offers[1].where})"]
    lines += ["", "Install it?  /concierge yes   or   /concierge no", ""]
    return "\n".join(lines)


def nothing(text: str, target: str = "") -> str:
    where = f"bot {target}" if target else "this profile"
    return "\n".join([
        "Concierge",
        "",
        f"  you said    {text.strip()}",
        f"  best match  none in the plugin catalog or the skill registries",
        "",
        f"Nothing answers to that, so nothing was installed in {where}.",
        "",
    ])


def handle(text: str, *, target: str = "", session_key: str = "",
           search_fn: Optional[Callable[[str, int], list]] = None,
           install: Optional[Callable] = None, store=None) -> str:
    """One request in, one skill card or one receipt out."""
    text = (text or "").strip()
    if not text:
        return "Concierge\n\n  Say what you want, like: /concierge install stripe payments\n"

    lowered = text.lower()
    if lowered in NO:
        _PENDING.pop(session_key, None)
        return "Nothing installed.\n"
    if lowered in YES:
        return _answer(session_key=session_key, install=install, store=store)

    query, named = split_target(text)
    if named and not target:
        target = named

    offers = search(query, search=search_fn)
    if not offers:
        _PENDING.pop(session_key, None)
        return nothing(query, target)

    _PENDING[session_key] = {"query": query, "offers": offers, "target": target}
    return render(query, offers, target)


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
    return bool(_PENDING.get(session_key))


def forget(session_key: str = "") -> None:
    _PENDING.pop(session_key, None)
