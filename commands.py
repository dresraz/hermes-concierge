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

YES = frozenset({"y", "yes", "do it", "ok", "okay", "go", "confirm"})
NO = frozenset({"n", "no", "cancel", "stop", "never mind", "nvm"})
UNDO_WORDS = frozenset({"undo", "revert", "roll back", "rollback", "reverse"})
HELP_WORDS = frozenset({"help", "?", "-h", "--help", "h", "commands"})

CANCEL_WORDS = frozenset({
    "cancel", "stop", "forget it", "never mind", "nevermind", "drop it",
    "same as last time", "do it again", "not now", "abort",
})

HELP_SHORT = (
    "\n"
    "  Concierge\n"
    "  One sentence does the work.\n"
    "\n"
    "  /concierge install obsidian            add a plugin or skill\n"
    "  /concierge create a researcher         make a bot, with skills\n"
    "  /concierge improve coder-bot: always run tests\n"
    "\n"
    "  /concierge browse pdf     look first\n"
    "  /concierge bots           your bots\n"
    "  /concierge undo           take back the last change\n"
    "  /concierge help all       every command\n"
    "\n"
)

HELP = (
    "\n"
    "  CONCIERGE\n"
    "  Bots, plugins and skills, one sentence at a time.\n"
    "\n"
    "  /concierge                     the shelf: what can be added\n"
    "  /concierge browse <word>       look through the shelf\n"
    "  /concierge browse <word> 2     the next page\n"
    "  /concierge <sentence>          install a plugin or skill, this profile\n"
    "  /concierge create <sentence>   make a new bot\n"
    "  /concierge improve <bot>: <what>  add what that bot is missing\n"
    "  /concierge bots                list the bots Concierge made\n"
    "  /concierge skills <bot>        what that bot has installed\n"
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

def _clean(raw: Any) -> str:
    return " ".join(str(raw or "").split())


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


def _is_word_char(char: str) -> bool:
    """A word character for boundary checks, the old \\w without importing it."""
    return char.isalnum() or char == "_"


def _starts_anchored(low: str, prefix: str) -> bool:
    """low starts with prefix on a word boundary, the old ^prefix\\b."""
    return low.startswith(prefix) and (
        len(low) == len(prefix) or not _is_word_char(low[len(prefix)])
    )


def _starts_any(low: str, prefixes: Sequence[str]) -> bool:
    return any(_starts_anchored(low, prefix) for prefix in prefixes)


def _plain_words(low: str, extra: str) -> set:
    """Lowercase letter runs plus extra chars, the old [a-z...]+ findalls."""
    out: set = set()
    buf: list[str] = []
    for char in low:
        if "a" <= char <= "z" or char in extra:
            buf.append(char)
        elif buf:
            out.add("".join(buf))
            buf = []
    if buf:
        out.add("".join(buf))
    return out


def _apostrophe_words(low: str) -> set:
    """The old [a-z']+ tokens: "what's" stays one word."""
    return _plain_words(low, "'")


def _dash_words(low: str) -> set:
    """The old [a-z0-9'-]+ tokens."""
    return _plain_words(low, "0123456789'-")


def _underscore_words(low: str) -> set:
    """The old [a-z0-9_-]+ tokens."""
    return _plain_words(low, "0123456789_-")



_BOTS_PHRASES = (
    tuple(
        head + mid + noun
        for head in ("what", "which", "list", "show")
        for mid in ("", " me", " my", " the", " all",
                    " me my", " me the", " me all")
        for noun in (" bot", " bots")
    )
    + ("my bots",)
    + tuple(
        head + " bots " + tail
        for head in ("what", "how many")
        for tail in ("do i have", "have i got", "are there")
    )
    + ("bots",)
)
_UNDO_PHRASES = (
    "undo", "revert", "roll back", "rollback", "deshaz", "deshacer",
)
_FIRE_PHRASES = (
    "delete", "remove", "fire", "reset", "get rid of", "kill", "drop",
    "uninstall", "borra", "elimina",
)
_BROWSE_PHRASES = (
    tuple(
        head + " " + mid + " i " + tail
        for head in ("what", "which")
        for mid in ("can", "should")
        for tail in ("install", "add", "get")
    )
    + tuple(
        head + mid + " what " + able + " " + tail
        for head in ("show", "list")
        for mid in ("", " me")
        for able in ("i can", "can i")
        for tail in ("install", "add", "get")
    )
    + tuple(
        head + mid + tail
        for head in ("show", "list")
        for mid in ("", " me")
        for tail in (" everything", " the catalog", " the marketplace")
    )
)


def _natural_verb(low: str) -> str:
    """The command a plain sentence is asking for, or "".

    Politeness is stripped first: "please list my bots" is the same sentence as
    "list my bots", and "can you remove the old coder bot" is a fire.
    """
    low = _strip_polite(low)
    if _starts_any(low, _UNDO_PHRASES):
        return "undo"
    if _starts_any(low, _BOTS_PHRASES):
        return "bots"
    if _starts_any(low, _BROWSE_PHRASES):
        return "browse"
    if _starts_any(low, _FIRE_PHRASES):
        return "fire"
    return ""


def _wants_a_bot(text: str) -> bool:
    """True when the sentence asks for a bot, not for a plugin or a skill.

    A bot word next to a role cue is not enough on its own: "a bot that writes
    my taxes" names a writer and asks for nothing, and it must reach the
    marketplace answer ("nothing fits") rather than invent a bot.
    """
    from . import market, presets

    low = " ".join((text or "").lower().split())
    if not low or " into " in low:
        return False
    if market.split_target(text)[1]:
        return False
    role = presets.detect(text)
    if role is None:
        return False
    words = _apostrophe_words(low)
    stripped = _strip_polite(low)
    asking = _asks_create(stripped) or _asks_create(low)
    if words & BOT_WORDS:
        return asking
    return asking


def _asks_for_bot(text: str) -> bool:
    """A bot was asked for, whatever the sentence calls it.

    This is the guard that keeps the worst outcome off the screen: showing an
    install card for a random package when the person asked for a bot.
    """
    from . import market

    low = " ".join((text or "").lower().split())
    if not low or market.split_target(text)[1]:
        return False
    words = _apostrophe_words(low)
    if words & CAPABILITY_WORDS:
        return False
    # "make the house bot shorter" names a bot you already have: that is a
    # change to it, not a request for another one.
    try:
        if any(_has_token_word(low, name) for name in _bot_names()):
            return False
    except Exception:
        pass
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


POLITE = (
    "please ", "can you ", "could you ", "would you ", "will you ",
    "i want to ", "i'd like to ", "i would like to ", "i need to ",
    "i need ", "i want ", "i'd like ", "help me ", "let's ", "lets ",
)
CREATE_ANY = ("hire", "make", "create", "build", "spawn", "set up", "stand up",
              "give me", "get me", "spin up", "start",
              "hazme", "haz", "crea", "crear", "arma", "armar", "monta", "montar")
NEED_ANY = ("need", "want", "looking for", "could use", "necesito", "quiero",
            "kiero", "busco")
SECOND_ANY = ("another", "second one", "one more", "twin", "number 2", "a new")


def _strip_polite(low: str) -> str:
    """Drop the words people put in front of a request."""
    out = low
    changed = True
    while changed:
        changed = False
        for phrase in POLITE:
            if out.startswith(phrase):
                out = out[len(phrase):].lstrip()
                changed = True
    return out


def _has_phrase(low: str, phrases: Sequence[str]) -> bool:
    """A phrase as whole words, the old \\bphrase\\b search."""
    for phrase in phrases:
        if not phrase:
            continue
        start = 0
        while True:
            at = low.find(phrase, start)
            if at < 0:
                break
            end = at + len(phrase)
            left_ok = (at > 0 and _is_word_char(low[at - 1])) != _is_word_char(low[at])
            right_ok = _is_word_char(low[end - 1]) != (end < len(low) and _is_word_char(low[end]))
            if left_ok and right_ok:
                return True
            start = at + 1
    return False


def _has_token_word(haystack: str, needle: str) -> bool:
    """needle as a whole token, where a hyphen joins: the old (?<![\\w-])m(?![\\w-]).

    "reads" is inside "threads" and "pdf" is inside "pdf-skill": neither counts.
    """
    if not needle:
        return False
    start = 0
    while True:
        at = haystack.find(needle, start)
        if at < 0:
            return False
        end = at + len(needle)
        left = haystack[at - 1] if at > 0 else ""
        right = haystack[end] if end < len(haystack) else ""
        if left and (left.isalnum() or left in "_-"):
            start = at + 1
            continue
        if right and (right.isalnum() or right in "_-"):
            start = at + 1
            continue
        return True


def _help_me_job(low: str) -> bool:
    """'help me <word>' where the word is not 'with', the old lookahead."""
    start = 0
    while True:
        at = low.find("help me ", start)
        if at < 0:
            return False
        if at > 0 and _is_word_char(low[at - 1]):
            start = at + 1
            continue
        rest = low[at + len("help me "):]
        if rest.startswith("with") and (
            len(rest) == 4 or not _is_word_char(rest[4])
        ):
            start = at + 1
            continue
        if rest and _is_word_char(rest[0]):
            return True
        start = at + 1


def _asks_create(low: str) -> bool:
    """The sentence asks for a bot in make or need words, anywhere in it."""
    if _has_phrase(low, CREATE_ANY) or _has_phrase(low, NEED_ANY):
        return True
    # "help me keep my inbox at zero" is a job; "help me with excel" is a tool.
    return _help_me_job(low)


def _has_det_name(stripped: str, name: str) -> bool:
    """'my/the/for/to/into <name>' as whole words, the old det + \\s+ + name."""
    for det in ("my", "the", "for", "to", "into"):
        start = 0
        while True:
            at = stripped.find(det, start)
            if at < 0:
                break
            end = at + len(det)
            if at > 0 and _is_word_char(stripped[at - 1]):
                start = at + 1
                continue
            gap = end
            while gap < len(stripped) and stripped[gap].isspace():
                gap += 1
            if gap == end or not stripped.startswith(name, gap):
                start = at + 1
                continue
            stop = gap + len(name)
            if stop < len(stripped) and _is_word_char(stripped[stop]):
                start = at + 1
                continue
            return True
    return False


_LEAD_QUANTIFIERS = ("one more", "another", "a second", "second", "new")


def _trim_leading_quantifier(stripped: str) -> str:
    """Drop one leading 'another'/'a second'/..., the old anchored removal."""
    for word in _LEAD_QUANTIFIERS:
        if stripped.startswith(word):
            tail = stripped[len(word):]
            if tail and tail[0].isspace():
                return tail.lstrip()
    return stripped


def _mine_word(stripped: str) -> str:
    """The word after my/the/our, the old capture group."""
    i, n = 0, len(stripped)
    while i < n:
        for det in ("my", "the", "our"):
            if not stripped.startswith(det, i):
                continue
            if i > 0 and _is_word_char(stripped[i - 1]):
                continue
            gap = i + len(det)
            if gap >= n or not stripped[gap].isspace():
                continue
            while gap < n and stripped[gap].isspace():
                gap += 1
            if gap >= n or not ("a" <= stripped[gap] <= "z" or "0" <= stripped[gap] <= "9"):
                continue
            stop = gap + 1
            while stop < n and (
                "a" <= stripped[stop] <= "z" or "0" <= stripped[stop] <= "9" or stripped[stop] == "-"
            ):
                stop += 1
            return stripped[gap:stop]
        i += 1
    return ""


def _starts_det_name(stripped: str, name: str) -> bool:
    """stripped opens with 'a/an/the <name>', the old anchored article match."""
    for det in ("a", "an", "the"):
        if stripped.startswith(det):
            gap = len(det)
            if gap < len(stripped) and stripped[gap].isspace():
                if stripped[gap:].lstrip().startswith(name):
                    return True
    return False


def _route(text: str) -> tuple:
    """One sentence, one decision.

    The order matters and it is the whole product: a destination beats
    everything, a bot you already have beats a new one, asking for a bot beats
    the marketplace, and the marketplace is the last resort rather than the
    answer to every sentence.
    """
    from . import presets

    if _is_bot_profile():
        return "improve", _self_name(), text

    from . import market

    query, target = market.split_target(text)
    if target:
        return "install", "", text
    low = " ".join((query or "").lower().split())
    if not low:
        return "install", "", text
    words = _dash_words(low)
    stripped = _strip_polite(low)
    names = [name for name in _bot_names() if name != "default"]

    # A bot you already have, aimed at by name. A hyphenated name is a name;
    # a plain word also has to be pointed at ("my intern", "for intern").
    for name in sorted(names, key=len, reverse=True):
        if name not in words:
            continue
        if "-" in name or _has_det_name(stripped, name):
            return "improve", name, query

    second = _has_phrase(stripped, SECOND_ANY)
    role = presets.detect(query)
    if role is None:
        trimmed = _trim_leading_quantifier(stripped)
        if trimmed != stripped:
            role = presets.detect(trimmed)
            if role is None:
                for candidate in presets.names():
                    if candidate in trimmed.split():
                        role = presets.get(candidate)
                        break

    # "my researcher" is the one you have, unless the sentence asks for another.
    # "install a weather plugin for my assistant" is an install, not an improve:
    # the verb says what to do, the possessive only says where it goes.
    install_verb = _has_phrase(stripped, ("install", "add", "enable"))
    capability = bool(words & CAPABILITY_WORDS)
    if install_verb and (capability or role is not None) and ":" not in text:
        return "install", "", text

    # "my coder" and "the coder" both point at the one you have.
    wanted = _mine_word(stripped)
    if wanted and not second:
        if wanted in names or presets.get(wanted) is not None:
            for name in names:
                if name == wanted or name.startswith(wanted + "-"):
                    return "improve", name, query
            return "improve", wanted, query

    bot_word = bool(words & BOT_WORDS)
    # Read the ask from the whole sentence: "I need something that ..." keeps its
    # verb before the politeness words are stripped.
    asking = _asks_create(low) or _asks_create(stripped)
    capability = bool(words & CAPABILITY_WORDS)
    # A bot was asked for: by the word, by a role, or by "something that does X".
    # The marketplace is never the answer to that, even when the sentence also
    # says "skills" or "plugins".
    if second and (bot_word or role is not None or asking):
        return "create", "", query
    if bot_word and asking:
        return "create", "", query
    if role is not None and asking and not capability:
        return "create", "", query
    if role is not None and role.name in words and not capability:
        return "create", "", query
    if role is not None and not capability and not _has_phrase(stripped, ("install", "add", "get")):
        if _starts_det_name(stripped, role.name) or _is_role_bare(stripped, role):
            return "create", "", query
    if role is not None:
        for name in names:
            if name == role.name or name.startswith(role.name + "-"):
                return "improve", name, query
    return "install", "", text


def _is_role_bare(low: str, role: Any) -> bool:
    """"a researcher, please" and "researcher for papers" are bot asks."""
    head = low.rstrip(",!.?").strip()
    return head == role.name or head.startswith(role.name + " ")


def _strip_name(text: str, name: str) -> str:
    """The ask without the bot's name in it."""
    target = (name or "").lower()
    at = -1
    if target:
        low = text.lower()
        start = 0
        while True:
            found = low.find(target, start)
            if found < 0:
                break
            end = found + len(target)
            if (found == 0 or not _is_word_char(low[found - 1])) and (
                end >= len(low) or not _is_word_char(low[end])
            ):
                at = found
                break
            start = found + 1
    out = text[:at] + " " + text[at + len(target):] if at >= 0 else text
    return " ".join(out.split()).strip(" :,-") or text


_SELF = ("yourself", "itself", "your self", "yourself.")

_SELF_VERBS = (
    "improve", "add ", "capable", "capabilities", "capability", "ability",
    "handle", "support", "better at", "able to",
)


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
                "  Deleting a bot needs its number, so nothing is removed by a guess.\n"
                "  /concierge bots, then /concierge fire <number>\n"
            )
        return handle_concierge(
            "{} {}".format(action, selector), store=store, session_key=session_key
        )
    if action == "none":
        from . import card as card_mod

        return card_mod.nothing(text)
    return None


_SPANISH_VERBS = ("mejora", "mejorar", "ensea", "ensña", "entrena")


def _spanish_improve(low: str) -> str:
    """The sentence after mejora/mejorar/ensea/ensña/entrena, or "" when it is not one."""
    for verb in _SPANISH_VERBS:
        if low.startswith(verb):
            tail = low[len(verb):]
            if tail and tail[0].isspace() and tail.lstrip():
                return tail.lstrip()
    return ""


def _into_target(text: str):
    """A trailing 'into <name>', as (name, start), the way the old search read it."""
    low = text.lower()
    start = 0
    while True:
        at = low.find("into", start)
        if at < 0:
            return None
        end = at + len("into")
        if (at == 0 or not _is_word_char(low[at - 1])) and (
            end >= len(low) or not _is_word_char(low[end])
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


def _self_improve(text: str) -> bool:
    """'make yourself able to read pdfs' is about the bot you are talking to."""
    low = " " + " ".join((text or "").lower().split()) + " "
    if not any(word in low for word in _SELF):
        return False
    return any(verb in low for verb in _SELF_VERBS)


def _improve_shape(text: str) -> bool:
    """"<bot>: <what>" is an improve, whatever word came before it."""
    head, sep, rest = (text or "").partition(":")
    if not sep or not rest.strip():
        return False
    if "://" in head:
        return False
    words = _underscore_words(head.lower())
    if words & BOT_WORDS:
        return False
    shape = head.strip().lower()
    if not shape or not ("a" <= shape[0] <= "z" or "0" <= shape[0] <= "9"):
        return False
    return all(
        "a" <= char <= "z" or "0" <= char <= "9" or char in " ._-"
        for char in shape
    )


_WHAT_IN_HEADS = (
    "what installed in", "what is installed in", "what's installed in",
    "what inside", "what is inside", "what's inside",
    "what is in", "what's in", "what in",
)


def _what_is_in(low: str) -> str:
    """The bot after "what's in X", or "" when the sentence is not that shape."""
    for head in _WHAT_IN_HEADS:
        if not low.startswith(head):
            continue
        tail = low[len(head):]
        if not tail or not tail[0].isspace():
            continue
        rest = tail.lstrip()
        for det in ("my", "the"):
            if rest.startswith(det):
                gap = len(det)
                if gap < len(rest) and rest[gap].isspace():
                    rest = rest[gap:].lstrip()
                    break
        name: list[str] = []
        for char in rest:
            if "a" <= char <= "z" or "0" <= char <= "9" or char in "_-":
                name.append(char)
            else:
                break
        if name:
            return "".join(name)
    return ""


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
    if low in CANCEL_WORDS:
        _drop_cards(session_key)
        market.forget(session_key)
        return "  Dropped. Nothing was installed.\n"

    # A card word with no card in front of it is not a search term: "more" was
    # once answered by installing a random plugin.
    bare = "".join(
        char for char in low if "a" <= char <= "z" or "0" <= char <= "9" or char == " "
    ).strip()
    if bare in ("yes", "no", "more", "next", "1", "2") and not (
        card.is_waiting(session_key) or market.is_waiting(session_key)
    ):
        return "  Nothing is waiting. Start with: /concierge install <what you want>\n"
    if low in ("help all", "help -a", "help --all"):
        _drop_cards(session_key)
        return HELP
    if low in HELP_WORDS:
        _drop_cards(session_key)
        return HELP_SHORT
    in_bot = _what_is_in(low)
    if in_bot:
        _drop_cards(session_key)
        return handle_concierge("skills " + in_bot, store=store,
                                session_key=session_key, known=known, hire=hire)

    # The model reads the sentence; the action set is closed and every action
    # runs through the code that already knows how to install, verify and undo.
    routed = _model_route(text, store=store)
    if routed:
        answer = _run_route(routed, text, store=store, session_key=session_key,
                            known=known, hire=hire)
        if answer is not None:
            return answer

    natural = _natural_verb(low)
    if natural == "bots":
        _drop_cards(session_key)
        return _safe_bots(store)
    first_word = low.split(" ", 1)[0]
    if natural == "fire" and first_word not in ("fire", "reset", "delete", "remove", "rm"):
        _drop_cards(session_key)
        return (
            "  Deleting a bot needs its number, so nothing is removed by a guess.\n"
            "  /concierge bots, then /concierge fire <number>\n"
        )
    if natural == "browse":
        from . import shelf

        _drop_cards(session_key)
        return shelf.overview()
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
    if low in UNDO_WORDS or _starts_anchored(low, "undo") or _starts_anchored(low, "roll back") or _starts_anchored(low, "rollback"):
        _drop_cards(session_key)
        return handle_undo(store=store, undo=undo, seams=seams)

    if low.replace(" ", "").isdigit() and len(low.replace(" ", "")) > 4:
        return (
            "  That looks like a number, not a request.\n"
            "  Say what you want in one sentence, like /concierge install obsidian.\n"
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
            return "  One card at a time. /concierge yes takes it, /concierge no drops it.\n"

    if head in ("skills", "show") and _names_a_bot(rest, store):
        from . import improve, lifecycle, state

        if not rest and not _is_bot_profile():
            # No name in the owner's profile: a fleet summary, not 200 lines.
            try:
                made = [lifecycle.name_of(record) for record in lifecycle.bots(store)]
            except Exception:
                return "  The bot list could not be read just now. Nothing was changed.\n"
            if not made:
                return "  No bots yet. Make one: /concierge create a researcher\n"
            lines = ["  Skills per bot", ""]
            for bot in made:
                home = improve.resolve(bot)
                count = len(improve.installed(home)) if home is not None else 0
                lines.append("  {:<26} {}".format(bot, "{} skills".format(count) if count else "none yet"))
            lines.append("")
            lines.append("  One bot in detail: /concierge skills <bot>")
            lines.append("")
            return "\n".join(lines)
        name = rest.split()[0] if rest else _self_name()
        try:
            home = improve.resolve(name)
        except Exception:
            home = None
        if home is None:
            return "  No bot called {}. Say /concierge bots to see them.\n".format(name)
        have = sorted(improve.installed(home))
        if not have:
            return "  {} has no skills of its own yet.\n  Give it one: /concierge improve {}: it needs to read scanned PDFs\n".format(name, name)
        return "  {}\n\n{}".format(
            name,
            "".join("  - {}\n".format(skill) for skill in have),
        )

    if head == "bots":
        _drop_cards(session_key)
        return _safe_bots(store)

    if head in ("fire", "delete", "remove", "rm", "reset"):
        if _is_bot_profile():
            return "  A bot cannot delete or reset profiles. Ask the owner.\n"
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
            return "  {}\n".format(exc)

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

    if _self_improve(text) and not (_asks_for_bot(text) or _wants_a_bot(text)):
        _drop_cards(session_key)
        return handle_improve(
            text, store=store, known=known, bot=_self_name() if _is_bot_profile() else None
        )
    improved = _spanish_improve(low)
    if improved:
        _drop_cards(session_key)
        return handle_improve(improved, store=store, known=known)
    if _improve_shape(text):
        _drop_cards(session_key)
        return handle_improve(text, store=store, known=known)

    intent_name, bot, sentence = _classify(text, store=store)
    # A sentence that plainly asks for a bot is a bot, whatever the model said:
    # a prompt that talks the model into "install" must not override the guard.
    already = (bot or "") in _bot_names()
    if intent_name != "create" and not (intent_name == "improve" and already):
        if _asks_for_bot(text) or _wants_a_bot(text):
            intent_name, bot, sentence = "create", "", text
    _drop_cards(session_key)
    if intent_name == "create":
        return handle_hire(sentence or text, store=store, hire=hire, known=known)
    if intent_name == "improve":
        if not bot:
            return handle_improve(sentence or text, store=store, known=known)
        return handle_improve(_strip_name(sentence, bot), store=store, known=known, bot=bot)
    if intent_name == "bots":
        return _safe_bots(store)
    if intent_name == "browse":
        from . import shelf

        return shelf.overview()
    if intent_name == "help":
        return HELP
    if intent_name == "undo":
        return handle_undo(store=store, undo=undo, seams=seams)
    if intent_name == "none":
        return (
            "  I only take plain requests, not instructions about how to answer.\n"
            "  Say what you want, like /concierge install obsidian.\n"
        )
    if intent_name == "fire":
        return (
            "  Deleting a bot needs its number, so nothing is removed by a guess.\n"
            "  /concierge bots, then /concierge fire <number>\n"
        )

    if _is_bot_profile() and intent_name == "install":
        here = _self_name()
        from . import card as card_mod
        from . import market as market_mod

        _, target = market_mod.split_target(text)
        if target and target != here:
            return "  This bot can only install into itself, not {}.\n".format(target)
        return card_mod.handle(text, session_key=session_key, store=store, target=here)

    # "into <word>" that is not a bot is a typo, not a destination.
    aimed = _into_target(text)
    if aimed:
        aimed_name = aimed[0]
        try:
            from . import seams as _seams

            if not _seams.profile_exists(aimed_name):
                return "  No bot called {}. Say /concierge bots to see them.\n".format(
                    aimed_name
                )
        except Exception:
            pass

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
    def _named(item: Any) -> bool:
        for form in (item.name, item.name.replace("-", " ")):
            if _has_token_word(low, form):
                return True
        return False

    if early is not None and any(_named(item) for item in early.items):
        return improve.receipt(early, improve.apply(early, store=store))

    if _asks_for_bot(text):
        return handle_hire(text, store=store, hire=hire, known=known)

    # One decision point for "install this": handle_install owns the shortlist
    # and the model's pick. A second card.handle here would answer again from a
    # different ranking, which is how two screens could disagree.
    answer = handle_install(text, store=store, session_key=session_key)
    if "Nothing here fits" in answer:
        try:
            from . import seams as _seams

            if _seams.catalog_source() != "marketplace":
                return (
                    "  I could not reach the marketplace just now, so I will not claim\n"
                    "  that nothing exists. Nothing was installed. Try again in a moment.\n"
                )
        except Exception:
            pass
        # A job with no package is still a job: offer the bot instead of dead-ending.
        from . import presets as _presets

        low_text = " ".join(text.lower().split())
        finance = any(
            word in low_text
            for word in ("tax", "taxes", "invoice", "invoices", "bookkeeping",
                         "payroll", "accountant", "accounting", "vat", "irs",
                         "impuestos", "factura", "contabilidad")
        )
        role = _presets.detect(text)
        named = role is not None and role.name in low_text.split()
        if finance:
            subject = "an analyst for this (it can build the workbook)"
            answer += (
                "  Tax and invoicing tools are country-specific: say which country\n"
                "  and I will look for one that fits.\n"
            )
        elif named:
            subject = "a {} for this".format(role.name)
        else:
            subject = "a bot that does that"
        if answer.count("Next:") < 1:
            answer += "  Next: /concierge create {}\n".format(subject)
        return answer
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
    if text.lower().startswith("/concierge"):
        text = text[len("/concierge"):].strip()
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
        aimed = _into_target(text)
        try:
            known_destination = bool(aimed and seams.profile_exists(aimed[0]))
        except Exception:
            known_destination = False
        if aimed and not known_destination:
            return "  No bot called {}. Say /concierge bots to see them.\n".format(aimed[0])
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
        return card.handle(text, entries=catalog, store=store,
                           session_key=session_key, target=target)

    # The matcher builds a shortlist; the model picks from it. A name asked for
    # by name skips the model, so obvious asks stay instant.
    from . import choose

    choice = choose.pick(query, llm=_llm(), entries=catalog)
    if choice is not None:
        caution = getattr(choice, "caution", "")
        if getattr(choice, "kind", "") == "builtin":
            tool = getattr(choice, "description", "") or "its built-in tools"
            return (
                "  Nothing to install: Hermes already does this with {} \n"
                "  No plugin needed, and nothing was added.\n"
                "  If you want a bot that does it for you: /concierge create {}\n"
            ).format(tool, query[:60])
        if getattr(choice, "kind", "") == "skill":
            return market.handle(choice.name, target=target, session_key=session_key,
                                 store=store, search_fn=search, caution=caution)
        return card.handle(choice.name, entries=catalog, store=store,
                           session_key=session_key, target=target, caution=caution)
    if _llm() is None:
        # No model at all: the old two-shelf search still beats a dead end. The
        # caution still has to reach the card, or offline is the one path where a
        # paid memory provider or a GPU-heavy skill installs without a word.
        from . import choose

        rows = choose.shortlist(query, entries=catalog)
        if rows:
            top = rows[0]
            warning = choose.caution_for(top, query)
            if warning and getattr(top, "kind", "") == "skill":
                return market.handle(top.name, target=target, session_key=session_key,
                                     store=store, search_fn=search, caution=warning)
            if warning:
                return card.handle(top.name, entries=catalog, store=store,
                                   session_key=session_key, target=target, caution=warning)
        return market.handle(text, target=target, session_key=session_key,
                             store=store, search_fn=search)
    # Nothing was picked, so nothing is installed. Falling through to a second
    # lexical search here is how a polite "keep my desk tidy" ended up offering
    # a submission ledger: two shots at a wrong answer instead of one honest no.
    answer = card.nothing(query)
    answer += (
        "  If no tool can do it, a bot can try: /concierge create {}\n".format(query[:60])
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
        return "  A bot cannot make other bots. Ask the owner, or improve yourself.\n"

    text = _clean(raw)
    if text.lower().startswith("/concierge"):
        text = text[len("/concierge"):].strip()
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
    key_lines: list[str] = []
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
            []
            if seams.link_self_plugin(path)
            else ["  self     no /concierge in this bot (link failed)"]
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


def _safe_bots(store: Any) -> str:
    """The bot list, or an honest line when the store cannot be read."""
    try:
        from . import lifecycle

        return lifecycle.card(store)
    except Exception:
        return "  The bot list could not be read just now. Nothing was changed.\n"




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
        return ["  skills   preset skipped: {}: {}".format(type(exc).__name__, exc)] + _job_line(
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
            "  /concierge improve researcher-bot: it needs to read scanned PDFs\n"
        )
    bot, sentence = (bot, text) if bot else training.guess_bot(text)
    if _is_bot_profile():
        here = _self_name()
        if (bot or "").lower() in ("me", "myself", "self", "yourself", "itself", "you", "your self", ""):
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


def _llm() -> Any:
    """The plugin's model handle, or None when it is not available."""
    ctx = _CTX
    if ctx is None:
        return None
    try:
        return ctx.llm
    except Exception:
        return None


def _classify(text: str, store: Any = None) -> tuple:
    """What this sentence means: model first, rules when there is no model."""
    from . import intent as intent_mod, presets

    # A sentence that plainly hires or installs is decided by the rules, so the
    # common case costs no network wait at all.
    if _asks_for_bot(text) or _wants_a_bot(text):
        return _route(text)
    llm = None
    if _CTX is not None:
        try:
            llm = _CTX.llm
        except Exception:
            llm = None
    try:
        names = _bot_names()
    except Exception:
        names = ["default"]
    # Each bot carries its job, so "the house bot" resolves to lima-house-seller.
    jobs = {}
    try:
        records = getattr(store, "all", lambda: [])() if store is not None else []
    except Exception:
        records = []
    for record in records:
        if getattr(record, "kind", "") == "bot":
            jobs[record.profile or record.name] = getattr(record, "title", "")
    return intent_mod.classify(
        text,
        llm=llm,
        bots=names,
        roles=presets.names(),
        jobs=jobs,
        fallback=_route,
    )


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
            return "  This bot can only undo its own changes.\n"
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
                "  Nothing to undo. Bots are removed with a sentence of their own:\n"
                "  /concierge bots, then /concierge delete 1\n"
            )
        return "  Nothing to undo.\n"

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
_READ_ONLY = frozenset({"", "help", "?", "h", "commands", "-h", "--help", "bots", "browse", "shelf"})


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
    if low in _READ_ONLY or low.split(" ", 1)[0] in _READ_ONLY:
        return None
    return (
        "  Concierge changes this machine, so it does not run from a shared chat.\n"
        "  Ask the owner, or set plugins.entries.concierge.allow_gateway: true.\n"
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
    "YES",
    "NO",
    "UNDO_WORDS",
    "handle_concierge",
    "handle_hire",
    "handle_undo",
    "register",
]
