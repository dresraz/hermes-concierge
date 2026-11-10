"""Writes, and how to take them back.

Every change lands here first as a record: what kind, which profile, which
paths on disk, and a soul backup when a rule is added. Undo reverses the last
record only. Installs go through the hermes CLI itself, never around it, so a
bot never receives credentials: creation uses --clone, which leaves messaging
channels behind.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def home() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return Path(str(get_hermes_home()))
    except Exception:
        return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))


def _env_for(target: Path) -> dict:
    env = dict(os.environ)
    env["HERMES_HOME"] = str(target)
    return env


def _run(args: list, target: Path, timeout: int = 180) -> tuple:
    try:
        done = subprocess.run(
            args,
            env=_env_for(target),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            text=True,
        )
        return (done.returncode, (done.stdout or "")[-2000:])
    except Exception as exc:
        return (1, "could not run {}: {}".format(" ".join(args[:3]), exc))


def _stack_path(target: Path, create: bool = True) -> Path:
    directory = target / "cache" / "concierge"
    if create:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    return directory / "undo.json"


def _read_stack(target: Path) -> list:
    try:
        data = json.loads(_stack_path(target, create=False).read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_stack(target: Path, records: list) -> bool:
    try:
        _stack_path(target).write_text(json.dumps(records[-20:]))
        return True
    except Exception:
        return False


def push(record: dict) -> bool:
    if not isinstance(record, dict):
        return False
    try:
        target = home()
        records = _read_stack(target)
        records.append(record)
        return bool(_write_stack(target, records))
    except Exception:
        return False


def pop() -> Any:
    target = home()
    records = _read_stack(target)
    while records and records[-1] is None:
        records.pop()
    if not records:
        _write_stack(target, records)
        return None
    record = records.pop()
    _write_stack(target, records)
    return record


def peek() -> Any:
    try:
        records = _read_stack(home())
        return records[-1] if records else None
    except Exception:
        return None


def find_skill_dir(target: Path, name: str) -> str:
    for base in (target / "skills",):
        try:
            hit = base / name
            if (hit / "SKILL.md").exists():
                return str(hit)
            for path in base.rglob(name + "/SKILL.md"):
                return str(path.parent)
        except Exception:
            pass
    return ""


def has_bot_record(name: str) -> bool:
    """True when this plugin created the bot (a kind=bot record exists)."""
    try:
        for record in _read_stack(home()):
            if isinstance(record, dict) and record.get("kind") == "bot":
                if (record.get("name", "") or "").lower() == (name or "").strip().lower():
                    return True
    except Exception:
        pass
    return False


def install_skill(name: str, profile: str = "") -> tuple:
    target = home()
    clean_name = (name or "").strip()
    if not clean_name or clean_name.startswith("-") or clean_name in (".", "..") or "/" in clean_name or clean_name.startswith("."):
        return (False, "", "bad name")
    args = ["hermes"]
    if profile:
        clean_profile = (profile or "").strip()
        if (
            not clean_profile
            or clean_profile.startswith("-")
            or clean_profile in (".", "..")
            or "/" in clean_profile
            or clean_profile.startswith(".")
        ):
            return (False, "", "bad profile")
        args += ["-p", profile]
    args += ["skills", "install", name, "--yes"]
    code, out = _run(args, target)
    folder = find_skill_dir(target if not profile else profile_dir(profile), name)
    if code == 0 and folder:
        return (True, folder, out)
    return (False, "", out)


def install_plugin(name: str, profile: str = "") -> tuple:
    target = home()
    clean = (name or "").strip()
    if not clean or clean.startswith("-") or clean in (".", "..") or "/" in clean or clean.startswith("."):
        return (False, "", "bad name")
    if profile:
        try:
            target = profile_dir(profile)
        except ValueError:
            return (False, "", "bad profile")
    args = ["hermes"]
    if profile:
        args += ["-p", profile]
    args += ["plugins", "install", clean, "--enable", "--yes-deps"]
    code, out = _run(args, home(), timeout=300)
    folder = str(target / "plugins" / clean)
    try:
        exists = Path(folder).exists()
    except Exception:
        exists = False
    if code == 0 and exists:
        return (True, folder, out)
    return (False, "", out)


def remove_skill_dir(folder: str) -> bool:
    try:
        path = Path(folder)
        root = home()
        if path.is_symlink():
            return False
        resolved = path.resolve()
        try:
            root_resolved = root.resolve()
        except Exception:
            return False
        if resolved == root_resolved or root_resolved not in resolved.parents:
            return False
        if any(part in (".", "..") for part in path.parts):
            return False
        if not resolved.exists():
            return True
        if not (resolved / "SKILL.md").exists():
            return False
        shutil.rmtree(resolved, ignore_errors=False)
        return not resolved.exists()
    except Exception:
        return False


def remove_plugin(name: str, profile: str = "") -> tuple:
    target = home()
    clean = (name or "").strip()
    if not clean or clean.startswith("-") or clean in (".", "..") or "/" in clean or clean.startswith("."):
        return (1, "bad name")
    if profile and profile.lower() not in ("default", "main", "custom"):
        try:
            target = profile_dir(profile)
        except ValueError:
            return (1, "bad profile")
    folder = target / "plugins" / clean
    try:
        if not folder.exists():
            return (0, "already gone")
    except Exception:
        pass
    args = ["hermes"]
    if profile and profile.lower() not in ("default", "main", "custom"):
        args += ["-p", profile]
    args += ["plugins", "remove", clean]
    return _run(args, home(), timeout=120)


def bot_names() -> list:
    root = home()
    try:
        if root.parent.name == "profiles":
            root = root.parent.parent
    except Exception:
        pass
    profiles = root / "profiles"
    names: list = []
    try:
        for path in sorted(profiles.iterdir()):
            if path.is_dir() and not path.name.startswith("."):
                names.append(path.name)
    except Exception:
        pass
    return names


def profile_dir(name: str) -> Path:
    clean = (name or "").strip()
    if not clean or clean.startswith("-") or clean in (".", "..") or "/" in clean or clean.startswith("."):
        raise ValueError("bad profile name")
    root = home()
    try:
        if root.parent.name == "profiles":
            root = root.parent.parent
    except Exception:
        pass
    return root / "profiles" / name


def create_bot(name: str, preset_skills: list) -> tuple:
    target = home()
    clean = (name or "").strip()
    if not clean or clean.startswith("-") or clean in (".", "..") or "/" in clean or clean.startswith("."):
        return (False, "bad name", 0, [])
    if clean.lower() in ("default", "main", "custom"):
        return (False, "that one stays", 0, [])
    code, out = _run(["hermes", "profile", "create", name, "--clone", "--no-alias"], target, timeout=120)
    if code != 0:
        return (False, out, 0, [])
    # A fresh clone inherits the owner's .env. The bot must not receive
    # credentials, so drop the copied file right away. Model access resolves
    # through the credential pool, or the owner runs hermes -p <bot> auth add.
    try:
        env_file = profile_dir(name) / ".env"
        if env_file.exists():
            env_file.unlink()
    except Exception:
        pass
    done = 0
    failed: list = []
    for skill in preset_skills or []:
        try:
            skill_code, _out = _run(["hermes", "-p", name, "skills", "install", skill, "--yes"], target, timeout=180)
        except Exception:
            skill_code = 1
        if skill_code == 0:
            done += 1
        else:
            failed.append(skill)
    return (True, out, done, failed)


def delete_bot(name: str) -> tuple:
    target = home()
    clean = (name or "").strip()
    if clean.lower() in ("default", "main", "custom"):
        return (False, "that one stays")
    if not clean or clean.startswith("-") or clean in (".", "..") or "/" in clean or clean.startswith("."):
        return (False, "bad name")
    return _run(["hermes", "profile", "delete", name, "-y"], target, timeout=120)


def add_rule(bot: str, sentence: str) -> tuple:
    clean_bot = (bot or "").strip()
    if not clean_bot or clean_bot.startswith("-") or clean_bot in (".", "..") or "/" in clean_bot or clean_bot.startswith("."):
        return (False, "", "bad bot")
    base = home() if clean_bot.lower() in ("default", "main", "custom") else profile_dir(bot)
    soul = base / "SOUL.md"
    try:
        previous = soul.read_text() if soul.exists() else ""
    except Exception as exc:
        return (False, "", "could not read SOUL.md: {}. Check the profile directory is writable.".format(exc))
    want = (sentence or "").strip()
    if want and any(want == line or ("- " + want) == line for line in (l.strip() for l in previous.splitlines() if l.strip())):
        return (True, "", "duplicate")
    backup = ""
    try:
        import uuid

        if soul.exists():
            backup = str(soul) + "." + uuid.uuid4().hex[:8] + ".concierge-backup"
            shutil.copy2(str(soul), backup)
        with open(str(soul), "a", encoding="utf-8") as handle:
            handle.write("\n\n## Learned rules\n\n- {}\n".format(sentence.strip()))
        return (True, backup, "added")
    except Exception as exc:
        return (False, "", "could not write SOUL.md: {}. Check the profile directory is writable.".format(exc))


def restore_rule(soul_path: str, backup: str, existed: bool) -> bool:
    try:
        if backup and Path(backup).exists():
            shutil.copy2(backup, soul_path)
            try:
                Path(backup).unlink()
            except Exception:
                pass
            return True
        if not existed:
            try:
                Path(soul_path).unlink()
            except Exception:
                pass
            return True
        return False
    except Exception:
        return False
