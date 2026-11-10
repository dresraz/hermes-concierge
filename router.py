"""What a sentence means, decided by the model instead of a word list.

Regexes answered the phrasings their author happened to imagine. Every miss was
another word added to another list, and the next phrasing missed again. The model
already reads the whole shelf; let it read the sentence too, and hand back one of
a small closed set of actions.

The model never executes anything. It says which action and which target; the
existing code paths install, verify and reverse, with their own guards. When no
model is reachable the caller falls back to the rules, so a provider outage
degrades the wording, not the safety.
"""

from __future__ import annotations

import json
from typing import Any, Optional

ACTIONS = (
    "install",   # one thing from the marketplace
    "improve",   # make an existing bot better: a skill, or one standing rule
    "create",    # a new bot
    "list",      # which bots exist
    "fire",      # remove a bot
    "reset",     # put a bot back to stock
    "undo",      # reverse the last change
    "browse",    # look through what is available
    "help",
    "none",      # nothing in the marketplace does this
)

INSTRUCTIONS = """You decide what a Hermes user is asking for, from one sentence.

Answer with JSON only: {"action": ..., "bot": ..., "what": ...}

action is one of:
  install  one plugin or skill from the marketplace
  improve  make an existing bot better, by adding a skill or writing a standing rule
  create   a new bot (a new assistant with its own name)
  list     which bots exist
  fire     delete a bot
  reset    put a bot back to stock
  undo     reverse the last change
  browse   look through the marketplace
  help     how this works
  none     nothing in the marketplace does this job

bot: the bot's name, exactly as listed. Leave empty for the owner's own profile.
what: the job in the user's own words, short. Keep names the user said.
inside_bot: the name of the bot this message is being sent to, or empty.

Rules:
- "you", "yourself", "me", "your own" mean inside_bot when inside_bot is set.
- Looking and changing are different outcomes, not different verbs. If the user
  wants to SEE what exists, the answer is browse and nothing changes. If they
  want something added or altered, it is install or improve. Judge the outcome
  the sentence asks for; the verb ("search", "find", "get", "add") is a hint,
  never the rule. "search for design skills" is looking. "give me design skills"
  is changing.
- Dialogue with no clear action is "help".
- Asking to add a capability to a bot that is not a marketplace thing is
  "improve" with the capability as "what"; do not answer none just because the
  words are vague.
- A request to change how a bot talks ("always answer in one line") is "improve".
- Creating, deleting or resetting someone else's bot is still that action: the
  code asks for confirmation.
- "none" is only for jobs no plugin or skill could ever do: booking a flight,
  hiring a person, fixing a car.
"""


RESOLVE_PROMPT = """You resolve what a person said to one exact name from a list.

Said: {said}

Candidates:
{candidates}

Handle misspellings ("obsdian" is "obsidian"), spaces vs hyphens ("writer bot"
is "writer-bot"), plurals ("pdfs" is "pdf"), and phrases like "my researcher
bot" or "the notes bot" (return the name itself, not the phrase).

Answer JSON only: {{"name": "<one exact candidate, or empty>"}}
Return "" when nothing on the list fits what was said. Never invent a name:
only a candidate counts."""


def _bot_candidates() -> list:
    """Every profile on this machine, the names a bot reference can mean."""
    try:
        from . import improve

        root = improve.resolve("default")
        if root is not None and (root / "profiles").is_dir():
            names = sorted(
                p.name
                for p in (root / "profiles").iterdir()
                if p.is_dir() and not p.name.startswith(".")
            )
            return ["default"] + names
    except Exception:
        pass
    return []


def _thing_candidates(said: str, limit: int = 200) -> list:
    """Marketplace names worth asking the model about for these words.

    The whole marketplace (about two thousand names) never goes on the call.
    Only names sharing a 3-letter prefix with something said stay, plus every
    exact-ish match, so a typo keeps its target while the list stays small.
    """
    from . import search

    try:
        rows = search.build()
    except Exception:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for row in rows or []:
        if isinstance(row, dict):
            name = str(row.get("name", "") or "")
        else:
            name = str(getattr(row, "name", "") or "")
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    said_words = [word for word in _slug(said or "").split("-") if len(word) >= 3]
    said_flat = "".join(char for char in (said or "").lower() if char.isalnum())
    out: list[str] = []
    for name in names:
        name_words = [word for word in _slug(name).split("-") if len(word) >= 3]
        if any(one[:3] == other[:3] for one in said_words for other in name_words):
            if len(out) < limit:
                out.append(name)
    for name in names:
        flat = "".join(char for char in name.lower() if char.isalnum())
        if not flat or name in out:
            continue
        if flat == said_flat or (
            len(flat) >= 4 and said_flat and (flat in said_flat or said_flat in flat)
        ):
            out.append(name)
    return out


def resolve_name(said: str, kind: str, llm: Any) -> str:
    """One model call mapping what was said to one listed name, or "".

    ``kind`` is "bot" (profiles on this machine) or "thing" (the marketplace
    names that could plausibly match). The model may only choose from that
    list; anything else, and anything unparsable, is "".
    """
    if llm is None:
        return ""
    text = " ".join(str(said or "").split())
    if not text:
        return ""
    if kind == "bot":
        candidates = _bot_candidates()
    elif kind == "thing":
        candidates = _thing_candidates(text)
    else:
        return ""
    if not candidates:
        return ""
    prompt = RESOLVE_PROMPT.format(
        said=text, candidates="\n".join("- {}".format(name) for name in candidates)
    )
    try:
        answer = llm.complete_structured(
            instructions=prompt,
            input=[{"type": "text", "text": text}],
            json_mode=True,
            max_tokens=60,
            temperature=0,
            timeout=15,
        )
    except Exception:
        return ""
    raw = (getattr(answer, "text", "") or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return ""
    try:
        data = json.loads(raw[start : end + 1])
    except Exception:
        return ""
    heard = str(data.get("name") or "").strip()
    if not heard:
        return ""
    real = {name.lower(): name for name in candidates}
    return real.get(heard.lower(), "")


def _slug(text: str) -> str:
    """Profile-safe form: 'Writer Bot!' reads as 'writer-bot'."""
    out: list[str] = []
    token: list[str] = []
    for char in (text or "").lower():
        if char.isalnum():
            token.append(char)
        elif token:
            out.append("".join(token))
            token = []
    if token:
        out.append("".join(token))
    return "-".join(out)


def route(text: str, *, here: str, bots: list, llm: Any) -> Optional[dict]:
    """One call, one action. None when the model cannot answer."""
    if llm is None:
        return None
    context = "bots: {}\ninside_bot: {}".format(", ".join(bots) or "none", here or "")
    try:
        answer = llm.complete_structured(
            instructions=INSTRUCTIONS + "\n" + context,
            input=[{"type": "text", "text": text}],
            json_mode=True,
            max_tokens=120,
            temperature=0,
            timeout=30,
        )
    except Exception:
        return None
    raw = (getattr(answer, "text", "") or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except Exception:
        return None
    action = str(data.get("action") or "").strip().lower()
    if action not in ACTIONS:
        return None
    bot = str(data.get("bot") or "").strip()
    if bot:
        # A spoken name uses spaces where the profile uses hyphens:
        # "writer bot" is "writer-bot". Normalize before validating.
        norm = _slug(bot)
        real = { _slug(name): name for name in bots }
        if norm in real:
            bot = real[norm]
    if bot and bot.lower() not in {name.lower() for name in bots}:
        # A name the user typed is fine; a hallucinated one is not.
        # Compare spoken forms too, so "writer bot" in the sentence keeps it.
        if bot.lower() not in text.lower() and _slug(bot) not in _slug(text):
            bot = ""
    return {"action": action, "bot": bot, "what": str(data.get("what") or "").strip()}
