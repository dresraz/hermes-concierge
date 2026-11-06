"""The command surface: one command, one sentence, one result.

  /concierge <sentence>          install the best match from the live catalog
  /concierge hire <sentence>     make a new bot
  /concierge train <bot>: <what> teach a bot one standing habit
  /concierge bots                list the bots Concierge made
  /concierge fire <n>            delete bot number n
  /concierge reset <n>           take back what Concierge changed in bot n
  /concierge undo                take back the last thing Concierge did

Only one command has to be learned. Everything else is a word after it.

One path asks first: a catalog install runs third-party code, so it shows the
scan verdict and the pinned SHA and waits for a yes. Hiring and training act
straight away, because the sentence already said what to do, the result is
visible, and undo covers regret.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional, Sequence

YES = frozenset({"y", "yes", "do it", "ok", "okay", "go", "confirm"})
NO = frozenset({"n", "no", "cancel", "stop", "never mind", "nvm"})
UNDO_WORDS = frozenset({"undo", "revert", "roll back", "rollback", "reverse"})
HELP_WORDS = frozenset({"help", "?", "-h", "--help", "h", "commands"})

HELP = (
    "\n"
    "  CONCIERGE\n"
    "  Bots and skills, one sentence at a time.\n"
    "\n"
    "  /concierge <sentence>          install the best match from the catalog\n"
    "  /concierge hire <sentence>     make a new bot\n"
    "  /concierge train <bot>: <what> teach a bot one standing habit\n"
    "  /concierge bots                list the bots Concierge made\n"
    "  /concierge fire <n>            delete bot number n\n"
    "  /concierge reset <n>           take back what Concierge changed in bot n\n"
    "  /concierge undo                take back the last thing Concierge did\n"
    "  /concierge help                this list\n"
    "\n"
    "  A catalog install shows one card and waits for your yes.\n"
    "  On a card: yes installs it, no drops it, more describes the runner-up.\n"
    "  Bots and training act straight away and show a receipt.\n"
    "\n"
    "  Roles hire with their skills: researcher, writer, coder, assistant,\n"
    "  marketer, watcher, designer, analyst, tutor, planner.\n"
    "\n"
    "  Example: /concierge hire a researcher for papers\n"
    "  Example: /concierge hire keeps my inbox at zero\n"
    "  Name it: /concierge hire inbox-zero: keeps my inbox at zero\n"
)

USAGE = HELP

# Kept for the one path that still asks: the catalog card. One pending card per conversation,
# because the gateway runs many conversations in one process and a typed "yes" must only ever
# confirm a card that same conversation was shown.
_PENDING: dict = {}


def _clean(raw: Any) -> str:
    return " ".join(str(raw or "").split())


def _forget(message: str, session_key: str = "") -> str:
    _PENDING.pop(session_key or "", None)
    return message


def handle_concierge(
    raw: Any,
    *,
    store: Any = None,
    session_key: str = "",
    seams: Any = None,
    hire: Optional[Callable[..., Any]] = None,
    train: Optional[Callable[..., Any]] = None,
    known: Optional[Sequence[str]] = None,
    undo: Optional[Callable[..., Any]] = None,
) -> str:
    """The whole surface behind one command."""
    from . import card, lifecycle

    if store is None:
        from . import state

        store = state.Store()

    text = _clean(raw)
    low = text.lower()
    if not text or low in HELP_WORDS:
        card.forget(session_key)
        _forget("", session_key)
        return HELP
    if low in UNDO_WORDS:
        card.forget(session_key)
        _forget("", session_key)
        return handle_undo(store=store, undo=undo, seams=seams)

    head, _, _ = low.partition(" ")
    rest = text[len(head):].strip()

    if head == "bots":
        card.forget(session_key)
        _forget("", session_key)
        return lifecycle.card(store)

    if head in ("fire", "reset"):
        # "fire the intern" is a sentence, not a bot: only a selector fires.
        parts = rest.split()
        selector = parts[0] if parts else ""
        confirm = " ".join(parts[1:])
        if not lifecycle.is_selector(store, selector):
            return card.handle(text, session_key=session_key)
        card.forget(session_key)
        _forget("", session_key)
        try:
            if head == "fire":
                return lifecycle.fire(store, selector, confirm=confirm, seams=seams)
            return lifecycle.reset(store, selector, seams=seams)
        except lifecycle.Refused as exc:
            return "  {}\n".format(exc)

    if head == "hire":
        card.forget(session_key)
        _forget("", session_key)
        return handle_hire(rest, store=store, hire=hire, known=known)

    if head == "train":
        card.forget(session_key)
        _forget("", session_key)
        return handle_train(rest, store=store, train=train, known=known)

    # Bare yes/no/more belong to a catalog card this conversation was shown.
    return card.handle(text, session_key=session_key)


def handle_hire(
    raw: Any,
    *,
    store: Any = None,
    hire: Optional[Callable[..., Any]] = None,
    known: Optional[Sequence[str]] = None,
) -> str:
    """One sentence in, one new bot out. No confirmation: the sentence was the request."""
    from . import bots, lifecycle, state

    text = _clean(raw)
    if not text:
        return "Usage: /concierge hire <sentence>   e.g. /concierge hire keeps my inbox at zero\n"

    plan = bots.spec(text)
    if plan.name == lifecycle.DEFAULT:
        return (
            "  {} is the profile you are talking to, not a bot. Name this one:\n"
            "  /concierge hire {}-2: {}\n".format(plan.name, plan.name, text)
        )

    taken = list(known) if known is not None else bots.names()
    if plan.name in taken:
        return (
            "  {} already exists.\n\n"
            "  Name it yourself and try again, for example:\n"
            "  /concierge hire {}-2: {}\n".format(plan.name, plan.name, text)
        )

    try:
        plan, path = (hire or bots.hire)(text)
    except bots.Collision as exc:
        return "  {} already exists. Nothing was created.\n".format(exc.name)
    except Exception as exc:
        return "Not hired: {}: {}\n".format(type(exc).__name__, exc)

    # The role's soul and skills must land before the receipt is computed, or the
    # card reports the generic soul the hire flow wrote a moment earlier. A preset
    # failure never costs the bot: it exists, and the receipt says what is missing.
    try:
        plugin_lines = _inherit_plugins(path)
    except Exception as exc:
        plugin_lines = ["  plugins  stock defaults, copy failed: {}".format(type(exc).__name__)]
    try:
        preset_lines = _apply_preset(text, plan.name, path)
    except Exception:
        preset_lines = []

    lines, ok = bots.receipt(
        plan, path, known=(taken + [plan.name] if known is not None else None)
    )
    saved = _remember(
        state.Installed(
            name=plan.name,
            kind="bot",
            title=plan.title,
            profile=plan.name,
            soul_path=str(Path(str(path)) / "SOUL.md"),
            enabled=True,
        ),
        store,
    )
    head = "Hired {}".format(plan.name) if ok else "Hired {}, but check this".format(plan.name)
    undo_line = "  undo     /concierge undo" if saved else "  no undo  the record could not be saved"
    return "\n".join(
        [head, ""]
        + ["  " + line for line in lines]
        + plugin_lines
        + preset_lines
        + [
            "",
            "  next     /concierge train {}: <habit>".format(plan.name),
            undo_line,
            "",
        ]
    )


def _inherit_plugins(profile_path: Any) -> list[str]:
    """Your plugin switches ride along. Never fatal: the bot exists either way."""
    from . import plugins_inherit

    return plugins_inherit.inherit(profile_path).lines()


def _apply_preset(text: str, name: str, profile_path: Any) -> list[str]:
    """A role sentence also installs that role's skills. Never fatal: the bot exists."""
    from . import presets

    role = presets.detect(text)
    if role is None:
        return []
    try:
        report = presets.install(name, Path(str(profile_path)), role)
    except Exception as exc:
        return ["  skills   preset skipped: {}: {}".format(type(exc).__name__, exc)]
    return report.lines() if report.wanted else []


def handle_train(
    raw: Any,
    *,
    store: Any = None,
    train: Optional[Callable[..., Any]] = None,
    known: Optional[Sequence[str]] = None,
) -> str:
    """One sentence in, one skill written into an existing bot. No confirmation."""
    from . import state, training

    text = _clean(raw)
    if not text:
        return training.DEFAULT_HINT + "\n"

    bot, instruction = training.guess_bot(text)
    if not instruction:
        return training.DEFAULT_HINT + "\n"

    taken = list(known) if known is not None else training.bots()
    if bot not in taken:
        options = ", ".join(taken[:8]) or "none yet"
        return "  No bot called {}.\n  Bots you have: {}\n  Make one with /concierge hire <sentence>.\n".format(
            bot, options
        )

    try:
        result = (train or training.train)(bot, instruction)
    except training.UnknownBot as exc:
        return "  No bot called {}. Nothing was written.\n".format(exc.name)
    except Exception as exc:
        return "Not trained: {}: {}\n".format(type(exc).__name__, exc)

    lines, ok = training.receipt(result)
    saved = _remember(
        state.Installed(
            name=result.slug,
            kind="skill",
            title=instruction[:120],
            profile=result.bot,
            skills=[str(result.path.parent)],
            enabled=True,
        ),
        store,
    )
    head = "Trained {}".format(result.bot) if ok else "Trained {}, but check this".format(result.bot)
    undo_line = "  undo     /concierge undo" if saved else "  no undo  the record could not be saved"
    return "\n".join(
        [head, ""]
        + ["  " + line for line in lines]
        + ["", undo_line, ""]
    )


def handle_undo(*, store: Any = None, undo: Optional[Callable[..., Any]] = None, seams: Any = None) -> str:
    """Reverse the last record, then check on disk that it is really gone."""
    store = store if store is not None else _store()
    record = store.latest()
    if record is None:
        return "Nothing to undo. Concierge has not changed anything yet.\n"

    lines = _undo_record(record, undo=undo, seams=seams)
    if any(line.startswith("kept:") for line in lines):
        # A refusal is not an undo: the receipt stays so the bot is still tracked.
        return "\n".join(
            ["Not undone: {}".format(record.name), ""] + ["  " + line for line in lines] + [""]
        )
    problems = [line for line in lines if line.startswith(("could not", "still there"))]
    if problems:
        head = "Not fully undone"
        tail = "  the receipt is kept, so /concierge undo tries again\n"
    else:
        store.drop(record.name)
        head = "Undone"
        tail = ""
    return "\n".join(
        ["{}: {}".format(head, record.name), ""]
        + ["  " + line for line in lines]
        + ([tail] if tail else [])
    )


def _undo_record(
    record: Any,
    *,
    seams: Any = None,
    undo: Optional[Callable[..., Any]] = None,
    guard: bool = True,
) -> list:
    """Reverse one record. The seam is chosen by what kind of record it is."""
    from . import effects

    kind = getattr(record, "kind", "") or "plugin"
    if kind == "bot":
        return _undo_bot(record, seams if seams is not None else _seams(), guard=guard)
    if kind == "skill":
        return _undo_skill(record, effects)
    from . import undo as undo_mod

    return list((undo or undo_mod.undo)(record))


def _undo_bot(record: Any, seams: Any, *, guard: bool = True) -> list:
    name = getattr(record, "name", "") or ""
    try:
        home = seams.profile_home(name)
    except Exception:
        home = None
    present = bool(home is not None and getattr(home, "exists", lambda: False)())
    if not present:
        # Already absent is the outcome undo wanted, not a failure. Reporting it
        # as one kept the record forever and made every later undo repeat it.
        return ["already gone: profile {}".format(name)]
    if guard:
        # Undo takes back a change. It never deletes a bot someone has lived in,
        # because there is nothing to restore it from. Fire is that sentence.
        from . import lifecycle

        history = lifecycle.history_of(name, seams)
        if history:
            return [
                "kept: {} has history ({}) and undo never deletes a used bot".format(
                    name, ", ".join(history)
                ),
                "to delete it on purpose: /concierge fire <its number> {}".format(name),
            ]
    try:
        seams.remove_profile(name)
    except Exception as exc:
        return ["could not remove profile {}: {}: {}".format(name, type(exc).__name__, exc)]
    if getattr(home, "exists", lambda: False)():
        return ["removed: profile {}".format(name), "still there: {}".format(home)]
    return ["removed: profile {}".format(name)]


def _undo_skill(record: Any, effects: Any) -> list:
    lines = []
    for path in list(getattr(record, "skills", None) or []):
        try:
            gone = effects.remove_skill_dir(path)
        except Exception as exc:
            lines.append("could not remove {}: {}: {}".format(path, type(exc).__name__, exc))
            continue
        lines.append("removed: skill {}".format(path) if gone else "still there: {}".format(path))
    return lines or ["nothing to remove"]


def _remember(record: Any, store: Any) -> bool:
    """Persist the record so undo has something exact to reverse.

    Returns False when it could not be written, so the receipt says so instead of
    offering an undo with nothing to reverse.
    """
    store = store if store is not None else _store()
    try:
        store.add(record)
    except Exception:  # a receipt that cannot be saved is still a receipt
        return False
    return True


def _store() -> Any:
    from . import state

    return state.Store()


def _seams() -> Any:
    from . import seams

    return seams


def register(ctx: Any) -> None:
    """Wire one slash command, plus the one bare word a shown catalog card accepts."""
    from . import reply

    ctx.register_command(
        "concierge",
        handler=handle_concierge,
        description="Bots and skills in one sentence: install, hire, train, list, fire, reset, undo.",
        args_hint="<sentence> | hire | train | bots | fire | reset | undo | help",
    )
    # On a messaging surface the catalog card's "yes" is a bare word. The CLI has no such seam, so
    # there the card says /concierge yes and this hook simply never fires.
    ctx.register_hook(reply.HOOK, reply.on_gateway_dispatch)


__all__ = [
    "HELP",
    "USAGE",
    "YES",
    "NO",
    "UNDO_WORDS",
    "handle_concierge",
    "handle_hire",
    "handle_train",
    "handle_undo",
    "register",
]
