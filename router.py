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
  install  one plugin, skill or connector from the marketplace
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
- Words that ask to LOOK are browse, never improve: "show me", "look for",
  "search for", "search", "look up", "look at", "what can", "which skills", "what are my options", "is there
  anything that", "find me", "anything for you". "look for X for you" is still a
  look: only an explicit install/add/give/teach changes a bot.
  Browse changes nothing; improve changes a bot.
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
    raw = (getattr(answer, "text") or "").strip()
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
    if bot and bot.lower() not in {name.lower() for name in bots}:
        # A name the user typed is fine; a hallucinated one is not.
        if bot.lower() not in text.lower():
            bot = ""
    return {"action": action, "bot": bot, "what": str(data.get("what") or "").strip()}
