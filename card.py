"""The card: one sentence in, one decision out.

Everything a person needs in order to say yes is on the card, and nothing is
installed until they say it. The card is a plain string so it renders the same
in the CLI, the TUI and a test.

Two keystrokes are deliberate, not friction: when core rates a plugin caution
it prints its own report, and the card makes the second yes explicit instead
of taking one answer as consent to two different questions.
"""

from __future__ import annotations

from typing import Optional

# A second candidate stays on the card when it is close enough that showing
# only the winner would be a guess.
CONTENDER_RATIO = 0.75

# What a confirmed sentence leaves behind until the person answers, one slot per
# conversation: one gateway process serves many chats at once, so a "yes" must only
# ever answer the card that same chat was shown. The entries themselves are kept, not
# their names, so answering never re-reads the catalog.
_PENDING: dict = {}


CARD_TTL = 600
CARD_MAX = 32
_STAMP: dict = {}


def _prune() -> None:
    """A card nobody answered expires, and the map never grows without bound."""
    import time

    now = time.time()
    for key in [k for k, when in _STAMP.items() if now - when > CARD_TTL]:
        _PENDING.pop(key, None)
        _STAMP.pop(key, None)
    while len(_STAMP) > CARD_MAX:
        oldest = min(_STAMP, key=_STAMP.get)
        _PENDING.pop(oldest, None)
        _STAMP.pop(oldest, None)


def _slot(session_key: str = "") -> dict:
    import time

    _prune()
    key = session_key or ""
    _STAMP[key] = time.time()
    return _PENDING.setdefault(
        key, {"sentence": "", "entries": [], "caution_accepted": False}
    )

YES = frozenset({"y", "yes", "install", "do it", "ok", "okay", "go"})
NO = frozenset({"n", "no", "cancel", "stop", "never mind", "nvm"})
MORE = frozenset({"more", "details", "show me"})


def _caps(entry) -> dict:
    from . import match

    return match.capabilities(entry)


def _count(n: int, label: str) -> str:
    """One tool, two tools: a card that reads like English."""
    return f"{n} {label}" if n != 1 else f"1 {label.rstrip('s')}"


def _adds(entry) -> str:
    """What the plugin registers, in the catalog's own words."""
    caps = _caps(entry)
    parts = []
    for key, label in (
        ("provides_tools", "tools"),
        ("provides_hooks", "hooks"),
        ("provides_middleware", "middleware"),
    ):
        value = caps.get(key) or []
        if value:
            count = len(value) if isinstance(value, (list, tuple)) else 1
            parts.append(_count(count, label))
    requires = caps.get("requires_env") or []
    if requires:
        parts.append(f"needs {', '.join(str(r) for r in requires)}")
    return ", ".join(parts) if parts else "no tools, no hooks, no middleware"


def cost_line(entry) -> str:
    """One honest line about what the plugin adds to every request."""
    caps = _caps(entry)
    tools = caps.get("provides_tools") or []
    if not tools:
        return "adds no tools, so nothing is added to the request"
    count = len(tools) if isinstance(tools, (list, tuple)) else 1
    # The catalog declares tool names, not schemas, so the only thing that can
    # be said without inventing a number is that they ride along on each call.
    return f"{_count(count, 'tools')}, sent on every request like every other tool"


def _pin(entry) -> str:
    sha = str(getattr(entry, "sha", "") or "")
    version = str(getattr(entry, "version", "") or "")
    repo = str(getattr(entry, "repo", "") or "")
    short = sha[:12] if sha else "unpinned"
    tail = f"v{version} " if version else ""
    return f"{repo} {tail}@ {short}".strip()


def _fit(text: str, limit: int) -> str:
    """Cut at a word boundary so the card never ends mid-word.

    A description chopped inside a word reads like a bug on camera, so trim to
    the last whole word that fits and mark the cut.
    """
    if len(text) <= limit:
        return text
    cut = text[: limit - 4]
    space = cut.rfind(" ")
    if space > 0:
        cut = cut[:space]
    return cut.rstrip(" ,;:.") + " ..."


def _dep_name(spec: str) -> str:
    """The package name out of a requirement spec, so the card stays readable."""
    import re

    head = str(spec).strip().split(";")[0]
    match = re.match(r"[A-Za-z0-9_.\-]+", head)
    return match.group(0) if match else head


def deps_line(deps) -> str:
    """What the plugin brings with it, in the person's words, before the yes."""
    from . import seams

    names = [_dep_name(str(d)) for d in deps]
    shown = ", ".join(names[:4]) + (f" (+{len(names) - 4} more)" if len(names) > 4 else "")
    if seams.risky_deps(deps):
        return f"  deps        {shown}  installs code from git or a url, not PyPI"
    return f"  deps        {shown}  installed with it, no extra question"


JURISDICTIONS = (
    (r"\bmexic\w*\b|\bcfdi\b|\bsat\b", "Mexico (CFDI / SAT)"),
    (r"\birs\b|\bw-?2\b|\b1099\b", "the United States (IRS)"),
    (r"\bhmrc\b|\bself assessment\b", "the United Kingdom (HMRC)"),
    (r"\bnf-?e\b", "Brazil (NF-e)"),
    (r"\bgst\b", "Australia / India (GST)"),
)


def jurisdiction(entry) -> str:
    """The country a plug-in is locked to, when it says so about itself.

    Mexican invoicing is useless in Peru, and a new person should not have to
    work that out from the description: the card says it, and the answer is no.
    """
    import re

    blob = " ".join(
        str(getattr(entry, key, "") or "") for key in ("name", "title", "description")
    ).lower()
    for pattern, label in JURISDICTIONS:
        if re.search(pattern, blob):
            return label
    return ""


def _one_line(description: str, limit: int = 92) -> str:
    """One sentence a stranger reads without scrolling."""
    text = " ".join((description or "").split())
    if not text:
        return ""
    cut = text.find(". ")
    if 0 < cut < limit:
        return text[: cut + 1]
    if len(text) > limit:
        return _fit(text, limit)
    return text if text.endswith(".") else text + "."


def _plain_adds(entry) -> str:
    """What the plugin does to the agent, in words a new person parses once."""
    tools = _caps(entry).get("tools") or []
    if not tools:
        return ""
    count = len(tools) if isinstance(tools, (list, tuple)) else 1
    return "Adds {}.".format(_count(count, "tool")).format(_count(count, "extra tool"))


def render(sentence: str, candidates: list, deps: Optional[list] = None,
           target: str = "", caution: str = "") -> str:
    """The card for one sentence and the candidates that earned a place on it.

    Written for someone who has never installed a plugin: the first line is the
    offer, then four short facts, then two words you can type. No tiers, no
    category labels, no commit shas on the main line.
    """
    from . import seams

    top = candidates[0]
    where = (
        "It goes into {}.".format(target)
        if target
        else ""
    )
    lines = ["", "Install {}?".format(top.name), ""]
    sentence = _one_line(top.description)
    if sentence:
        lines.append("  " + sentence)
    adds = _plain_adds(top.entry)
    if deps:
        names = ", ".join(_dep_name(str(d)) for d in deps[:3])
        if len(deps) > 3:
            names += " +{}".format(len(deps) - 3)
        risky = ""
        try:
            from . import seams as _seams

            risky = " (from git)" if _seams.risky_deps(deps) else ""
        except Exception:
            risky = ""
        adds = " ".join(part for part in (adds, "Also installs {}{}.".format(names, risky)) if part)
    tail = " ".join(part for part in (adds, where) if part)
    if tail:
        lines.append("  " + tail)
    locked = jurisdiction(top.entry)
    if locked and locked.split(" (")[0].lower() not in sentence.lower():
        # Only when the ask did not name that country itself.
        lines.append("  Only for {}. Not your country? Say no.".format(locked))

    if caution == "memory":
        lines.append("  Memory provider: usually needs a paid plan.")
    elif caution == "heavy":
        lines.append("  Heavy: downloads models and wants a GPU.")

    rival = _contender(candidates)
    if rival is not None:
        lines += ["", "  Another option: {}.".format(rival.name)]
    lines += ["", "  yes     no", ""]
    return "\n".join(lines)


def _contender(candidates: list):
    if len(candidates) < 2:
        return None
    first, second = candidates[0], candidates[1]
    if first.score <= 0 or second.score < first.score * CONTENDER_RATIO:
        return None
    return second


def _hint(sentence: str) -> str:
    """A word to browse for, taken from the ask itself rather than a canned one."""
    from . import match

    words = [w for w in match.tokens(sentence) if len(w) > 2]
    return words[0] if words else "plugins"


def _has_hits(word: str) -> bool:
    """Whether browsing for that word would show anything at all."""
    try:
        from . import shelf

        return bool(shelf.items(word, limit=2))
    except Exception:
        return True


def nothing(sentence: str, entries: Optional[list] = None) -> str:
    """The honest no: nothing in the catalog does this, and nothing was installed."""
    said = " ".join((sentence or "").split())[:80]
    return "\n".join(
        [
            "Concierge",
            "",
            "  Nothing here fits {} yet.".format('"' + said + '"' if said else "that"),
            "  Nothing was installed.",
            "",
            "  Try the word for the tool you want: /concierge browse {}".format(_hint(sentence))
            if _has_hits(_hint(sentence))
            else "  No tool does this, but a bot can try: /concierge create {}".format(
                " ".join((sentence or "").split())[:60]
            ),
            "",
        ]
    )


def handle(sentence: str, *, entries=None, store=None, install=None,
           session_key: str = "", target: str = "", caution: str = "") -> str:
    """One sentence in, one card or one receipt out."""
    from . import match, seams

    slot = _slot(session_key)
    text = (sentence or "").strip()
    if not text:
        return "Concierge\n\n  Say what you want in one sentence, like: /concierge remember my notes across sessions\n"

    if not target:
        # A plain sentence can name a bot too, not only the install verb.
        from . import market

        text, target = market.split_target(text)
        if not text:
            return "Install what? Name the thing you want and the bot after it.\n"

    lowered = text.lower()

    if lowered in NO:
        forgotten = slot.get("sentence", "") or ""
        _reset(session_key)
        return f"Nothing installed.{' Kept ' + forgotten + ' out.' if forgotten else ''}\n"

    if lowered == "2":
        # Refused rather than guessed: the card only ever describes one install.
        return "One install at a time. /concierge yes takes the top match, or name the other one.\n"

    if lowered in YES or lowered == "1":
        return _answer(store=store, install=install, session_key=session_key)

    if lowered in MORE:
        return more(session_key=session_key)

    if entries is None:
        try:
            entries = seams.catalog()
        except Exception:
            entries = []
    catalog = entries
    candidates = match.rank(text, catalog, limit=2)
    if not candidates:
        return nothing(text, catalog)

    slot["sentence"] = text
    slot["entries"] = candidates
    slot["target"] = target
    slot["caution_accepted"] = False
    try:  # the packages the repo declares, read before the yes; no list means none are shown
        deps = seams.declared_deps_remote(candidates[0].entry)
    except Exception:
        deps = []
    return render(text, candidates, deps=deps, target=target, caution=caution)


def _answer(*, store=None, install=None, session_key: str = "") -> str:
    slot = _slot(session_key)
    picked = slot.get("entries") or []
    if not picked:
        return "Nothing is waiting. Start with: /concierge <what you want>\n"
    return _install(picked[0].entry, store=store, install=install,
                    session_key=session_key, target=slot.get("target") or "")


def more(session_key: str = "") -> str:
    """The runner-up, described. Shows it; changes nothing about the pending yes."""
    picked = _slot(session_key)["entries"]
    if not picked:
        return "Nothing is waiting. Start with: /concierge <what you want>\n"
    if len(picked) < 2:
        return f"{picked[0].name} is the only match on the card.\n"

    rival = picked[1]
    lines = ["", "{}".format(rival.name), ""]
    if rival.description:
        lines.append("  " + _one_line(rival.description))
    lines += [
        "",
        "The card still holds {}. /concierge yes installs that.".format(picked[0].name),
        "For this one instead: /concierge {}".format(rival.name),
        "",
    ]
    return "\n".join(lines)


def _install(entry, *, store=None, install=None, session_key: str = "",
             target: str = "") -> str:
    from . import seams, state

    slot = _slot(session_key)
    install_fn = install or seams.install

    # Core's report is a string, not a print: in the TUI and in the gateway
    # stdout never reaches the conversation, so the report travels back with
    # the reply the same way the card does.
    shown: list[str] = []

    def approve(report: str) -> bool:
        # Core's own report is already on screen; the second yes is the answer
        # to core's question, not a repeat of the first one.
        if slot.get("caution_accepted"):
            return True
        shown.append(report)
        return False

    try:
        if target:
            # A named bot is a profile, and core binds HERMES_HOME at import, so
            # this runs core's own command line as a child with -p. The child
            # runs the same scan and admission; we only report what it wrote.
            outcome = seams.install_in(entry, target)
        else:
            outcome = install_fn(entry, approve=approve)
    except Exception as exc:
        # An installer that cannot run is a failure to report, never a traceback
        # in the middle of someone's conversation.
        _reset(session_key)
        return "Not installed: {}: {}\n".format(type(exc).__name__, exc)

    if not outcome.ok:
        if not target and outcome.verdict == "caution" and not slot.get("caution_accepted"):
            slot["caution_accepted"] = True
            body = "\n".join(part for part in shown if part.strip())
            return (
                (body + "\n\n" if body else "")
                + f"Core rated {entry.name} caution.\n"
                "Accept it with /concierge yes, or /concierge no.\n"
            )
        _reset(session_key)
        reason = outcome.blocked_reason or "core refused the install"
        return f"Not installed: {reason}\n"

    _reset(session_key)
    record = state.Installed(
        name=outcome.installed_name or str(getattr(entry, "name", "")),
        sha=str(getattr(entry, "sha", "") or ""),
        title=str(getattr(entry, "title", "") or ""),
        target=outcome.target,
        profile=target or seams.current_profile(),
        enabled=bool(outcome.enabled),
    )
    saved = _remember(record, store)
    return receipt(outcome, record, saved=saved)


def receipt(outcome, record, *, saved: bool = True) -> str:
    """What actually happened, checked on disk rather than assumed."""
    from pathlib import Path

    from . import seams

    target = Path(record.target) if record.target else None
    present = target is not None and target.exists()
    # The headline may not claim more than the line under it proves.
    head = (
        "Installed {}".format(record.name)
        if present
        else "Not installed: {} is not on disk".format(record.name)
    )
    lines = [head, ""]
    if present:
        lines.append("  on disk     yes, the files are there")
    else:
        lines.append("  on disk     nothing there yet")
    lines.append(f"  enabled     {'yes' if record.enabled else 'no'}")
    if record.profile:
        lines.append(f"  into        {record.profile}")
    try:  # re-read the installed tree: what core actually installed, not what the repo promised
        installed = seams.declared_deps(target) if target is not None else []
    except Exception:
        installed = []
    if installed:
        names = ", ".join(_dep_name(str(d)) for d in installed[:4])
        if len(installed) > 4:
            names += f" (+{len(installed) - 4} more)"
        lines.append(f"  deps        {names} installed")
    verdict = outcome.verdict or "not scanned"
    findings = len(outcome.findings)
    if not findings:
        lines.append(f"  scan        {verdict}, nothing flagged")
    elif findings == 1:
        lines.append(f"  scan        {verdict}, 1 note")
    else:
        lines.append(f"  scan        {verdict}, {findings} notes")
    for note in outcome.notes:
        lines.append(f"  note        {note}")
    if saved and present:
        lines += ["", "Undo it with /concierge undo", ""]
    elif saved:
        lines += ["", "Nothing to undo yet: the files are not there.", ""]
    else:
        # A receipt may not promise an undo that was never recorded.
        lines += ["", "Undo is off for this one: the record could not be saved.", ""]
    return "\n".join(lines)


def _remember(record, store) -> bool:
    """Persist the record so undo has something exact to reverse.

    Returns False when it could not be written, so the receipt says so instead of
    offering an undo with nothing to reverse.
    """
    if store is None:
        from . import state

        store = state.Store()
    try:
        store.add(record)
    except Exception:  # a receipt that cannot be saved is still a receipt
        return False
    return True


def _reset(session_key: str = "") -> None:
    """Drop this conversation's card; nothing of it survives in another chat."""
    _PENDING.pop(session_key or "", None)
    _STAMP.pop(session_key or "", None)


def forget(session_key: str = "") -> None:
    """Let go of a card without answering it (undo, or a new sentence)."""
    _reset(session_key)


def is_waiting(session_key: str = "") -> bool:
    """True when this conversation has a card standing open."""
    slot = _PENDING.get(session_key or "") or {}
    return bool(slot.get("entries"))
