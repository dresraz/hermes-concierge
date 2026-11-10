"""The command surface: one command, one sentence, one result.

  /concierge <sentence>          install a plugin or skill into this profile
  /concierge <sentence> into <bot>
                                 install it into that bot instead
  /concierge create <sentence>     make a new bot
  /concierge improve <bot>: <what> teach a bot one standing habit
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

import os
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

HELP_SHORT = (
    ""
    "Concierge\n"
    "One sentence does the work.\n"
    "\n"
    "/concierge install obsidian adds a plugin or skill.\n"
    "/concierge create a researcher makes a bot, with skills.\n"
    "/concierge improve coder-bot: always run tests.\n"
    "\n"
    "/concierge browse pdf looks first.\n"
    "/concierge bots shows your bots.\n"
    "/concierge undo takes back the last change.\n"
    "/concierge help all shows every command.\n"
    "\n"
)

HELP = (
    "\n"
    "Concierge\n"
    "Bots, plugins and skills, one sentence at a time.\n"
    "\n"
    "/concierge shows the shelf: what can be added.\n"
    "/concierge browse <word> looks through the shelf.\n"
    "/concierge browse <word> 2 shows the next page.\n"
    "/concierge <sentence> installs a plugin or skill into this profile.\n"
    "/concierge create <sentence> makes a new bot.\n"
    "/concierge improve <bot>: <what> adds what that bot is missing.\n"
    "/concierge bots lists the bots Concierge made.\n"
    "/concierge skills <bot> shows what that bot has installed.\n"
    "/concierge fire <n> deletes bot number n.\n"
    "/concierge reset <n> takes back what Concierge changed in bot n.\n"
    "/concierge undo takes back the last thing Concierge did.\n"
    "/concierge help shows this list.\n"
    "\n"
    "Add \"into <bot>\" to install into a bot instead of this profile.\n"
    "A marketplace install shows one card and waits for your yes.\n"
    "On a card: yes installs it, no drops it, more describes the runner-up.\n"
    "Bots and training act straight away and show a receipt.\n"
    "\n"
    "improve works on any bot on this machine, not only ones Concierge made.\n"
    "\n"
    "Roles create with their skills: researcher, writer, coder, assistant,\n"
    "marketer, watcher, designer, analyst, tutor, planner.\n"
    "\n"
    "Example: /concierge install stripe payments into intern\n"
    "Example: /concierge create a researcher for papers\n"
    "Example: /concierge improve researcher-bot: it needs to read scanned PDFs\n"
    "Example: /concierge create keeps my inbox at zero\n"
    "Name it: /concierge create inbox-zero: keeps my inbox at zero\n"
)

def _clean(raw: Any) -> str:
    return " ".join(str(raw or "").split())


# Intent lives in the model router now (router.route); no word lists here.


def _self_name() -> str:
    """The profile running this command, or "" when it cannot be read."""
    try:
        from . import seams

        return str(seams.current_profile() or "")
    except Exception:
        return ""


def _drop_cards(session_key: str) -> None:
    """Forget every waiting card in this conversation, on both shelves."""
    from . import card, market

    card.forget(session_key)
    market.forget(session_key)


def _inside(path: "Path", home: "Path") -> bool:
    """True when path really lives under home, not beside a name that shares a prefix."""
    try:
        return path.resolve().is_relative_to(home.resolve())
    except AttributeError:  # pragma: no cover - very old pythons
        return str(path.resolve()).startswith(str(home.resolve()) + "/")


def _is_bot_profile() -> bool:
    """True when this command runs inside a bot, not the owner's profile.

    A bot is a profile directory under ``profiles/``. A scratch HERMES_HOME
    reports itself as "custom", which is not a bot and must keep full power.
    """
    try:
        from hermes_constants import get_hermes_home

        home = Path(str(get_hermes_home()))
    except Exception:
        return False
    # A bot's home is <root>/profiles/<name>; the owner's home is the root.
    return home.parent.name == "profiles" and home.name not in ("", "profiles")





_ROUTING = False


def _model_route(text: str, *, store: Any) -> Optional[dict]:
    """Ask the model what this sentence is. None when it cannot answer."""
    global _ROUTING

    if _ROUTING:
        return None
    from . import router

    bots = _bot_names()
    here = _self_name() if _is_bot_profile() else ""
    _ROUTING = True
    try:
        return router.route(text, here=here, bots=bots, llm=_llm())
    finally:
        _ROUTING = False


def _run_route(
    route: dict,
    text: str,
    *,
    store: Any,
    session_key: str,
    known: Optional[Sequence[str]] = None,
    hire: Optional[Callable[..., Any]] = None,
    seams: Any = None,
) -> Optional[str]:
    """Carry out the action the model named, with the code that owns it."""
    action = route.get("action")
    what = route.get("what") or text
    bot = (route.get("bot") or "").strip()
    _drop_cards(session_key)

    if action == "help":
        return HELP_SHORT
    if action == "list":
        return _safe_bots(store)
    if action == "browse":
        from . import shelf

        words = (what or "").split()
        page = 1
        if len(words) > 1 and words[-1].isdigit() and len(words[-1]) <= 3:
            page = int(words[-1])
            what = " ".join(words[:-1])
        if what and what.lower() != text.lower():
            return shelf.browse(what, session_key=session_key, page=page)
        return shelf.overview()
    if action == "undo":
        global _ROUTING
        _ROUTING = True
        try:
            return handle_concierge("undo", store=store, session_key=session_key)
        finally:
            _ROUTING = False
    if action == "install":
        return handle_install(what, store=store, session_key=session_key)
    if action == "improve":
        target = bot or (_self_name() if _is_bot_profile() else None)
        return handle_improve(what, store=store, known=known, bot=target)
    if action == "create":
        return handle_hire(what, store=store, hire=hire, known=known)
    if action in ("fire", "reset"):
        said = route.get("what") or ""
        parts = (said.split() or [""])
        selector = parts[0].strip(" .:-")
        confirm = " ".join(parts[1:])
        from . import lifecycle

        selector, note = _resolve_bot(store, said, selector)
        if not lifecycle.is_selector(store, selector):
            if selector and not selector.isdigit():
                return "Concierge did not create {}, so it will not delete it.\n".format(selector)
            return (
                "Deleting a bot needs its number.\n"
                "/concierge bots, then /concierge fire <number>\n"
            )
        if _is_bot_profile():
            return "A bot cannot delete or reset profiles. Ask the owner.\n"
        _drop_cards(session_key)
        try:
            if action == "fire":
                answer = lifecycle.fire(store, selector, confirm=confirm, seams=seams)
            else:
                answer = lifecycle.reset(store, selector, seams=seams)
        except lifecycle.Refused as exc:
            return "{}\n".format(exc)
        return (note + "\n" if note else "") + answer
    if action == "none":
        from . import card as card_mod

        return card_mod.nothing(text)
    return None



def _into_target(text: str):
    """A trailing 'into <name>', as (name, start), the way the old search read it."""
    low = text.lower()
    start = 0
    while True:
        at = low.find("into", start)
        if at < 0:
            return None
        end = at + len("into")
        if (at == 0 or not (low[at - 1].isalnum() or low[at - 1] == "_")) and (
            end >= len(low) or not (low[end].isalnum() or low[end] == "_")
        ):
            gap = end
            while gap < len(text) and text[gap].isspace():
                gap += 1
            if gap > end:
                stop = gap
                while stop < len(text) and (
                    "a" <= text[stop] <= "z" or "A" <= text[stop] <= "Z"
                    or "0" <= text[stop] <= "9" or text[stop] in "_-"
                ):
                    stop += 1
                if stop > gap and not text[stop:].strip():
                    return text[gap:stop], at
        start = at + 1


def handle_concierge(
    raw: Any,
    *,
    store: Any = None,
    session_key: str = "",
    seams: Any = None,
    hire: Optional[Callable[..., Any]] = None,
    known: Optional[Sequence[str]] = None,
    undo: Optional[Callable[..., Any]] = None,
    **_: Any,
) -> str:
    """The whole surface behind one command.

    Core passes the surface's own keywords (``source`` and friends). They are not
    this command's business, and a signature that refuses them crashes the reply.
    """
    from . import card, lifecycle, market

    if store is None:
        from . import state

        store = state.Store()

    refusal = _gateway_refusal(raw, session_key)
    if refusal:
        return refusal
    text = _clean(raw)
    if text.lower().startswith("/concierge"):
        text = text[len("/concierge"):].strip()
    if not text:
        from . import shelf

        return shelf.overview()

    # Offline conveniences: exact single-word commands, decided by
    # whole-string equality on the command text. Everything else is free
    # text for the model router.
    lowered = text.lower()
    if lowered == "help":
        _drop_cards(session_key)
        return HELP_SHORT
    if lowered == "undo":
        _drop_cards(session_key)
        return handle_undo(store=store, undo=undo, seams=seams)

    # A pending card owns this conversation until it is answered: the whole
    # sentence goes to the model with the pending offer's description, and
    # only CONFIRM installs while only DROP clears.
    from . import card as card_mod

    llm = _llm()
    if card_mod.is_waiting(session_key):
        return card_mod.handle(text, session_key=session_key, store=store, llm=llm)
    from . import market as market_mod

    if market_mod.is_waiting(session_key):
        return market_mod.handle(text, session_key=session_key, store=store, llm=llm)

    if lowered.replace(" ", "").isdigit() and len(lowered.replace(" ", "")) > 4:
        return (
            "That looks like a number, not a request.\n"
            "Say what you want in one sentence, like /concierge install obsidian.\n"
        )

    # A number picks from the last shelf this conversation was shown, but only
    # when no card is waiting: a pending card owns every reply.
    if text.isascii() and text.isdigit() and len(text) <= 3:
        from . import shelf

        if shelf.pending(session_key):
            picked = shelf.pick(int(text), session_key=session_key, store=store)
            if picked:
                return picked

    # Free text goes to the model router. With no model there is no second
    # search and no guessing: one plain sentence says what to do instead.
    routed = _model_route(text, store=store)
    if routed is None:
        _drop_cards(session_key)
        return (
            "I need a model to read that. Name the thing and I will install it, "
            "or run /concierge help.\n"
        )
    answer = _run_route(routed, text, store=store, session_key=session_key,
                        known=known, hire=hire, seams=seams)
    if answer is not None:
        return answer
    return (
        "I need a model to read that. Name the thing and I will install it, "
        "or run /concierge help.\n"
    )


def _read_note(typed: Any, resolved: str) -> str:
    """One line when the model heard a different name than was typed."""
    flat = lambda s: "".join(char for char in str(s or "").lower() if char.isalnum())
    if not resolved or flat(typed) == flat(resolved):
        return ""
    return "Read {} as {}.".format(" ".join(str(typed).split()), resolved)


def _resolve_bot(store: Any, said: str, selector: str) -> tuple:
    """Exact bot name first, one model call on the miss path.

    Returns (selector, note). With no model, or when nothing listed fits,
    the selector comes back unchanged and the caller keeps its refusal.
    """
    from . import lifecycle

    if lifecycle.is_selector(store, selector):
        return selector, ""
    if not selector or selector.isdigit():
        return selector, ""
    try:
        from . import router as _router

        heard = _router.resolve_name(said, "bot", _llm())
    except Exception:
        heard = ""
    if heard and lifecycle.is_selector(store, heard):
        return heard, _read_note(said, heard)
    return selector, ""


def _exact_entry(query: str, catalog: list) -> str:
    """The entry whose own name is exactly what was asked for, if any."""
    wanted = "".join(char for char in (query or "").lower() if char.isalnum())
    if not wanted:
        return ""
    for entry in catalog or []:
        name = getattr(entry, "name", "") or (
            entry.get("name", "") if isinstance(entry, dict) else ""
        )
        flat = "".join(char for char in str(name).lower() if char.isalnum())
        if flat and flat == wanted:
            return str(name)
    return ""


def _install_now(name, *, catalog, store, session_key, target, caution="", llm=None):
    """Install the pick and print the receipt. There is no question to answer.

    The sentence already named the entry, so the card is shown and then the
    pending offer is taken through the model like any other answer. With no
    model the pending offer is answered directly: an exact name is plain
    lexical evidence, not a guess.
    """
    from . import card
    from . import market as market_mod

    market_mod.forget(session_key)
    card.handle(name, entries=catalog, store=store, session_key=session_key,
                target=target, caution=caution, llm=llm)
    if llm is None:
        return card._answer(store=store, install=None, session_key=session_key)
    return card.handle("yes", entries=catalog, store=store, session_key=session_key,
                       target=target, caution=caution, llm=llm)


def _exact_skill(query: str) -> str:
    """A skill asked for by its own name installs the way a named plugin does."""
    wanted = "".join(char for char in (query or "").lower() if char.isalnum())
    if not wanted:
        return ""
    try:
        from . import discover

        for item in discover.catalogue():
            flat = "".join(char for char in item["name"].lower() if char.isalnum())
            if flat and flat == wanted:
                return item["name"]
    except Exception:
        return ""
    return ""


def handle_install(
    raw: Any,
    *,
    store: Any = None,
    session_key: str = "",
    catalog: Optional[list] = None,
    search: Optional[Callable[..., list]] = None,
) -> str:
    """Install anything the marketplace holds, into this profile or a named bot."""
    from . import card, market, match, seams

    text = _clean(raw)
    if text.lower().startswith("/concierge"):
        text = text[len("/concierge"):].strip()
    if not text:
        return (
            "Install what? Say it plainly, for example:\n"
            "/concierge install stripe payments\n"
            "/concierge install stripe payments into intern\n"
        )

    query, target = market.split_target(text)
    # Connectors are not installable: name them honestly before any installer runs.
    try:
        from . import search as search_mod

        for row in search_mod._connectors():
            want = "".join(char for char in str(row.get("name", "")).lower() if char.isalnum())
            got = "".join(char for char in query.lower() if char.isalnum())
            if want and (want == got or (len(got) >= 3 and want in got)):
                return "Concierge does not install connectors yet. {} is a connector, so nothing was installed.\n".format(row.get("name", ""))
    except Exception:
        pass
    if _is_bot_profile():
        here = _self_name()
        if target and target != here:
            return "This bot can only install into itself, not {}.\n".format(target)
        target = here
    if not target:
        aimed = _into_target(text)
        try:
            known_destination = bool(aimed and seams.profile_exists(aimed[0]))
        except Exception:
            known_destination = False
        if aimed and not known_destination:
            return "No bot called {}. Say /concierge bots to see them.\n".format(aimed[0])
        if aimed and known_destination:
            target = aimed[0]
            query = text[: aimed[1]].strip()

    # The plugin shelf answers first because its card carries the scan verdict.
    if catalog is None:
        try:
            catalog = seams.catalog()
        except Exception:
            catalog = []
    # A waiting card owns every reply: the sentence is handed to the model
    # with the pending offer's description, and only CONFIRM installs.
    if card.is_waiting(session_key):
        return card.handle(text, entries=catalog, store=store,
                           session_key=session_key, target=target, llm=_llm())

    # Asked for by name, with nothing to choose: install and print the receipt.
    # The card exists to ask a question; when the sentence already answered it,
    # the question is friction.
    # A near-miss by name gets one model call first: typos and spoken forms
    # ("obsdian", "writer bot") resolve to the listed name.
    note = ""
    exact = _exact_entry(query, catalog)
    exact_skill = "" if exact else _exact_skill(query)
    if not exact and not exact_skill:
        try:
            from . import router as _router

            heard = _router.resolve_name(query, "thing", _llm())
        except Exception:
            heard = ""
        if heard:
            note = _read_note(query, heard)
            query = heard
            exact = _exact_entry(query, catalog)
            if not exact:
                exact_skill = _exact_skill(query)
    if exact:
        answer = _install_now(exact, catalog=catalog, store=store,
                              session_key=session_key, target=target, llm=_llm())
        return (note + "\n" if note else "") + answer
    if exact_skill:
        from . import market as market_mod

        market_mod.handle(exact_skill, target=target, session_key=session_key,
                          store=store, search_fn=search, llm=_llm())
        if _llm() is None:
            # No model: the name already said what to install, so the pending
            # offer is answered directly instead of guessed at.
            answer = market_mod._answer(session_key=session_key, store=store)
        else:
            answer = market_mod.handle("yes", target=target, session_key=session_key,
                                       store=store, search_fn=search, llm=_llm())
        return (note + "\n" if note else "") + answer

    # The matcher builds a shortlist; the model picks from it. A name asked for
    # by name skips the model, so obvious asks stay instant.
    from . import choose

    choice = choose.pick(query, llm=_llm(), entries=catalog)
    if choice is not None:
        caution = getattr(choice, "caution", "")
        if getattr(choice, "kind", "") == "builtin":
            tool = getattr(choice, "description", "") or "its built-in tools"
            return (
                "Nothing to install: Hermes already does this with {}.\n"
                "No plugin needed, and nothing was added.\n"
                "If you want a bot that does it for you: /concierge create {}\n"
            ).format(tool, query[:60])
        if getattr(choice, "kind", "") == "skill":
            answer = market.handle(choice.name, target=target, session_key=session_key,
                                   store=store, search_fn=search, caution=caution,
                                   llm=_llm())
            return (note + "\n" if note else "") + answer
        answer = _install_now(choice.name, catalog=catalog, store=store,
                               session_key=session_key, target=target, caution=caution,
                               llm=_llm())
        return (note + "\n" if note else "") + answer
    if _llm() is None:
        # No model, no guessing: the sentence needs a reader.
        return (
            "I need a model to read that. Name the thing and I will install it, "
            "or run /concierge help.\n"
        )
    # The same ranked list browse shows: the same words offer the same names.
    try:
        from . import search as search_mod

        shared = search_mod.candidates(query, limit=8)
    except Exception:
        shared = []
    if shared:
        top = shared[0]
        if top.get("kind") == "skill":
            answer = market.handle(top["name"], target=target, session_key=session_key,
                                   store=store, search_fn=search, llm=_llm())
        else:
            answer = card.handle(top["name"], entries=catalog, store=store,
                                 session_key=session_key, target=target, llm=_llm())
        return (note + "\n" if note else "") + answer
    # Nothing was picked, so nothing is installed. Falling through to a second
    # lexical search here is how a polite "keep my desk tidy" ended up offering
    # a submission ledger: two shots at a wrong answer instead of one honest no.
    answer = card.nothing(query)
    answer += (
        "If no tool can do it, a bot can try: /concierge create {}\n".format(query[:60])
    )
    return (note + "\n" if note else "") + answer


def handle_hire(
    raw: Any,
    *,
    store: Any = None,
    hire: Optional[Callable[..., Any]] = None,
    known: Optional[Sequence[str]] = None,
) -> str:
    """One sentence in, one new bot out. No confirmation: the sentence was the request."""
    from . import bots, lifecycle, seams, state

    if _is_bot_profile():
        return "A bot cannot make other bots. Ask the owner.\n"

    text = _clean(raw)
    if text.lower().startswith("/concierge"):
        text = text[len("/concierge"):].strip()
    if not text:
        return "Usage: /concierge create <sentence>. For example: /concierge create keeps my inbox at zero.\n"

    plan = bots.spec(text, llm=_llm())
    if plan.name == lifecycle.DEFAULT:
        return (
            "{} is the profile you are talking to, not a bot. Name this one:\n"
            "/concierge create {}-2: {}\n".format(plan.name, plan.name, text)
        )

    taken = list(known) if known is not None else bots.names()
    if plan.name in taken:
        return (
            "{} already exists.\n\n"
            "Name it yourself and try again, for example:\n"
            "/concierge create {}-2: {}\n".format(plan.name, plan.name, text)
        )

    try:
        if hire is None:
            plan, path = bots.hire(text, llm=_llm())
        else:
            plan, path = hire(text)
    except bots.Collision as exc:
        return "{} already exists. Nothing was created.\n".format(exc.name)
    except Exception as exc:
        return "Not hired: {}: {}\n".format(type(exc).__name__, exc)

    # The role's soul and skills must land before the receipt is computed, or the
    # card reports the generic soul the hire flow wrote a moment earlier. A preset
    # failure never costs the bot: it exists, and the receipt says what is missing.
    key_lines: list[str] = []
    try:
        plugin_lines = _inherit_plugins(path)
    except Exception as exc:
        plugin_lines = ["Plugins use stock defaults: copy failed ({}).".format(type(exc).__name__)]
    try:
        preset_lines = _apply_preset(text, plan.name, path)
    except Exception:
        preset_lines = []
    # Last, after every other writer has touched config.yaml: linking earlier
    # let the credential copy rewrite the file and drop the switch.
    try:
        self_lines = (
            []
            if seams.link_self_plugin(path)
            else ["Link failed: no /concierge in this bot."]
        )
    except Exception:
        self_lines = []

    from . import presets

    llm = _llm()
    lines, ok = bots.receipt(
        plan, path, known=taken, count_skills=presets.detect(text, llm) is None
    )
    # Record what hire wrote, not just that a bot exists: the role preset's
    # skills are stock, and reset keeps stock while taking back later changes.
    # Without the role and its skills, reset claims it replayed every record
    # while leaving the hire-time tree behind.
    role_name = ""
    preset_skills: list = []
    try:
        role = presets.detect(text, llm) or presets.get("assistant")
        if role is not None:
            role_name = str(role.name)
            try:
                preset_skills = list(presets.verify(Path(str(path)), role))
            except Exception:
                preset_skills = list(role.picks)
    except Exception:
        role_name = ""
        preset_skills = []
    saved = _remember(
        state.Installed(
            name=plan.name,
            kind="bot",
            title=plan.title,
            profile=plan.name,
            soul_path=str(Path(str(path)) / "SOUL.md"),
            enabled=True,
            role=role_name,
            skills=preset_skills,
        ),
        store,
    )
    head = "Created {}".format(plan.name) if ok else "Created {}, but check this".format(plan.name)
    undo_line = "Undo with /concierge undo." if saved else "Undo is off for this one: the record could not be saved."
    return "\n".join(
        [head, ""]
        + list(lines)
        + key_lines
        + self_lines
        + plugin_lines
        + preset_lines
        + [
            "",
            "Next: /concierge improve {}: <habit>".format(plan.name),
            undo_line,
            "",
        ]
    )


def _safe_bots(store: Any) -> str:
    """The bot list, or an honest line when the store cannot be read."""
    try:
        from . import lifecycle

        return lifecycle.card(store)
    except Exception:
        return "The bot list could not be read just now. Nothing was changed.\n"




def _inherit_plugins(profile_path: Any) -> list[str]:
    """Your plugin switches ride along. Never fatal: the bot exists either way."""
    from . import plugins_inherit

    return plugins_inherit.inherit(profile_path).lines()


def _apply_preset(text: str, name: str, profile_path: Any) -> list[str]:
    """A role sentence also installs that role's skills. Never fatal: the bot exists."""
    from . import bots, presets

    llm = _llm()
    role = presets.detect(text, llm) or presets.get("assistant")
    if role is None:  # the roster always names an assistant; never crash the hire
        return list(_job_line(text, profile_path, bots))
    try:
        report = presets.install(name, Path(str(profile_path)), role, llm=llm)
    except Exception as exc:
        return ["Role skills skipped: {}: {}.".format(type(exc).__name__, exc)] + _job_line(
            text, profile_path, bots
        )
    lines = report.lines() if report.wanted else []
    if llm is None:
        # No model, no role choice: say so instead of a silent default.
        lines = list(lines) + [presets.ROLE_FALLBACK_NOTE]
    return lines + _job_line(text, profile_path, bots)


def _job_line(text: str, profile_path: Any, bots: Any) -> list[str]:
    """Keep the owner's job on the soul, whatever the role install did."""
    try:
        job = bots.spec(text).title
        soul = Path(str(profile_path)) / "SOUL.md"
        if not job or not soul.is_file():
            return []
        body = soul.read_text(encoding="utf-8")
        if "Your job here:" in body:
            return []
        line = "Your job here: {}{}.".format(job[:1].lower(), job[1:]).rstrip(".") + "."
        soul.write_text(body.rstrip() + "\n\n" + line + "\n", encoding="utf-8")
        return []
    except Exception:
        return []


def handle_improve(
    raw: Any,
    *,
    store: Any = None,
    known: Optional[Sequence[str]] = None,
    bot: Optional[str] = None,
) -> str:
    """Make an existing bot better: a skill from the marketplace, or one rule.

    Works on any profile, not only the ones Concierge made. The marketplace is
    not a walled garden; delete and reset stay limited, because removing a
    stranger's bot is destructive.
    """
    from . import improve, training

    text = _clean(raw)
    if text.lower().startswith("/concierge"):
        text = text[len("/concierge"):].strip()
    if not text:
        return (
            "Improve which bot? Say it plainly:\n"
            "/concierge improve researcher-bot: it needs to read scanned PDFs\n"
        )
    if bot:
        sentence = text
    else:
        try:
            names = list(known) if known is not None else _bot_names()
        except Exception:
            names = []
        bot, sentence = training.guess_bot(text, names or None)
    if _is_bot_profile():
        here = _self_name()
        if (bot or "").lower() in ("me", "myself", "self", "yourself", "itself", "you", "your self", ""):
            bot = here
        if bot != here:
            return "This bot can only improve itself, not {}.\n".format(bot)
    if not sentence:
        return (
            "Improve {} how? Name the job: /concierge improve {}: it needs to read PDFs.\n"
            .format(bot, bot)
        )
    llm = _llm()
    plan = improve.plan(bot, sentence, llm=llm)
    note = ""
    if plan is None and (bot or "") and llm is not None:
        # A near-miss ("my researcher bot") gets one model call before the no.
        try:
            from . import router as _router

            heard = _router.resolve_name(bot, "bot", llm)
        except Exception:
            heard = ""
        if heard:
            retry = improve.plan(heard, sentence, llm=llm)
            if retry is not None:
                note = _read_note(bot, heard)
                bot, plan = heard, retry
    if plan is None:
        return "No bot called {}. Say /concierge bots to see them.\n".format(bot)
    if not plan.items and not getattr(plan, "have", None) and llm is None:
        # No model, no verdict: the sentence names no skill, and only a reader
        # can say whether it is a rule or a capability.
        return (
            "I need a model to read that. Name the thing and I will install it, "
            "or run /concierge help.\n"
        )
    answer = improve.receipt(plan, improve.apply(plan, store=store))
    return (note + "\n" if note else "") + answer


def _llm() -> Any:
    """The plugin's model handle, or None when it is not available."""
    ctx = _CTX
    if ctx is None:
        return None
    try:
        return ctx.llm
    except Exception:
        return None




def _bot_names() -> list:
    """Every profile on this machine, read off the disk."""
    from . import improve

    names = []
    root = improve.resolve("default")
    if root is not None and (root / "profiles").is_dir():
        names = sorted(p.name for p in (root / "profiles").iterdir() if p.is_dir() and not p.name.startswith("."))
    return ["default"] + names


def handle_undo(*, store: Any = None, undo: Optional[Callable[..., Any]] = None, seams: Any = None) -> str:
    """Reverse the last record, then check on disk that it is really gone."""
    store = store if store is not None else _store()
    record = store.latest()
    if record is not None and _is_bot_profile():
        here = _self_name()
        owner = getattr(record, "profile", "") or getattr(record, "name", "")
        if owner and owner != here:
            return "This bot can only undo its own changes.\n"
    if record is None:
        try:
            from . import lifecycle as _lifecycle

            made = _lifecycle.bots(store)
        except Exception:
            made = []
        if made:
            # Undo reverses installs and rules, never a profile: saying nothing
            # changed while a bot is standing there reads as a lie.
            return (
                "Nothing to undo. Bots are removed with a sentence of their own:\n"
                "/concierge bots, then /concierge delete 1\n"
            )
        return "Nothing to undo.\n"

    lines = _undo_record(record, undo=undo, seams=seams)
    if any(line.startswith("kept:") for line in lines):
        # A refusal is not an undo: the receipt stays so the bot is still tracked.
        return "\n".join(
            ["Not undone: {}".format(record.name), ""] + list(lines) + [""]
        )
    problems = [line for line in lines if line.startswith(("could not", "still there"))]
    if problems:
        head = "Not fully undone"
        tail = "The receipt is kept, so /concierge undo tries again.\n"
    else:
        store.drop(record.name, record.kind)
        head = "Undone"
        tail = ""
    return "\n".join(
        ["{}: {}".format(head, record.name), ""]
        + list(lines)
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
    if kind == "rule":
        # A rule lives in the bot's own soul, wherever that bot is.
        return _undo_rule(record, effects)
    profile = getattr(record, "profile", "") or ""
    # Checked before the kind, because a skill in another bot has to leave that
    # bot's home, and undo.py only ever looks at this profile.
    if profile and profile != _current_profile():
        return _undo_in(record, profile, seams if seams is not None else _seams())
    if kind == "skill":
        return _undo_skill(record, effects)
    from . import undo as undo_mod

    return list((undo or undo_mod.undo)(record))


def _undo_rule(record: Any, effects: Any) -> list:
    """Put the soul back the way it was before this rule was written."""
    path = getattr(record, "soul_path", "") or ""
    if not path:
        return ["no soul recorded, nothing to restore"]
    snapshot = effects.Snapshot(
        path=path,
        backup=getattr(record, "soul_backup", "") or "",
        existed=bool(getattr(record, "soul_existed", False)),
    )
    try:
        effects.restore_soul(snapshot)
    except Exception as exc:
        return ["could not restore the rule: {}: {}".format(type(exc).__name__, exc)]
    return ["restored: rule in " + (getattr(record, "profile", "") or "this profile")]


def _current_profile() -> str:
    from . import seams

    try:
        return seams.current_profile()
    except Exception:
        return "default"


def _undo_in(record: Any, profile: str, seams: Any) -> list:
    """Take back an install that went into another bot, not into this profile.

    Leaving this to undo.undo would remove the same name from the wrong home and
    then say "already gone" while the bot kept the plugin, so the profile is the
    first thing this asks for.
    """
    name = getattr(record, "name", "") or ""
    kind = getattr(record, "kind", "") or "plugin"
    # A skill carries its name in the same field, so only a plugin record is
    # looked up as a plugin.
    plugin = name if kind != "skill" or getattr(record, "plugin", "") else ""
    lines = []
    try:
        home = seams.profile_home(profile)
    except Exception as exc:
        return ["could not find {}: {}: {}".format(profile, type(exc).__name__, exc)]
    if not plugin and not list(getattr(record, "skills", None) or []):
        return ["nothing to remove: the receipt has no name"]
    if plugin and seams.plugin_dir_in(home, (plugin,)) is None:
        lines.append("already gone: plugin {} in {}".format(plugin, profile))
    elif plugin:
        try:
            seams.remove_plugin_in(profile, plugin)
        except Exception as exc:
            lines.append("could not remove {}: {}: {}".format(plugin, type(exc).__name__, exc))
        else:
            left = seams.plugin_dir_in(home, (plugin,))
            lines.append("removed: plugin {} from {}".format(plugin, profile)
                         if left is None else "still there: {}".format(left))
    from . import effects

    for path in list(getattr(record, "skills", None) or []):
        leaf = str(path).rstrip("/").rsplit("/", 1)[-1]
        exact = Path(str(path))
        # The receipt holds the exact folder that was written. Removing that is
        # the only removal that cannot miss a nested category directory.
        if exact.is_dir() and _inside(exact, Path(str(home))):
            try:
                gone = effects.remove_skill_dir(str(exact))
            except Exception as exc:
                lines.append("could not remove skill {}: {}: {}".format(
                    leaf, type(exc).__name__, exc))
                continue
            lines.append("removed: skill {} from {}".format(leaf, profile)
                         if gone else "still there: skill {} in {}".format(leaf, profile))
            continue
        if seams.skill_dir_in(home, leaf) is None:
            lines.append("already gone: skill {} in {}".format(leaf, profile))
            continue
        try:
            gone = seams.remove_skill_in(profile, leaf)
        except Exception as exc:
            lines.append("could not remove skill {}: {}: {}".format(leaf, type(exc).__name__, exc))
            continue
        lines.append("removed: skill {} from {}".format(leaf, profile)
                     if gone else "still there: skill {} in {}".format(leaf, profile))
    return lines


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
        return ["still there: {}".format(home)]
    return []


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


# The surface this plugin is running on, captured at register. `cli`, `tui`,
# `desktop` and `acp` are the operator's own session; anything else is a messaging
# platform, where a stranger in a group chat could otherwise install code.
_LOCAL_SURFACES = frozenset({"cli", "tui", "desktop", "acp", "webui", "app", "mobile"})

# Refusing on "not in the local list" refused the phone and desktop apps, whose
# identity strings this plugin cannot enumerate. Name the chats that really are
# shared instead: everything else has to be one of Hermes's own surfaces, because
# that is the only place a /concierge command exists at all.
_MESSAGING = frozenset({
    "telegram", "discord", "slack", "whatsapp", "signal", "matrix", "irc",
    "feishu", "teams", "line", "wechat", "messenger", "twilio", "photon",
    "email", "sms", "ntfy", "raft", "a2a", "google_chat", "mattermost",
})
_CTX: Any = None
# The home that published this plugin. Captured at register: inside a routed
# gateway turn get_hermes_home() is the bot's own home, so reading "the owner's
# login" at call time would read the empty profile we are about to fill.
_HOME: Any = None


_PLATFORM: str = ""
# Set while the admission hook answers a shown card, which is not a new ask.
_PLATFORM_ANSWER: bool = False


def _surface() -> str:
    """Where this call runs: the hook's platform, the plugin context, then core.

    A messaging turn binds HERMES_SESSION_PLATFORM; the CLI, the TUI and the
    desktop app bind HERMES_SESSION_SOURCE instead. Reading only the first is why
    /concierge refused itself inside the desktop app. Core has the last word on
    whether a surface is a shared chat (see _gateway_refusal).
    """
    if _PLATFORM:
        return _PLATFORM
    try:
        surface = str(_CTX.session_surface() or "").lower() if _CTX is not None else ""
    except Exception:
        surface = ""
    if surface:
        return surface
    try:
        from gateway.session_context import get_session_env

        return str(get_session_env("HERMES_SESSION_SOURCE", "") or "").lower()
    except Exception:
        return ""


def _allow_gateway() -> bool:
    """The owner's opt-in: plugins.entries.concierge.allow_gateway."""
    try:
        from hermes_cli.config import load_config_readonly

        cfg = load_config_readonly() or {}
        entry = ((cfg.get("plugins") or {}).get("entries") or {}).get("concierge") or {}
        return entry.get("allow_gateway") is True
    except Exception:
        return False


def _messaging() -> bool:
    """Core's own answer to "is this a human chat channel?".

    It knows more surfaces than this plugin can: a slash command runs in a
    worker process that strips session variables, so asking for the surface name
    there always comes back empty and the gate refused the owner's own app.
    """
    try:
        from gateway.session_context import session_is_messaging_surface

        return bool(session_is_messaging_surface())
    except Exception:
        return False


def _names_a_bot(rest: str, store: Any) -> bool:
    """'show me skills that clean up drives' is a search, not a bot called me."""
    name = (rest.split() or [""])[0].lower()
    if not name or name in ("me", "self", "my"):
        return False
    try:
        from . import lifecycle

        return any(
            str(lifecycle.name_of(record)).lower() == name for record in lifecycle.bots(store)
        )
    except Exception:
        return False


def _gateway_refusal(raw: Any, session_key: str = "") -> Optional[str]:
    """A shared chat may look, not change. Returns the refusal, or None.

    The decision comes from core: a surface core calls messaging, or one named
    in _MESSAGING, is a shared chat. A surface in _LOCAL_SURFACES, or one core
    does not call messaging, is the owner's own session. An unknown surface
    with no core answer is therefore allowed: the command only exists on
    Hermes's own surfaces.
    """
    # A card yes is still a change: it needs the same verdict as a normal
    # command. Only the owner's opt-in or a non-chat surface allows it.
    # Dropping the card changes nothing, so a DROP stays allowed: refusing it
    # would strand the card. The model reads the reply to decide.
    if _PLATFORM_ANSWER:
        try:
            from . import card as _card_mod
            from . import reply as _reply_mod

            verdict = _card_mod.decide_answer(
                _clean(raw), _reply_mod._pending_description(session_key), _llm()
            )
        except Exception:
            verdict = "OTHER"
        if verdict == "DROP":
            return None
        if _allow_gateway():
            return None
        surface = _surface()
        if surface in _LOCAL_SURFACES:
            return None
        if not _messaging() and surface not in _MESSAGING:
            return None
        # Otherwise fall through to the refusal below: a bare yes on a
        # shared chat does not install.
    if _allow_gateway():
        return None
    surface = _surface()
    if surface in _LOCAL_SURFACES:
        return None
    if not _messaging() and surface not in _MESSAGING:
        return None
    text = _clean(raw)
    if text.lower().startswith("/concierge"):
        text = text[len("/concierge"):].strip()
    low = text.lower()
    if low in ("", "help", "help all", "bots", "browse", "shelf"):
        return None
    if low.split(" ", 1)[0] in ("help", "bots", "browse", "shelf"):
        return None
    return (
        "Concierge changes this machine, so it does not run from a shared chat.\n"
        "Ask the owner, or set plugins.entries.concierge.allow_gateway: true.\n"
    )


def bind(ctx: Any) -> None:
    """Hold the context, without registering anything (the reload seam needs it)."""
    global _CTX, _HOME

    _CTX = ctx
    try:
        _HOME = Path(str(ctx.home_path)) if getattr(ctx, "home_path", None) else None
    except Exception:
        _HOME = None


def register(ctx: Any) -> None:
    """Wire one slash command, plus the one bare word a shown catalog card accepts."""
    from . import reply

    bind(ctx)

    ctx.register_command(
        "concierge",
        handler=handle_concierge,
        description="Bots, plugins and skills in one sentence: install, create, improve, list, fire, reset, undo.",
        args_hint="<sentence> | create | improve | bots | fire | reset | undo | help",
    )
    # On a messaging surface the catalog card's "yes" is a bare word. The CLI has no such seam, so
    # there the card says /concierge yes and this hook simply never fires.
    ctx.register_hook(reply.HOOK, reply.on_admission)


__all__ = [
    "HELP",
    "handle_concierge",
    "handle_hire",
    "handle_undo",
    "register",
]
