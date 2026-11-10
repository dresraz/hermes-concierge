"""One model call. It returns everything the code needs.

The model does not execute anything. It reads the sentence plus the real data
(bot names, preset roles, candidate marketplace names, the pending offer) and
returns one plan. The code only executes a plan whose names come from those
lists. With no model, there is no plan.
"""

from __future__ import annotations

import json
from typing import Any, Optional

ACTIONS = (
    "install",
    "improve",
    "create",
    "list",
    "fire",
    "reset",
    "undo",
    "browse",
    "help",
    "none",
)

OUTCOMES = ("CONFIRM", "DROP", "OTHER")


def _prompt(sentence: str, *, bots: list, roles: str, candidates: list, pending: str) -> str:
    lines = [
        "You decide what a Hermes user wants, from one sentence.",
        'Answer with JSON only: {"action": ..., "bot": ..., "thing": ..., "role": ..., "answer": ..., "what": ...}',
        "",
        "action is one of: install, improve, create, list, fire, reset, undo, browse, help, none.",
        "bot is a bot name from the list below, or empty.",
        "thing is one marketplace name from the candidate list below, or empty.",
        "Each candidate line is \"name -- what it does\". Answer with the exact name only.",
        "role is one preset role name from the list below, or empty.",
        "answer is CONFIRM when the user accepts the pending offer, DROP when they refuse it, OTHER otherwise.",
        "what is the job in the user's own words, short.",
        "",
        "Rules:",
        "- Looking changes nothing, changing adds or alters. Judge the outcome the sentence asks for.",
        "- A typo is still the thing: obsdian means obsidian when obsidian is listed.",
        "- A spoken name is still the name: writer bot means writer-bot when listed.",
        "- Only return names that appear in the lists below. Never invent one.",
        "- none is only for jobs no plugin or skill could ever do.",
        "",
        "bots:",
        ", ".join(bots) if bots else "none yet",
        "",
        "preset roles:",
        roles,
        "",
        "candidate marketplace entries, one per line:",
        "\n".join(candidates[:200]) if candidates else "none",
    ]
    if pending:
        lines += ["", "pending offer:", pending]
    lines += ["", "sentence:", sentence]
    return "\n".join(lines)


def route(sentence: str, *, bots: list, llm: Any, pending: str = "") -> Optional[dict]:
    if llm is None:
        return None
    try:
        from . import presets as presets_mod
        from . import search as search_mod

        candidates = search_mod.names_for_model(sentence)
        instructions = _prompt(
            sentence,
            bots=bots or [],
            roles=presets_mod.blurbs(),
            candidates=candidates,
            pending=pending or "",
        )
        answer = llm.complete_structured(
            instructions=instructions,
            input=[{"type": "text", "text": sentence}],
            json_mode=True,
            max_tokens=200,
            temperature=0,
            timeout=45,
        )
    except Exception:
        return None
    raw = getattr(answer, "text", "") or ""
    if not isinstance(raw, str):
        return None
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except Exception:
        return None
    action = str(data.get("action") or "").strip().lower()
    if action not in ACTIONS:
        return None
    bot = str(data.get("bot") or "").strip()
    thing = str(data.get("thing") or "").strip()
    role = str(data.get("role") or "").strip()
    answer = str(data.get("answer") or "OTHER").strip().upper()
    if answer not in OUTCOMES:
        answer = "OTHER"
    return {
        "action": action,
        "bot": bot,
        "thing": thing,
        "role": role,
        "answer": answer,
        "what": str(data.get("what") or "").strip(),
    }
