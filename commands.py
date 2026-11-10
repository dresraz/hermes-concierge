"""The whole surface behind one command.

Free text always reaches the model. The model returns one plan and the code
below only executes it. Nothing here matches words to decide intent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

_CTX: Any = None
_PENDING: dict = {}
_ROWS: dict = {}
_ROWS_AT: dict = {}
_ROWS_TTL = 600.0

import re as _re

# Small head-word patterns only, all anchored at the start. They never scan
# the middle of a sentence, so "box" inside "inbox" cannot match. Each one
# maps to a single literal command; anything odd falls through to the model.
_SEARCH_RX = _re.compile(r"^(?:search(?:ing)?|find|look\s+for|lookup)\b\s*(.*)$")
_UNDO_RX = _re.compile(r"^(?:undo|revert|take\s+(?:that|it)\s+back)\s*$")
_BOTS_RX = _re.compile(r"^(?:bots|list(?:\s+bots)?|my\s+bots|show\s+(?:my\s+)?bots)\s*$")
_INSTALL_RX = _re.compile(r"^install\s+(.+)$")
_YES_RX = _re.compile(r"^(?:yes|yeah|yep|y|sure|ok|okay)\s*$")
_NO_RX = _re.compile(r"^(?:no|nope|nah|n|cancel)\s*$")


def _llm() -> Any:
    try:
        return _CTX.llm if _CTX is not None else None
    except Exception:
        return None


def _current_profile() -> str:
    try:
        from hermes_constants import get_hermes_home

        home = Path(str(get_hermes_home()))
        if home.parent.name == "profiles":
            return home.name
        return "default"
    except Exception:
        return "default"


def _is_bot_profile() -> bool:
    try:
        from hermes_constants import get_hermes_home

        home = Path(str(get_hermes_home()))
        return home.parent.name == "profiles"
    except Exception:
        return False


def _allow_gateway() -> bool:
    try:
        cfg = getattr(_CTX, "config", None)
        if isinstance(cfg, dict):
            value = cfg.get("plugins", {}).get("entries", {}).get("concierge", {}).get("allow_gateway")
            if value is True:
                return True
    except Exception:
        pass
    try:
        from hermes_cli.config_effective import load_user_config_effective

        cfg = load_user_config_effective()
        if isinstance(cfg, dict):
            return bool(cfg.get("plugins", {}).get("entries", {}).get("concierge", {}).get("allow_gateway") is True)
    except Exception:
        return False
    return False


# The surfaces the owner is sitting at. Everything else, including a surface we
# have never heard of, counts as a shared chat: the safe side of this gate is
# "do not change the machine from someone else's chat".
_LOCAL_SURFACES = frozenset({"cli", "tui", "desktop", "acp"})


def _messaging(platform: str = "") -> bool:
    """Is this a shared chat?

    A platform named by the caller decides on its own: the admission hook is told
    where the message came from, and that answer does not depend on session
    variables a worker may have stripped. With no platform, core's own answer
    stands, and an unknown answer counts as a shared chat.
    """
    named = (platform or "").strip().lower()
    if named:
        return named not in _LOCAL_SURFACES
    try:
        from gateway.session_context import session_is_messaging_surface

        return bool(session_is_messaging_surface())
    except Exception:
        return True


def _refusal(platform: str = "") -> Optional[str]:
    if _messaging(platform) and not _allow_gateway():
        return "Concierge changes this machine, so it does not run from a shared chat.\nAsk the owner, or set plugins.entries.concierge.allow_gateway to true.\n"
    return None


def _version() -> str:
    try:
        import subprocess

        here = Path(__file__).resolve().parent
        sha = subprocess.run(
            ["git", "-C", str(here), "rev-parse", "--short=7", "HEAD"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        return "0.9.3 " + sha if sha else "0.9.3"
    except Exception:
        return "0.9.3"


HELP = (
    "Concierge\n"
    "One sentence does the work.\n"
    "\n"
    "/concierge install obsidian adds a plugin or skill.\n"
    "/concierge create a researcher makes a bot, with skills.\n"
    "/concierge improve coder-bot: always run tests.\n"
    "\n"
    "/concierge browse pdf looks first.\n"
    "/concierge search maps looks first, another word for browse.\n"
    "/concierge bots shows your bots.\n"
    "/concierge undo takes back the last change.\n"
    "/concierge fire coder-bot deletes a bot, with confirmation.\n"
    "/concierge help all shows every command.\n"
)

HELP_ALL = HELP + (
    "\n"
    "install, create, improve, browse, bots, fire, reset, undo, help.\n"
    "Inside a bot, it only changes that bot.\n"
)


def _overview() -> str:
    from . import store as store_mod
    from . import search as search_mod

    bots = store_mod.bot_names()
    try:
        skills_count, plugins_count, connectors_count = search_mod.counts()
    except Exception:
        skills_count, plugins_count, connectors_count = (0, 0, 0)
    lines = ["Concierge", ""]
    if bots:
        noun = "bot" if len(bots) == 1 else "bots"
        lines.append("{} {}: {}.".format(len(bots), noun, ", ".join(bots)))
    else:
        lines.append("No bots yet. Make one: /concierge create a researcher")
    skills_noun = "skill" if skills_count == 1 else "skills"
    plugins_noun = "plugin" if plugins_count == 1 else "plugins"
    connectors_noun = "connector" if connectors_count == 1 else "connectors"
    lines.append("On the shelf: {} {}, {} {} and {} {}.".format(
        skills_count, skills_noun, plugins_count, plugins_noun, connectors_count, connectors_noun))
    lines.append("Lists refresh daily from the marketplace.")
    lines.append("")
    lines.append("Version {}.".format(_version()))
    lines.append("")
    lines.append("Say what you need in one sentence, or look first:")
    lines.append("/concierge browse pdf looks through what is available.")
    lines.append("/concierge help lists the commands.")
    return "\n".join(lines) + "\n"


def _bot_names() -> list:
    from . import store as store_mod

    return store_mod.bot_names()


def handle_concierge(raw: Any, **kwargs: Any) -> str:
    from . import router as router_mod

    session_key = str(kwargs.get("session_key", "") or "")
    refusal = _refusal()
    if refusal:
        return refusal
    text = " ".join(str(raw or "").split()).strip()
    if text.lower().startswith("/concierge"):
        text = text[len("/concierge"):].strip()
    low = text.lower()
    if not text:
        return _overview()
    if low in ("help", "help all", "help -a"):
        _PENDING.pop(session_key, None)
        return HELP_ALL if low in ("help all", "help -a") else HELP
    if low == "undo" or _UNDO_RX.match(low):
        _PENDING.pop(session_key, None)
        return _do_undo()
    if low in ("bots", "list") or _BOTS_RX.match(low):
        _PENDING.pop(session_key, None)
        names = _bot_names()
        if not names:
            return "No bots yet. Make one: /concierge create a researcher\n"
        noun = "bot" if len(names) == 1 else "bots"
        return "{} {}: {}.\n".format(len(names), noun, ", ".join(names))
    if low == "browse" or low.startswith("browse "):
        _PENDING.pop(session_key, None)
        return _do_browse(text[6:].strip(), session_key)
    if low == "install":
        _PENDING.pop(session_key, None)
        return "Install what? For example: /concierge install obsidian\n"
    search_hit = _SEARCH_RX.match(low)
    if search_hit:
        _PENDING.pop(session_key, None)
        return _do_browse(search_hit.group(1).strip(), session_key)
    install_hit = _INSTALL_RX.match(low)
    if install_hit:
        _PENDING.pop(session_key, None)
        target = _current_profile() if _is_bot_profile() else ""
        return _do_install(install_hit.group(1).strip(), target=target)
    stripped = text.strip()
    if stripped.isascii() and stripped.isdigit() and len(stripped) <= 4:
        import time as _time

        try:
            fresh = (_time.time() - _ROWS_AT.get(session_key, 0.0)) < _ROWS_TTL
        except Exception:
            fresh = False
        if _ROWS.get(session_key) and fresh:
            return _pick_row(session_key, int(stripped))
        _ROWS.pop(session_key, None)
        _ROWS_AT.pop(session_key, None)
        pending = _PENDING.get(session_key) or {}
        if pending.get("key", "").startswith("fire:") and pending.get("confirmed"):
            bot = pending.get("bot", "")
            try:
                names = _bot_names()
                expected = names.index(bot) + 1
            except Exception:
                expected = -1
            if int(stripped) == expected:
                return _do_fire_or_reset("fire", bot, "", session_key, "CONFIRM")
            return "That deletes {}. Reply yes to delete it, or no to keep it.\n".format(bot or "that bot")
        return "Say the job in one sentence: /concierge something that reads my pdfs.\n"
    pending = _PENDING.get(session_key) or {}
    if pending.get("key", "").startswith("fire:"):
        if _YES_RX.match(low):
            return _do_fire_or_reset("fire", pending.get("bot", ""), "", session_key, "CONFIRM")
        if _NO_RX.match(low):
            _PENDING.pop(session_key, None)
            return "Nothing deleted. {} is still here.\n".format(pending.get("bot", "it"))
    if low == "no":
        _PENDING.pop(session_key, None)
        return "Nothing is waiting for an answer. Say the job: /concierge something that reads my pdfs.\n"
    pending_summary = ""
    try:
        pending_summary = (_PENDING.get(session_key) or {}).get("summary", "")
    except Exception:
        pending_summary = ""
    plan = router_mod.route(text, bots=_bot_names(), llm=_llm(), pending=pending_summary)
    if plan is None:
        if _llm() is None:
            return "I need a model to read that. Without one I can still: /concierge bots, /concierge browse <word>, /concierge search <word>, /concierge install <name>, /concierge undo.\n"
        return "Could not read that just now. Try again, or name the thing: /concierge install <name>.\n"
    return _run_plan(plan, text, session_key=session_key)


def _run_plan(plan: dict, text: str, *, session_key: str) -> str:
    from . import search as search_mod
    from . import store as store_mod

    action = plan.get("action", "")
    answer = str(plan.get("answer") or "OTHER").strip().upper()
    if action not in ("fire", "reset"):
        _PENDING.pop(session_key, None)
    if action == "help":
        return HELP
    if action == "list":
        bots = _bot_names()
        if not bots:
            return "No bots yet. Make one: /concierge create a researcher\n"
        noun = "bot" if len(bots) == 1 else "bots"
        return "{} {}: {}.\n".format(len(bots), noun, ", ".join(bots))
    if action == "undo":
        return _do_undo()
    if action == "browse":
        return _do_browse(plan.get("what") or text, session_key)
    if action == "none":
        return "Nothing here fits \"{}\". Try different words, or run /concierge help.\n".format(text[:80])
    if action == "install":
        bot = (plan.get("bot") or "").strip()
        if _is_bot_profile():
            here = _current_profile()
            if bot and bot.lower() not in ("default", "main", "custom") and bot.lower() != here.lower():
                return "A bot can only change itself. Switch to your main chat to change anything else.\n"
            target = here
        elif not bot:
            target = ""
        elif bot.lower() in ("default", "main", "custom"):
            target = ""
        else:
            canon = next((n for n in _bot_names() if n.lower() == bot.lower()), "")
            if not canon:
                return "No bot called {}. Say /concierge bots to see them.\n".format(bot)
            target = canon
        return _do_install(plan.get("thing") or plan.get("what") or text, target=target)
    if action == "improve":
        return _do_improve(plan.get("bot") or "", plan.get("thing") or "", plan.get("what") or "")
    if action == "create":
        return _do_create(plan.get("role") or "", plan.get("what") or text)
    if action in ("fire", "reset"):
        return _do_fire_or_reset(action, plan.get("bot") or "", plan.get("what") or text, session_key, answer)
    return "I need a model to read that. Without one I can still: /concierge bots, /concierge browse <word>, /concierge search <word>, /concierge install <name>, /concierge undo.\n"


def _canonical_thing(name: str) -> tuple:
    """The marketplace's own spelling of a name, plus which shelf holds it.

    Only plain names pass: anything shaped like a path, a flag, or a glob
    is not a marketplace entry. A trailing " -- description" (as the model
    sometimes echoes the menu) is stripped first.
    """
    from . import search as search_mod

    raw = (name or "").strip()
    for sep in ("--", "(", ":"):
        if sep in raw:
            raw = raw.split(sep, 1)[0]
    raw = raw.strip().strip("\"'")
    if not raw or len(raw) > 100 or raw.startswith("-") or "/" in raw or raw.startswith("."):
        return ("", False, False)
    import string as _string

    allowed = set(_string.ascii_letters + _string.digits + " _-.")
    if any(ch not in allowed for ch in raw):
        return ("", False, False)
    lowered = "".join(ch for ch in raw.lower() if ch.isalnum())
    if not lowered:
        return ("", False, False)
    for row in search_mod.skills():
        flat = "".join(ch for ch in str(row.get("name", "")).lower() if ch.isalnum())
        if flat and flat == lowered:
            return (str(row.get("name", "")), True, False)
    for row in search_mod.plugins():
        flat = "".join(ch for ch in str(row.get("name", "")).lower() if ch.isalnum())
        if flat and flat == lowered:
            return (str(row.get("name", "")), False, True)
    return ("", False, False)


def _do_browse(query: str, session_key: str) -> str:
    from . import search as search_mod

    import time as _time

    if not (query or "").strip():
        return "Look through what? Say /concierge browse pdf.\n"
    rows = search_mod.candidates(query, limit=10)
    if not rows:
        return "Nothing here fits \"{}\". Try different words, or run /concierge help.\n".format(query[:80])
    _ROWS[session_key] = rows
    _ROWS_AT[session_key] = _time.time()
    lines = []
    for index, row in enumerate(rows, start=1):
        if row.get("kind") == "connector":
            desc = (row.get("description", "") or "").strip()[:80]
            if desc:
                lines.append("{}. {} (connector): {}".format(index, row["name"], desc))
            else:
                lines.append("{}. {} (connector: connect it in chat settings, nothing to install)".format(index, row["name"]))
            continue
        desc = (row.get("description", "") or "").strip()[:80] or "chat connector"
        lines.append("{}. {} ({}): {}".format(index, row["name"], row.get("kind", "skill"), desc))
    lines.append("")
    lines.append("Reply with a number to install it, or say the job in one sentence.")
    return "\n".join(lines) + "\n"


def _pick_row(session_key: str, number: int) -> str:
    rows = _ROWS.get(session_key) or []
    if number < 1 or number > len(rows):
        return "Say the job in one sentence: /concierge something that reads my pdfs.\n"
    row = rows[number - 1]
    _ROWS.pop(session_key, None)
    _ROWS_AT.pop(session_key, None)
    if row.get("kind") == "connector":
        return "That one is a connector, not a skill or plugin. Connect it in chat settings; there is nothing to install here. Nothing was changed.\n"
    target = _current_profile() if _is_bot_profile() else ""
    return _do_install(row["name"], target=target)


def _do_install(name: str, *, target: str) -> str:
    from . import search as search_mod
    from . import store as store_mod

    clean = " ".join(str(name or "").split()).strip()
    if not clean:
        return "Install what? For example: /concierge install obsidian\n"
    low_target = (target or "").strip().lower()
    if low_target and low_target not in ("default", "main", "custom"):
        canon = next((n for n in _bot_names() if n.lower() == low_target), "")
        if not canon:
            return "No bot called {}. Say /concierge bots to see them.\n".format(target)
        target = canon
    elif low_target in ("default", "main", "custom"):
        target = low_target
    skill_names = {row["name"].lower() for row in search_mod.skills()}
    plugin_names = {row["name"].lower() for row in search_mod.plugins()}
    connector_names = {row["name"].lower() for row in search_mod.connectors()}
    lowered = clean.lower()
    if lowered in connector_names and lowered not in skill_names and lowered not in plugin_names:
        return "That one is a connector, so there is nothing to install here. Nothing was changed.\n"
    canon, is_skill, is_plugin = _canonical_thing(clean)
    if canon:
        clean = canon
    if not is_skill and not is_plugin:
        return "Nothing here fits \"{}\". Try different words, or run /concierge help.\n".format(clean[:80])
    if is_skill:
        home = store_mod.home() if not target else store_mod.profile_dir(target)
        try:
            already = store_mod.find_skill_dir(home, clean)
        except Exception:
            already = ""
        if already:
            store_mod.push({"kind": "skill", "name": clean, "paths": [], "profile": target or "default"})
            where = " in {}".format(target) if target else ""
            return "{} is already here{}. Nothing changed.\nSee what else does that job: /concierge browse {}\n".format(clean, where, clean.split()[0][:40])
        try:
            ok, folder, _out = store_mod.install_skill(clean, profile=target)
        except Exception:
            return "Not installed: {} did not install. Nothing was kept. Try /concierge browse {} to check the name.\n".format(clean, clean.split()[0][:40])
        if not ok or not folder:
            return "Not installed: {} did not install. Nothing was kept. Try /concierge browse {} to check the name.\n".format(clean, clean.split()[0][:40])
        saved = bool(store_mod.push({"kind": "skill", "name": clean, "paths": [folder], "profile": target or "default"}))
        lines = ["Installed skill {}".format(clean), "It is at {}.".format(folder)]
        if clean.lower() in plugin_names:
            lines.append("A plugin shares this name; installed the skill.")
        if target:
            lines.append("It goes into {}.".format(target))
        else:
            lines.append("It goes into default.")
        lines.append(_undo_line(saved))
        return "\n".join(lines) + "\n"
    try:
        ok, folder, _out = store_mod.install_plugin(clean, profile=target)
    except Exception:
        return "Not installed: {} did not install. Nothing was kept. Try /concierge browse {} to check the name.\n".format(clean, clean.split()[0][:40])
    if not ok:
        return "Not installed: {} did not install. Nothing was kept. Try /concierge browse {} to check the name.\n".format(clean, clean.split()[0][:40])
    saved = bool(store_mod.push({"kind": "plugin", "name": clean, "paths": [folder] if folder else [], "profile": target or "default"}))
    lines = ["Installed {}".format(clean)]
    if folder:
        lines.append("It is at {}.".format(folder))
    else:
        lines.append("The files are there.")
    if target:
        lines.append("It is enabled. It goes into {}.".format(target))
    else:
        lines.append("It is enabled. It goes into default.")
    lines.append(_undo_line(saved))
    return "\n".join(lines) + "\n"


def _do_improve(bot: str, thing: str, what: str) -> str:
    from . import store as store_mod

    here = _current_profile() if _is_bot_profile() else ""
    target = bot or here
    if _is_bot_profile() and target != here:
        return "A bot can only change itself. Switch to your main chat to change anything else.\n"
    if not target:
        names = _bot_names()
        if not names:
            return "No bots yet. Make one: /concierge create a researcher\n"
        return "Improve which bot? For example: /concierge improve {}: it needs to read PDFs\n".format(names[0])
    if target.lower() not in ("default", "main", "custom"):
        canon = next((n for n in _bot_names() if n.lower() == target.lower()), "")
        if not canon and not (_is_bot_profile() and target == here):
            return "No bot called {}. Say /concierge bots to see them.\n".format(target)
        target = canon or target
    if not (what or "").strip() and not (thing or "").strip():
        return "Improve {} how? For example: /concierge improve {}: it needs to read PDFs\n".format(target, target)
    what = " ".join(str(what or "").split())
    if len(what) > 300:
        what = what[:300]
    if thing:
        canon_thing, is_skill, is_plugin = _canonical_thing(thing)
        if not is_skill:
            if is_plugin:
                return "{} is a plugin, not a bot skill. Install it with: /concierge install {}\n".format(thing, canon_thing or thing)
            return "Nothing here fits \"{}\". Try different words, or run /concierge help.\n".format(thing[:80])
        thing = canon_thing
        try:
            ok, folder, _out = store_mod.install_skill(thing, profile="" if target.lower() in ("default", "main", "custom") else target)
        except Exception:
            ok, folder = False, ""
        if not ok or not folder:
            return "Not installed: {} did not install into {}. Nothing was kept. Try /concierge browse {} to check the name.\n".format(thing, target, thing.split()[0][:40] if thing.split() else thing)
        saved = bool(store_mod.push({"kind": "skill", "name": thing, "paths": [folder], "profile": target}))
        return "Improved {}.\nInstalled skill {}.\n{}\n".format(target, thing, _undo_line(saved))
    try:
        base = store_mod.home() if target.lower() in ("default", "main", "custom") else store_mod.profile_dir(target)
        soul = base / "SOUL.md"
        existed = soul.exists()
    except Exception:
        soul = Path(str(store_mod.home() / "SOUL.md"))
        existed = False
    ok, backup, note = store_mod.add_rule(target, what)
    if note == "duplicate":
        return "{} already has that rule. Nothing changed.\n".format(target)
    if not ok:
        return "{}\n".format(note or "Nothing changed.")
    saved = bool(store_mod.push({"kind": "rule", "name": target, "paths": [], "profile": target,
                    "soul_path": str(soul), "soul_backup": backup or "", "soul_existed": existed}))
    return "Improved {}.\nRule added: {}.\n{}\n".format(target, what[:120], _undo_line(saved))


def _do_create(role: str, what: str) -> str:
    from . import presets as presets_mod
    from . import store as store_mod

    if _is_bot_profile():
        return "Bots can't create other bots. Switch to your main chat to make one.\n"
    picked = (role or "").strip().lower()
    if picked not in presets_mod.ROLES:
        picked = ""
    if not picked:
        return "What kind of bot? For example: /concierge create a researcher\n"
    name = picked + "-bot"
    taken = set(_bot_names()) | {"default", "main", "custom"}
    if name in taken:
        suffix = 2
        candidate = "{}-{}-bot".format(picked, suffix)
        while candidate in taken:
            suffix += 1
            candidate = "{}-{}-bot".format(picked, suffix)
        name = candidate
    skills = presets_mod.skills_for(picked)
    code, out, done, failed = store_mod.create_bot(name, skills)
    if not code:
        return "Could not create {}. Nothing was kept. Try again, or run /concierge help.\n".format(name)
    saved = bool(store_mod.push({"kind": "bot", "name": name, "paths": [str(store_mod.profile_dir(name))],
                    "profile": name, "role": picked}))
    lines = ["Created {}.".format(name), "{} of {} skills installed.".format(done, len(skills))]
    if failed:
        lines.append("Missing: {}. Add one later: /concierge improve {}: add {}.".format(
            ", ".join(failed[:3]), name, failed[0]))
    lines.append("Give it API access: hermes -p {} auth add <provider>.".format(name))
    lines.append(_undo_line(saved))
    return "\n".join(lines) + "\n"


def _do_fire_or_reset(action: str, bot: str, what: str, session_key: str, answer: str = "OTHER") -> str:
    from . import store as store_mod

    names = _bot_names()
    picked = ""
    for name in names:
        if name.lower() == (bot or "").strip().lower():
            picked = name
            break
    if not picked:
        stripped = (what or "").strip().rstrip(".")
        if stripped.isascii() and stripped.isdigit() and len(stripped) <= 4:
            index = int(stripped)
            if 1 <= index <= len(names):
                picked = names[index - 1]
    if not picked:
        return "Concierge did not create that, so it will not delete it. Delete it with: hermes profile delete <name>.\n"
    if not store_mod.has_bot_record(picked):
        return "Concierge did not create {}, so it will not delete it. Delete it with: `hermes profile delete {}`.\n".format(picked, picked)
    if action == "reset":
        _PENDING.pop(session_key, None)
        return _do_reset(picked)
    key = "fire:{}".format(picked)
    pending = _PENDING.get(session_key) or {}
    if pending.get("key") == key and pending.get("confirmed"):
        if answer == "DROP":
            _PENDING.pop(session_key, None)
            return "Nothing deleted. {} is still here.\n".format(picked)
        if not store_mod.has_bot_record(picked):
            _PENDING.pop(session_key, None)
            return "Concierge did not create {}, so it will not delete it. Say /concierge bots to see them.\n".format(picked)
        _PENDING.pop(session_key, None)
        code, _out = store_mod.delete_bot(picked)
        if code != 0:
            return "Could not delete {}. Nothing was removed. Delete it with: `hermes profile delete {}`.\n".format(picked, picked)
        return "Deleted {}.\n".format(picked)
    _PENDING[session_key] = {"key": key, "summary": "delete {}".format(picked), "bot": picked, "confirmed": True}
    _ROWS.pop(session_key, None)
    _ROWS_AT.pop(session_key, None)
    return "Deleting a bot removes it for good.\nTo delete {}, reply yes, or 1, or: /concierge fire {} {}\n".format(picked, names.index(picked) + 1, picked)


def _do_reset(bot: str) -> str:
    from . import presets as presets_mod
    from . import store as store_mod

    return "Reset: {} keeps what it has. Fire it and create it again to start over.\n".format(bot)


def _safe_soul_file(path: str, backup: bool = False, scope=None) -> bool:
    """A soul file Concierge may touch: SOUL.md inside the record's own home."""
    try:
        from . import store as store_mod

        resolved = Path(path).resolve()
        root = store_mod.home().resolve()
        if scope is None:
            scope = root
        else:
            scope = Path(scope).resolve()
            if scope != root and root not in scope.parents:
                return False
        if resolved.parent != scope:
            return False
        try:
            if resolved.exists() and resolved.stat().st_nlink != 1:
                return False
        except Exception:
            return False
        if backup:
            return resolved.name.startswith("SOUL.md.") and resolved.name.endswith(".concierge-backup")
        return resolved.name == "SOUL.md"
    except Exception:
        return False


def _undo_line(saved: bool) -> str:
    if saved:
        return "Undo with /concierge undo."
    return "The undo receipt could not be saved, so /concierge undo may not reverse this."


def _do_undo() -> str:
    from . import store as store_mod

    dropped = 0
    record = None
    for _ in range(10):
        candidate = store_mod.pop()
        if candidate is None:
            break
        if isinstance(candidate, dict):
            record = candidate
            break
        dropped += 1
    if record is None:
        if dropped:
            return "Cleared an unreadable receipt. Say the job: /concierge something that reads my pdfs.\n"
        return "Nothing to undo. Say the job: /concierge something that reads my pdfs.\n"
    kind = record.get("kind", "")
    if kind == "skill" and not (record.get("paths", []) or []):
        return "Nothing to undo. {} is unchanged.\n".format(record.get("name", ""))
    if kind == "bot":
        name = record.get("name", "")
        if not isinstance(name, str) or not name.strip() or name.strip().lower() in ("default", "main", "custom"):
            return "Concierge did not create {}, so it will not delete it. Say /concierge bots to see them.\n".format(name if isinstance(name, str) and name else "that")
        try:
            still_there = store_mod.profile_dir(name).exists()
        except Exception:
            still_there = False
        if not still_there:
            return "Nothing to undo. {} is already gone.\n".format(name)
    try:
        return _apply_undo(store_mod, record)
    except Exception:
        try:
            store_mod.push(record)
        except Exception:
            pass
        return "Something went wrong mid-undo. The receipt is kept, so try /concierge undo again.\n"


def _apply_undo(store_mod: Any, record: dict) -> str:
    kind = record.get("kind", "")
    if kind == "rule":
        backup = record.get("soul_backup", "")
        existed = bool(record.get("soul_existed", True))
        soul_path = record.get("soul_path", "")
        profile = record.get("profile", "") or ""
        try:
            if profile.lower() in ("default", "main", "custom", ""):
                scope = store_mod.home()
            else:
                scope = store_mod.profile_dir(profile)
        except Exception:
            return "Nothing to undo. That receipt points outside this home.\n"
        if soul_path and not _safe_soul_file(soul_path, scope=scope):
            return "Nothing to undo. That receipt points outside this home.\n"
        if backup and not _safe_soul_file(backup, backup=True, scope=scope):
            return "Nothing to undo. That receipt points outside this home.\n"
        if backup:
            ok = store_mod.restore_rule(soul_path, backup, True)
            if ok:
                return "Undone: rule in {}.\n".format(record.get("profile", ""))
            store_mod.push(record)
            return "Not fully undone: rule in {}. The backup is kept at {}. Copy it back to undo this.\n".format(record.get("profile", ""), backup)
        if not existed:
            try:
                from pathlib import Path as _Path

                _Path(soul_path).unlink(missing_ok=True)
                gone = not _Path(soul_path).exists()
            except Exception:
                gone = False
            if gone:
                return "Undone: rule in {}.\n".format(record.get("profile", ""))
            store_mod.push(record)
            return "Not fully undone: rule in {}. Nothing was kept, and {} is still there. Open it and delete the rule to finish the undo.\n".format(record.get("profile", ""), soul_path)
        store_mod.push(record)
        return "Not fully undone: rule in {}. No backup exists. Open {} and delete the rule to finish the undo.\n".format(record.get("profile", ""), soul_path or "the soul file")
    if kind == "skill":
        paths = record.get("paths", []) or []
        missing: list = []
        for folder in paths:
            if folder and not store_mod.remove_skill_dir(folder):
                missing.append(folder)
        if missing:
            record["paths"] = missing
            store_mod.push(record)
            return "Not fully undone: {}. These are still there: {}. Delete those folders to finish the undo.\n".format(record.get("name", ""), ", ".join(missing[:3]))
        return "Undone: {}.\n".format(record.get("name", ""))
    if kind == "plugin":
        name = record.get("name", "")
        code, _out = store_mod.remove_plugin(name, profile=record.get("profile", "") or "")
        if code == 0:
            return "Undone: {}.\n".format(name)
        store_mod.push(record)
        return "Not fully undone: {}. Remove it with: `hermes plugins remove {}`.\n".format(name, name)
    if kind == "bot":
        name = record.get("name", "")
        if not isinstance(name, str):
            return "Cleared an unreadable receipt. Say the job: /concierge something that reads my pdfs.\n"
        code, _out = store_mod.delete_bot(name)
        if code == 0:
            return "Undone: {}.\n".format(record.get("name", ""))
        store_mod.push(record)
        return "Not fully undone: {}. Delete it with: `hermes profile delete {}`.\n".format(record.get("name", ""), name)
    return "Cleared an unreadable receipt. Say the job: /concierge something that reads my pdfs.\n"


def on_admission(text: str = "", session_key: str = "", platform: str = "", **_kw: Any) -> Any:
    """Answer a pending question this conversation is holding, and nothing else.

    The fire prompt asks for a plain yes or no, and a plain reply arrives as an
    ordinary message, not as a command. So the hook takes exactly that case: a
    delete is pending for this session and the sentence is a yes, a no, or the
    number the prompt printed. Every other message returns None and is left
    alone, which is why this cannot swallow normal chat.

    The platform the hook was told about is the surface this runs on, and it is
    what the refusal gate reads: a worker can strip session variables, so the
    named surface is the answer that cannot go missing.
    """
    try:
        if not session_key:
            return None
        pending = _PENDING.get(session_key) or {}
        if not (pending.get("key", "") or "").startswith("fire:"):
            return None
        if _refusal(platform):
            return None
        low = " ".join(str(text or "").split()).strip().lower()
        if not low:
            return None
        if not (_YES_RX.match(low) or _NO_RX.match(low) or low.isdigit()):
            return None
        reply = handle_concierge(text, session_key=session_key)
        return {"action": "handled", "reply": reply}
    except Exception:
        return None


def register(ctx: Any) -> None:
    global _CTX

    _CTX = ctx
    ctx.register_command(
        "concierge",
        handler=handle_concierge,
        description="One sentence installs a skill or plugin, or makes a bot. One undo takes it back.",
        args_hint="<sentence> | install | create | improve | browse | bots | fire | undo | help",
    )
    try:
        ctx.register_hook("post_gateway_admission", on_admission)
    except Exception:
        pass
