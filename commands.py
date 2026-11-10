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

from . import text as _text

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

USAGE = HELP

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

        if what and what.lower() != text.lower():
            return shelf.browse(what)
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
        selector = (what.split() or [""])[0].strip(" .:-")
        from . import lifecycle

        if not lifecycle.is_selector(store, selector):
            return (
                "Deleting a bot needs its number, so nothing is removed by a guess.\n"
                "/concierge bots, then /concierge fire <number>\n"
            )
        return handle_concierge(
            "{} {}".format(action, selector), store=store, session_key=session_key
        )
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
    train: Optional[Callable[..., Any]] = None,
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

    refusal = _gateway_refusal(raw)
    if refusal:
        return refusal
    text = _clean(raw)
    if text.lower().startswith("/concierge"):
        text = text[len("/concierge"):].strip()
    low = text.lower()
    if not text:
        from . import shelf

        return shelf.overview()

    # A card word with no card in front of it is not a search term: "more" was
    # once answered by installing a random plugin.
    bare = "".join(
        char for char in low if "a" <= char <= "z" or "0" <= char <= "9" or char == " "
    ).strip()
    if bare in ("yes", "no", "more", "next", "1", "2") and not (
        card.is_waiting(session_key) or market.is_waiting(session_key)
    ):
        from . import shelf

        # A shelf was just shown: "no" closes it, it is not a mistake.
        if bare == "no" or shelf._rows(session_key):
            shelf.forget(session_key)
            if bare == "no":
                return "Nothing installed.\n"
        if bare in ("yes", "1"):
            return "Nothing to say yes to yet. Say the job: /concierge something that reads my pdfs.\n"
        return "Pick a number from the list, or say the job in one sentence.\n"
    if low in ("help all", "help -a", "help --all"):
        _drop_cards(session_key)
        return HELP
    if low == "help":
        _drop_cards(session_key)
        return HELP_SHORT


    # A card this conversation was shown owns yes, no, more and 1. Checked before
    # anything forgets it, or the flagship loop dies on its own receipt.
    from . import card as card_mod

    if card_mod.is_waiting(session_key):
        word = low.strip().rstrip("!.")
        if (
            word in card_mod.YES
            or word in card_mod.NO
            or word in card_mod.MORE
            or word in ("1", "2")
        ):
            return card_mod.handle(text, session_key=session_key, store=store)
        # Any other sentence is a new request: the old card is dropped below.
    if low == "undo":
        _drop_cards(session_key)
        return handle_undo(store=store, undo=undo, seams=seams)

    if low.replace(" ", "").isdigit() and len(low.replace(" ", "")) > 4:
        return (
            "That looks like a number, not a request.\n"
            "Say what you want in one sentence, like /concierge install obsidian.\n"
        )

    head, _, _ = low.partition(" ")
    rest = text[len(head):].strip()

    if head in ("browse", "shelf"):
        from . import shelf

        _drop_cards(session_key)
        words = rest.split()
        page = 1
        if len(words) > 1 and words[-1].isdigit() and len(words[-1]) <= 3:
            page = int(words[-1])
            rest = " ".join(words[:-1])
        return shelf.browse(rest, session_key=session_key, page=page)

    # A number picks from the last shelf this conversation was shown, unless a
    # card is waiting: on a card "1" means yes.
    if text.isascii() and text.isdigit() and len(text) <= 3:
        from . import shelf

        waiting = bool((card._slot(session_key) or {}).get("entries"))
        # A listing the user is looking at owns the number; a card owns yes/no.
        if shelf.pending(session_key):
            picked = shelf.pick(int(text), session_key=session_key, store=store)
            if picked:
                return picked
        if waiting and text != "1":
            return "One card at a time. /concierge yes takes it, /concierge no drops it.\n"

    if head in ("skills", "show") and _names_a_bot(rest, store):
        from . import improve, lifecycle, state

        if not rest and not _is_bot_profile():
            # No name in the owner's profile: a fleet summary, not 200 lines.
            try:
                made = [lifecycle.name_of(record) for record in lifecycle.bots(store)]
            except Exception:
                return "The bot list could not be read just now. Nothing was changed.\n"
            if not made:
                return "No bots yet. Make one: /concierge create a researcher.\n"
            lines = ["Skills each bot has:", ""]
            for bot in made:
                home = improve.resolve(bot)
                count = len(improve.installed(home)) if home is not None else 0
                lines.append("{}: {}".format(bot, "{} skills".format(count) if count else "none yet"))
            lines.append("")
            lines.append("One bot in detail: /concierge skills <bot>.")
            lines.append("")
            return "\n".join(lines)
        name = rest.split()[0] if rest else _self_name()
        try:
            home = improve.resolve(name)
        except Exception:
            home = None
        if home is None:
            return "No bot called {}. Say /concierge bots to see them.\n".format(name)
        have = sorted(improve.installed(home))
        if not have:
            return "{} has no skills of its own yet.\nGive it one: /concierge improve {}: it needs to read scanned PDFs.\n".format(name, name)
        return "{} has these skills: {}\n".format(name, ", ".join(have))

    if head == "bots":
        _drop_cards(session_key)
        return _safe_bots(store)

    if head in ("fire", "delete", "remove", "rm", "reset"):
        if _is_bot_profile():
            return "A bot cannot delete or reset profiles. Ask the owner.\n"
        # "fire the intern" is a sentence, not a bot: only a selector fires.
        parts = rest.split()
        selector = parts[0] if parts else ""
        confirm = " ".join(parts[1:])
        if not lifecycle.is_selector(store, selector):
            return card.handle(text, session_key=session_key)
        _drop_cards(session_key)
        try:
            if head in ("fire", "delete", "remove", "rm"):
                return lifecycle.fire(store, selector, confirm=confirm, seams=seams)
            return lifecycle.reset(store, selector, seams=seams)
        except lifecycle.Refused as exc:
            return "{}\n".format(exc)

    if head == "create":
        _drop_cards(session_key)
        return handle_hire(rest, store=store, hire=hire, known=known)

    if head == "improve":
        _drop_cards(session_key)
        return handle_improve(rest, store=store, known=known)

    # "install <what> into <bot>" is the same sentence as a plain request, with
    # the destination said out loud. Both shelves are searched: plugins first,
    # then skills, and whichever answers gets one card and one yes.
    if head == "install":
        from . import market as market_mod

        _drop_cards(session_key)
        market_mod.forget(session_key)
        return handle_install(rest, store=store, session_key=session_key)

    # Bare yes/no/more belong to a card this conversation was shown.
    from . import market as market_mod

    if market_mod.is_waiting(session_key):
        return market_mod.handle(text, session_key=session_key, store=store)
    # Old words are gone, but a stale habit should get a pointer, not a mystery.
    first, _, after = text.partition(" ")
    if first.lower() == "hire":
        return "hire is gone. Same thing: /concierge create {}\n".format(after.strip() or "<sentence>")
    if first.lower() == "train":
        return "train is gone. Same thing: /concierge improve {}\n".format(after.strip() or "<bot>: <what>")

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
                        known=known, hire=hire)
    if answer is not None:
        return answer
    return (
        "I need a model to read that. Name the thing and I will install it, "
        "or run /concierge help.\n"
    )


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


def _install_now(name, *, catalog, store, session_key, target, caution=""):
    """Install the pick and print the receipt. There is no question to answer."""
    from . import card

    card.handle(name, entries=catalog, store=store, session_key=session_key,
                target=target, caution=caution)
    return card.handle("yes", entries=catalog, store=store, session_key=session_key,
                       target=target, caution=caution)


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
    # A waiting card owns yes/no/more and a bare number, so those answer before
    # any search. A new sentence is a new request, not an answer to the card.
    answer_word = "".join(
        char for char in text.lower() if "a" <= char <= "z" or "0" <= char <= "9" or char == " "
    ).strip()
    if card.is_waiting(session_key) and (
        answer_word in ("yes", "y", "no", "n", "more") or answer_word.isdigit()
    ):
        return _install_now(text, catalog=catalog, store=store,
                            session_key=session_key, target=target)

    # Asked for by name, with nothing to choose: install and print the receipt.
    # The card exists to ask a question; when the sentence already answered it,
    # the question is friction.
    exact = _exact_entry(query, catalog)
    if exact:
        card.handle(exact, entries=catalog, store=store, session_key=session_key, target=target)
        return card.handle("yes", entries=catalog, store=store, session_key=session_key,
                           target=target)
    exact_skill = _exact_skill(query)
    if exact_skill:
        market.handle(exact_skill, target=target, session_key=session_key,
                      store=store, search_fn=search)
        return market.handle("yes", target=target, session_key=session_key,
                             store=store, search_fn=search)

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
            return market.handle(choice.name, target=target, session_key=session_key,
                                 store=store, search_fn=search, caution=caution)
        return _install_now(choice.name, catalog=catalog, store=store,
                            session_key=session_key, target=target, caution=caution)
    if _llm() is None:
        # No model, no guessing: the sentence needs a reader.
        return (
            "I need a model to read that. Name the thing and I will install it, "
            "or run /concierge help.\n"
        )
    # Nothing was picked, so nothing is installed. Falling through to a second
    # lexical search here is how a polite "keep my desk tidy" ended up offering
    # a submission ledger: two shots at a wrong answer instead of one honest no.
    answer = card.nothing(query)
    answer += (
        "If no tool can do it, a bot can try: /concierge create {}\n".format(query[:60])
    )
    return answer


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
        return "A bot cannot make other bots. Ask the owner, or improve yourself.\n"

    text = _clean(raw)
    if text.lower().startswith("/concierge"):
        text = text[len("/concierge"):].strip()
    if not text:
        return "Usage: /concierge create <sentence>. For example: /concierge create keeps my inbox at zero.\n"

    plan = bots.spec(text)
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
        plan, path = (hire or bots.hire)(text)
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
    try:
        extra_lines = _suggest_extras(text, path)
    except Exception:
        extra_lines = []
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

    lines, ok = bots.receipt(
        plan, path, known=taken, count_skills=presets.detect(text) is None
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
    head = "Created {}".format(plan.name) if ok else "Created {}, but check this".format(plan.name)
    undo_line = "Undo with /concierge undo." if saved else "Undo is off for this one: the record could not be saved."
    return "\n".join(
        [head, ""]
        + list(lines)
        + key_lines
        + self_lines
        + plugin_lines
        + preset_lines
        + extra_lines
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

    role = presets.detect(text)
    if role is None:
        # No role word in the sentence: a general assistant is more useful
        # than a thin shell, and the job line still says what it is for.
        role = presets.get("assistant")
    try:
        report = presets.install(name, Path(str(profile_path)), role)
    except Exception as exc:
        return ["Role skills skipped: {}: {}.".format(type(exc).__name__, exc)] + _job_line(
            text, profile_path, bots
        )
    lines = report.lines() if report.wanted else []
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


def _suggest_extras(text: str, profile_path: Any) -> list[str]:
    """Deliberately nothing.

    An audit of the old two-pick suggestion line scored it 1.8 out of 5: a coder
    bot was offered a skill about writing skills, an inbox bot a social calendar.
    A quiet receipt is better than a confident wrong suggestion, so the extras
    live in /concierge browse where the person is asking to look.
    """
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
    bot, sentence = (bot, text) if bot else training.guess_bot(text)
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
    if plan is None:
        names = ", ".join(_bot_names()) or "none"
        return "No bot called {}. Bots here: {}\n".format(bot, names)
    if not plan.items and not getattr(plan, "have", None) and llm is None:
        # No model, no verdict: the sentence names no skill, and only a reader
        # can say whether it is a rule or a capability.
        return (
            "I need a model to read that. Name the thing and I will install it, "
            "or run /concierge help.\n"
        )
    return improve.receipt(plan, improve.apply(plan, store=store))


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
    /concierge refused itself inside the desktop app. Still fail-closed: an
    identity nothing recognises is treated as a shared chat.
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


def _gateway_refusal(raw: Any) -> Optional[str]:
    """A shared chat may look, not change. Returns the refusal, or None."""
    # Answering a card this chat was already shown is not a new request: the
    # card only exists because the action that drew it was allowed.
    if _PLATFORM_ANSWER:
        return None
    if _allow_gateway():
        return None
    surface = _surface()
    if surface in _LOCAL_SURFACES:
        return None
    if surface and surface not in _MESSAGING:
        return None
    if not surface and not _messaging():
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
    "USAGE",
    "handle_concierge",
    "handle_hire",
    "handle_undo",
    "register",
]
