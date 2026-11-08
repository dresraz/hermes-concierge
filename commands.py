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
import re
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

YES = frozenset({"y", "yes", "do it", "ok", "okay", "go", "confirm"})
NO = frozenset({"n", "no", "cancel", "stop", "never mind", "nvm"})
UNDO_WORDS = frozenset({"undo", "revert", "roll back", "rollback", "reverse"})
HELP_WORDS = frozenset({"help", "?", "-h", "--help", "h", "commands"})

HELP = (
    "\n"
    "  CONCIERGE\n"
    "  Bots, plugins and skills, one sentence at a time.\n"
    "\n"
    "  /concierge                     the shelf: what can be added\n"
    "  /concierge browse <word>       look through the shelf\n"
    "  /concierge <sentence>          install a plugin or skill, this profile\n"
    "  /concierge create <sentence>   make a new bot\n"
    "  /concierge improve <bot>: <what>  add what that bot is missing\n"
    "  /concierge bots                list the bots Concierge made\n"
    "  /concierge fire <n>            delete bot number n\n"
    "  /concierge reset <n>           take back what Concierge changed in bot n\n"
    "  /concierge undo                take back the last thing Concierge did\n"
    "  /concierge help                this list\n"
    "\n"
    "  Add \"into <bot>\" to install into a bot instead of this profile.\n"
    "  A marketplace install shows one card and waits for your yes.\n"
    "  On a card: yes installs it, no drops it, more describes the runner-up.\n"
    "  Bots and training act straight away and show a receipt.\n"
    "\n"
    "  improve works on any bot on this machine, not only ones Concierge made.\n"
    "\n"
    "  Roles create with their skills: researcher, writer, coder, assistant,\n"
    "  marketer, watcher, designer, analyst, tutor, planner.\n"
    "\n"
    "  Example: /concierge install stripe payments into intern\n"
    "  Example: /concierge create a researcher for papers\n"
    "  Example: /concierge improve researcher-bot: it needs to read scanned PDFs\n"
    "  Example: /concierge create keeps my inbox at zero\n"
    "  Name it: /concierge create inbox-zero: keeps my inbox at zero\n"
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


# A sentence that names a bot to make is a hire, whatever verb it starts with:
# "install a research bot", "I want a research bot", "make me a coder". The role
# cue is the tell, and a destination ("into <bot>") always wins over it.
BOT_WORDS = frozenset({"bot", "bots", "agent", "agents"})
# Asking for a capability is not asking for a bot, even when a role word shows up.
CAPABILITY_WORDS = frozenset({
    "skill", "skills", "plugin", "plugins", "tool", "tools", "integration",
    "integrations", "app", "apps", "extension", "extensions",
})
# How people ask for a bot without saying "bot": "I need something that ...",
# "I could use a writer", "another researcher".
ASK_WORDS = ("i need", "i want", "i could use", "could use", "looking for",
             "help me", "something that", "one that", "another ", "second ",
             "one more ")
MAKE_VERBS = ("hire", "make ", "make me", "create", "build", "spawn", "set up",
              "stand up", "give me")


_BOTS_PHRASES = (
    r"^(?:what|which|list|show)(?: me)?(?: my| the| all)? bots?\b",
    r"^my bots\b",
    r"^(?:what|how many) bots (?:do i have|have i got|are there)\b",
    r"^bots\b",
)
_BROWSE_PHRASES = (
    r"^(?:what|which) (?:can|should) i (?:install|add|get)\b",
    r"^(?:show|list)(?: me)? what (?:i can|can i) (?:install|add|get)\b",
    r"^(?:show|list)(?: me)?(?: everything| the catalog| the marketplace)\b",
)


def _natural_verb(low: str) -> str:
    """The read-only command a plain sentence is asking for, or ""."""
    for pattern in _BOTS_PHRASES:
        if re.match(pattern, low):
            return "bots"
    for pattern in _BROWSE_PHRASES:
        if re.match(pattern, low):
            return "browse"
    return ""


def _wants_a_bot(text: str) -> bool:
    """True when the sentence asks for a bot, not for a plugin or a skill."""
    from . import market, presets

    low = " ".join((text or "").lower().split())
    if not low or " into " in low:
        return False
    if market.split_target(text)[1]:
        return False
    if presets.detect(text) is None:
        return False
    words = set(re.findall(r"[a-z']+", low))
    if words & BOT_WORDS:
        return True
    return any(low.startswith(verb) for verb in MAKE_VERBS)


def _asks_for_bot(text: str) -> bool:
    """A bot was asked for, whatever the sentence calls it.

    This is the guard that keeps the worst outcome off the screen: showing an
    install card for a random package when the person asked for a bot.
    """
    from . import market

    low = " ".join((text or "").lower().split())
    if not low or market.split_target(text)[1]:
        return False
    words = set(re.findall(r"[a-z']+", low))
    if words & CAPABILITY_WORDS:
        return False
    asked = any(
        verb.strip() in words or low.startswith(verb.strip()) for verb in MAKE_VERBS
    ) or any(phrase in low for phrase in ASK_WORDS)
    if not asked:
        return False
    if words & BOT_WORDS:
        return True
    # "I'd like another researcher" names the role, not the word bot.
    from . import presets

    return presets.detect(low) is not None


def low_verb(text: str) -> str:
    return (text or "").strip().split(" ", 1)[0].lower()


def _self_name() -> str:
    """The profile running this command, or "" when it cannot be read."""
    try:
        from . import seams

        return str(seams.current_profile() or "")
    except Exception:
        return ""


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


def _route(text: str) -> tuple:
    """One sentence, one decision, using the bots that actually exist.

    A bot you already have wins over a new one: naming a role that exists
    improves that bot instead of making a twin. A role with no bot creates one.
    Everything else is an install. This is the whole front door.
    """
    from . import presets

    if _is_bot_profile():
        return "improve", _self_name(), text

    from . import market

    # "into <bot>" is a destination, even when that profile is not registered
    # with core: a folder that looks like a bot is a bot here.
    aimed_into = re.search(r"\binto\s+([a-z0-9_-]+)\s*$", text.lower())
    if aimed_into and (
        aimed_into.group(1) in _bot_names() or low_verb(text) in ("install", "add", "get")
    ):
        return "install", "", text
    query, target = market.split_target(text)
    if target:
        return "install", "", text
    low = " ".join((query or "").lower().split())
    if not low:
        return "install", "", text
    words = set(re.findall(r"[a-z0-9'-]+", low))
    names = [name for name in _bot_names() if name != "default"]
    # A word, not a substring: a bot called "art" must not swallow "start a chart".
    names = [n for n in names if n != "default"]
    for name in sorted(names, key=len, reverse=True):
        if name not in words:
            continue
        # A common-word bot name must be aimed at, not merely present.
        aimed = (
            "-" in name
            or ("-" in name and low.startswith(name))
            or re.search(r"\b(?:my|the|for|into|to)\s+" + re.escape(name) + r"\b", low)
        )
        if aimed:
            return "improve", name, query
    # "make my researcher cite sources" is aimed at the researcher you have.
    mine_word = re.search(r"\bmy\s+([a-z0-9][a-z0-9-]*)", low)
    if mine_word:
        wanted = mine_word.group(1)
        if wanted in names or presets.get(wanted) is not None:
            for name in names:
                if name == wanted or name.startswith(wanted + "-"):
                    return "improve", name, query
            return "improve", wanted, query

    role = presets.detect(query)
    if role is None:
        # "another assistant" names the role after the qualifier, not before it.
        trimmed = re.sub(r"^(?:one more|another|a second|second|new)\s+", "", low)
        if trimmed != low:
            role = presets.detect(trimmed)
            if role is None:
                for name in presets.names():
                    if name in trimmed.split():
                        role = presets.get(name)
                        break
    if role is None:
        # "make me a bot that does X" with no known role is still a bot, not a
        # marketplace search: the sentence asked for a profile, not a plugin.
        if bool(words & BOT_WORDS) and any(
            verb.strip() in words for verb in MAKE_VERBS
        ):
            return "create", "", query
        return "install", "", text
    # "my researcher" is the one you have, however the sentence starts.
    mine = bool(re.search(r"\bmy\s+(?:[a-z0-9-]+\s+){0,4}(" + "|".join(
        [re.escape(name) for name in names] + [re.escape(role.name)]
    ) + r")\b", low))
    asking = any(phrase in low for phrase in ASK_WORDS)
    creating = not mine and (
        bool(words & BOT_WORDS)
        or any(low.startswith(verb.strip()) for verb in MAKE_VERBS)
        # A role named inside a request, with no capability word anywhere, is a
        # bot being asked for: "I need something that keeps my inbox at zero".
        or (asking and not (words & CAPABILITY_WORDS))
    )
    # 2. a role that already has a bot is improved, unless the sentence asks for
    #    a new one in as many words: a second researcher has to be possible
    for name in names:
        if name == role.name or name.startswith(role.name + "-"):
            if creating:
                return "create", "", query
            return "improve", name, query
    # 3. a role with no bot is created when the sentence asks for one
    if creating or role.name in words:
        return "create", "", query
    return "install", "", text


def _strip_name(text: str, name: str) -> str:
    """The ask without the bot's name in it."""
    out = re.sub(r"\b" + re.escape(name) + r"\b", " ", text, count=1, flags=re.I)
    return " ".join(out.split()).strip(" :,-") or text


def _improve_shape(text: str) -> bool:
    """"<bot>: <what>" is an improve, whatever word came before it."""
    head, sep, rest = (text or "").partition(":")
    return bool(sep and rest.strip() and re.fullmatch(r"[a-z0-9][a-z0-9 ._-]*", head.strip().lower()))


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

    refusal = _gateway_refusal(raw)
    if refusal:
        return refusal
    text = _clean(raw)
    low = text.lower()
    if not text:
        from . import shelf

        return shelf.overview()
    if low in HELP_WORDS:
        card.forget(session_key)
        _forget("", session_key)
        return HELP
    natural = _natural_verb(low)
    if natural == "bots":
        card.forget(session_key)
        _forget("", session_key)
        _repair_keys(store)
        return lifecycle.card(store)
    if natural == "browse":
        from . import shelf

        card.forget(session_key)
        _forget("", session_key)
        return shelf.overview()
    if low in UNDO_WORDS:
        card.forget(session_key)
        _forget("", session_key)
        return handle_undo(store=store, undo=undo, seams=seams)

    head, _, _ = low.partition(" ")
    rest = text[len(head):].strip()

    if head in ("browse", "shelf"):
        from . import shelf

        card.forget(session_key)
        _forget("", session_key)
        return shelf.browse(rest, session_key=session_key)

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
            return "  One card at a time. /concierge yes takes it, /concierge no drops it.\n"

    if head == "bots":
        card.forget(session_key)
        _forget("", session_key)
        _repair_keys(store)
        return lifecycle.card(store)

    if head in ("fire", "reset"):
        if _is_bot_profile():
            return "  A bot cannot delete or reset profiles. Ask the owner.\n"
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

    if head == "create":
        card.forget(session_key)
        _forget("", session_key)
        return handle_hire(rest, store=store, hire=hire, known=known)

    if head == "improve":
        card.forget(session_key)
        _forget("", session_key)
        return handle_improve(rest, store=store, known=known)

    # "install <what> into <bot>" is the same sentence as a plain request, with
    # the destination said out loud. Both shelves are searched: plugins first,
    # then skills, and whichever answers gets one card and one yes.
    if head == "install":
        from . import market as market_mod

        card.forget(session_key)
        market_mod.forget(session_key)
        _forget("", session_key)
        # "install a research bot" is a hire: the sentence names the thing to
        # make, not a package to fetch. A destination still wins.
        if _wants_a_bot(rest):
            return handle_hire(rest, store=store, hire=hire, known=known)
        return handle_install(rest, store=store, session_key=session_key)

    # Bare yes/no/more belong to a card this conversation was shown.
    from . import market as market_mod

    if market_mod.is_waiting(session_key):
        return market_mod.handle(text, session_key=session_key, store=store)
    # Old words are gone, but a stale habit should get a pointer, not a mystery.
    first, _, after = text.partition(" ")
    if first.lower() == "hire":
        return "  hire is gone. Same thing: /concierge create {}\n".format(after.strip() or "<sentence>")
    if first.lower() == "train":
        return "  train is gone. Same thing: /concierge improve {}\n".format(after.strip() or "<bot>: <what>")

    if _improve_shape(text):
        card.forget(session_key)
        _forget("", session_key)
        return handle_improve(text, store=store, known=known)

    intent, bot, sentence = _route(text)
    card.forget(session_key)
    _forget("", session_key)
    if intent == "create":
        return handle_hire(sentence, store=store, hire=hire, known=known)
    if intent == "improve":
        return handle_improve(_strip_name(sentence, bot), store=store, known=known, bot=bot)

    # No bot named: a plugin or a skill. A skill this machine already ships wins
    # when the sentence names it, because it costs nothing and adds no tools;
    # otherwise the catalog answers first, and the skills on disk get a turn
    # only when the catalog has nothing.
    from . import improve

    here = _self_name() or "default"
    if improve.resolve(here) is None:
        here = "default"
    early = improve.plan(here, text)
    low = text.lower()
    if early is not None and any(item.name in low or item.name.replace("-", " ") in low for item in early.items):
        return improve.receipt(early, improve.apply(early, store=store))

    if _asks_for_bot(text):
        return handle_hire(text, store=store, hire=hire, known=known)

    answer = card.handle(text, session_key=session_key)
    if "best match  none" in answer:
        plan = improve.plan(here, text)
        if plan is not None and plan.items:
            return improve.receipt(plan, improve.apply(plan, store=store))
    return answer


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
    if not text:
        return (
            "Install what? Say it plainly, for example:\n"
            "  /concierge install stripe payments\n"
            "  /concierge install stripe payments into intern\n"
        )

    query, target = market.split_target(text)
    if _is_bot_profile():
        here = _self_name()
        if target and target != here:
            return "  This bot can only install into itself, not {}.\n".format(target)
        target = here
    if not target:
        aimed = re.search(r"\binto\s+([a-z0-9_-]+)\s*$", text, re.I)
        if aimed:
            target = aimed.group(1)
            query = text[: aimed.start()].strip()

    # The plugin shelf answers first because its card carries the scan verdict.
    if catalog is None:
        try:
            catalog = seams.catalog()
        except Exception:
            catalog = []
    if match.rank(query, catalog, limit=1):
        return card.handle(query, entries=catalog, store=store,
                           session_key=session_key, target=target)
    return market.handle(query, target=target, session_key=session_key,
                         store=store, search_fn=search)


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
        return "  A bot cannot make other bots. Ask the owner, or improve yourself.\n"

    text = _clean(raw)
    if not text:
        return "Usage: /concierge create <sentence>   e.g. /concierge create keeps my inbox at zero\n"

    plan = bots.spec(text)
    if plan.name == lifecycle.DEFAULT:
        return (
            "  {} is the profile you are talking to, not a bot. Name this one:\n"
            "  /concierge create {}-2: {}\n".format(plan.name, plan.name, text)
        )

    taken = list(known) if known is not None else bots.names()
    if plan.name in taken:
        return (
            "  {} already exists.\n\n"
            "  Name it yourself and try again, for example:\n"
            "  /concierge create {}-2: {}\n".format(plan.name, plan.name, text)
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
        key_lines = _share_keys(plan.name, path)
    except Exception as exc:
        key_lines = ["  keys     not copied: {}".format(type(exc).__name__)]
    try:
        plugin_lines = _inherit_plugins(path)
    except Exception as exc:
        plugin_lines = ["  plugins  stock defaults, copy failed: {}".format(type(exc).__name__)]
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
            ["  self     /concierge inside this bot, for itself only"]
            if seams.link_self_plugin(path)
            else ["  self     no /concierge in this bot (link failed)"]
        )
    except Exception:
        self_lines = []

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
    head = "Created {}".format(plan.name) if ok else "Created {}, but check this".format(plan.name)
    undo_line = "  undo     /concierge undo" if saved else "  no undo  the record could not be saved"
    return "\n".join(
        [head, ""]
        + ["  " + line for line in lines]
        + key_lines
        + self_lines
        + plugin_lines
        + preset_lines
        + extra_lines
        + [
            "",
            "  next     /concierge improve {}: <habit>".format(plan.name),
            undo_line,
            "",
        ]
    )


def _repair_keys(store: Any) -> None:
    """A bot Concierge made should never be missing the owner's login."""
    from . import seams

    for record in getattr(store, "all", lambda: [])():
        if getattr(record, "kind", "") != "bot":
            continue
        lookup = getattr(seams, "profile_home", None)
        if lookup is None:
            continue
        home = lookup(record.profile or record.name)
        try:
            # Not only missing: a rotated key has to reach bots that already
            # exist, or one of them fails auth while everything looks fine.
            seams.share_credentials(home, _HOME)
        except Exception:
            continue


def _share_keys(name: str, profile_path: Any) -> list[str]:
    """A bot needs the same model login, or it cannot answer at all."""
    from . import seams

    copied = seams.share_credentials(profile_path, _HOME)
    if not copied:
        return ["  keys     none to copy, this profile has no credentials yet"]
    return ["  keys     your login, {}".format(", ".join(copied))]


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


def _suggest_extras(text: str, profile_path: Any) -> list[str]:
    """Two more skills that fit the sentence, offered with the command to take one.

    The preset seed is a floor. This reads the skill trees on disk, weighs each
    candidate, and names what else would help this role, never installing it.
    """
    from . import discover, presets

    role = presets.detect(text)
    if role is None:
        return []
    skills_dir = Path(str(profile_path)) / "skills"
    installed = set()
    if skills_dir.is_dir():
        installed = {item.parent.name for item in skills_dir.glob("**/SKILL.md")}
    picks = discover.suggest(
        text, role.name, blurb=role.blurb, skip=installed, limit=2
    )
    return discover.lines(picks, Path(str(profile_path)).name)


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
    if not text:
        return (
            "Improve which bot? Say it plainly:\n"
            "  /concierge improve researcher-bot: it needs to read scanned PDFs\n"
        )
    bot, sentence = (bot, text) if bot else training.guess_bot(text)
    if _is_bot_profile():
        here = _self_name()
        if (bot or "").lower() in ("me", "myself", "self", ""):
            bot = here
        if bot != here:
            return "  This bot can only improve itself, not {}.\n".format(bot)
    if not sentence:
        return (
            "  Improve {} how? Name the job: /concierge improve {}: it needs to read PDFs\n"
            .format(bot, bot)
        )
    plan = improve.plan(bot, sentence)
    if plan is None:
        names = ", ".join(_bot_names()) or "none"
        return "  No bot called {}. Bots here: {}\n".format(bot, names)
    return improve.receipt(plan, improve.apply(plan, store=store))


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
        store.drop(record.name, record.kind)
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
    effects.restore_soul(snapshot)
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
        return ["could not find {}: {}: {}({})".format(profile, type(exc).__name__, exc)]
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
    for path in list(getattr(record, "skills", None) or []):
        leaf = str(path).rstrip("/").rsplit("/", 1)[-1]
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


# The surface this plugin is running on, captured at register. `cli`, `tui`,
# `desktop` and `acp` are the operator's own session; anything else is a messaging
# platform, where a stranger in a group chat could otherwise install code.
_LOCAL_SURFACES = frozenset({"", "cli", "tui", "desktop", "acp", "webui"})
_CTX: Any = None
# The home that published this plugin. Captured at register: inside a routed
# gateway turn get_hermes_home() is the bot's own home, so reading "the owner's
# login" at call time would read the empty profile we are about to fill.
_HOME: Any = None
_READ_ONLY = frozenset({"", "help", "?", "h", "commands", "-h", "--help", "bots", "browse", "shelf"})


def _surface() -> str:
    try:
        return str(_CTX.session_surface() or "").lower() if _CTX is not None else ""
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


def _gateway_refusal(raw: Any) -> Optional[str]:
    """A shared chat may look, not change. Returns the refusal, or None."""
    if _surface() in _LOCAL_SURFACES or _allow_gateway():
        return None
    text = _clean(raw)
    low = text.lower()
    if low in _READ_ONLY or low.split(" ", 1)[0] in _READ_ONLY:
        return None
    return (
        "  Concierge changes this machine, so it does not run from a shared chat.\n"
        "  Ask the owner, or set plugins.entries.concierge.allow_gateway: true.\n"
    )


def register(ctx: Any) -> None:
    """Wire one slash command, plus the one bare word a shown catalog card accepts."""
    global _CTX, _HOME

    from . import reply

    _CTX = ctx
    try:
        _HOME = Path(str(ctx.home_path)) if getattr(ctx, "home_path", None) else None
    except Exception:
        _HOME = None

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
    "YES",
    "NO",
    "UNDO_WORDS",
    "handle_concierge",
    "handle_hire",
    "handle_undo",
    "register",
]
