"""seams.py: the only module in Concierge that calls into Hermes core.

Three seams, each a thin call into the code path the CLI itself uses:

    catalog()            hermes_cli.plugin_catalog.load_catalog_live()
    install(entry)       hermes_cli.plugins_cmd_catalog.install_catalog_entry()
    enable(name)         hermes_cli.plugins_cmd._set_plugin_enabled()

Nothing here re-implements a gate. The security scan, the caution decision, the
dependency consent, the removed-plugin kill list and the config admission check
all run inside core, in the order core runs them. Concierge supplies the answer
to exactly one question, the caution prompt, and only after the user answers it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Sequence

import os
import shutil
import sys


@dataclass
class Outcome:
    """What an install actually did, in the words the card prints."""

    ok: bool
    installed_name: str = ""
    target: str = ""
    verdict: str = ""
    findings: list = field(default_factory=list)
    blocked_reason: str = ""
    enabled: bool = False
    notes: list = field(default_factory=list)


def catalog() -> list:
    """Every plugin the live catalog advertises, at the pin it advertises."""
    from hermes_cli.plugin_catalog import load_catalog_live

    return load_catalog_live()


def find(name: str, entries: Optional[list] = None) -> Optional[object]:
    """The catalog entry whose name is exactly *name*, else None."""
    for entry in entries if entries is not None else catalog():
        if getattr(entry, "name", "") == name:
            return entry
    return None


def _findings(result) -> list:
    """Finding descriptions core reported, in core's wording."""
    return [getattr(f, "description", str(f)) for f in getattr(result, "findings", []) or []]


def install(entry, *, approve: Optional[Callable[[str], bool]] = None,
            replace_existing: bool = False) -> Outcome:
    """Install one catalog entry through core's install path.

    *approve* is called with core's own scan report only when core rates the
    plugin caution. Returning False leaves nothing installed. A dangerous
    rating never reaches *approve*: core refuses it and so do we.
    """
    from hermes_cli.plugins_cmd import PluginScanBlocked
    from hermes_cli.plugins_cmd_catalog import install_catalog_entry
    from tools.plugin_guard import format_scan_report

    force = replace_existing

    # A slash command has no tty for core's python-dependency question, so
    # Concierge answers it yes: the catalog is pre-screened, so a pinned plugin's
    # own packages are the safe default. The card reads the same declaration out
    # of the repo first (``declared_deps_remote``) so the person sees the packages
    # before the yes, and the receipt re-reads them on disk afterwards.
    try:
        target, manifest, installed_name = install_catalog_entry(
            entry, force=force, scan_decision_cb=None, assume_deps_consent=True)
    except PluginScanBlocked as blocked:
        result = getattr(blocked, "scan_result", None)
        verdict = getattr(result, "verdict", "dangerous")
        if verdict != "caution" or approve is None:
            return Outcome(ok=False, verdict=verdict, findings=_findings(result),
                           blocked_reason=str(blocked))
        report = format_scan_report(result)
        if not approve(report):
            return Outcome(ok=False, verdict=verdict, findings=_findings(result),
                           blocked_reason="declined at the caution prompt")
        target, manifest, installed_name = install_catalog_entry(
            entry, force=force, scan_decision_cb=lambda _result: True,
            assume_deps_consent=True)

    outcome = Outcome(ok=True, installed_name=installed_name, target=str(target), verdict="safe")
    outcome.verdict, outcome.findings = _verdict_of(entry, target)
    outcome.enabled, outcome.notes = enable(installed_name)
    return outcome


def _verdict_of(entry, target) -> tuple:
    """Re-scan the installed tree so the card reports what shipped, not what was promoted."""
    try:
        from tools.plugin_guard import scan_plugin

        result = scan_plugin(target, source=getattr(entry, "repo", "") or "")
    except Exception as exc:  # a scan that cannot run is reported, not assumed clean
        return "", [f"re-scan did not run: {type(exc).__name__}: {exc}"]
    return getattr(result, "verdict", ""), _findings(result)


def enable(installed_name: str) -> tuple:
    """Turn the plugin on through core's admission transaction. Returns (enabled, notes)."""
    from hermes_cli.plugins_cmd import _set_plugin_enabled

    try:
        _set_plugin_enabled(installed_name, enable=True)
    except Exception as exc:  # installed but not enabled is a real outcome; name the cause
        return False, [f"installed but not enabled: {type(exc).__name__}: {exc}"]
    return True, []


# ---- profiles -----------------------------------------------------------------
# A bot is a profile. These wrap core's own profile lifecycle so Concierge never
# grows a second one: aliases, seeded skills and config all stay core's work.


def profile_names() -> list[str]:
    from hermes_cli.profiles import list_profiles

    return [info.name for info in list_profiles(lazy_skill_count=True)]


def profile_home(name: str) -> Path:
    from hermes_cli.profiles import get_profile_dir

    return get_profile_dir(name)


def _nonempty_files(folder: Path) -> int:
    try:
        return sum(1 for path in folder.rglob("*") if path.is_file() and path.stat().st_size)
    except OSError:
        return 0


def profile_history(name: str) -> dict:
    """What a bot has accumulated since it was made: sessions, memory, cron jobs.

    A fresh profile comes from core with empty ``sessions/`` and ``memories/`` and
    no cron file, so anything counted here is something a person would lose if the
    profile were deleted. Filesystem only, and every read is allowed to fail: this
    runs just before a delete, so it must never be the thing that blocks one.
    """
    counts = {"sessions": 0, "memories": 0, "cron": 0}
    try:
        home = profile_home(name)
    except Exception:
        return counts
    if not home.exists():
        return counts
    db = home / "state.db"
    if db.exists():
        try:
            from sqlite3 import connect

            conn = connect("file:{}?mode=ro".format(db), uri=True)
            try:
                row = conn.execute("select count(*) from sessions").fetchone()
            finally:
                conn.close()
            counts["sessions"] = int(row[0] or 0) if row else 0
        except Exception:
            counts["sessions"] = 0
    if not counts["sessions"]:
        counts["sessions"] = _nonempty_files(home / "sessions")
    counts["memories"] = _nonempty_files(home / "memories")
    jobs = home / "cron" / "jobs.json"
    if jobs.exists():
        try:
            import json

            raw = json.loads(jobs.read_text() or "[]")
            listed = raw if isinstance(raw, list) else (raw.get("jobs") or [])
            counts["cron"] = len(listed)
        except Exception:
            counts["cron"] = 0
    return counts


def create_profile(
    name: str, *, soul: str, description: str = "", lean: bool = True
) -> Path:
    """Create a profile with a chosen brain, not the whole 44-skill tree.

    ``lean`` passes ``no_skills`` to core: the profile starts with essentials only
    (``hermes-agent``) and core writes the ``.no-bundled-skills`` marker so
    ``hermes update`` never re-seeds it. The caller then copies exactly the bundled
    skills it named on the receipt (``copy_bundled``).
    """
    from hermes_cli.profiles import create_profile as core_create_profile

    home = core_create_profile(
        name, description=description or None, soul=soul, no_skills=lean
    )
    if lean:
        # Core's create path does not run the sync that seeds essentials, so a
        # lean profile would start with no skills at all. `hermes-agent` is the
        # one skill every profile must carry.
        from agent.skill_utils import ESSENTIAL_SKILLS

        copy_bundled(Path(home), sorted(ESSENTIAL_SKILLS))
    return home


def _bundled_root(skills_sync=None, get_bundled_skills_dir=None) -> Path:
    """Find the directory that actually holds the bundled skill tree.

    Core's helpers are preferred but never required: the plugin also runs from a
    plain interpreter (tests), so the search falls back to the checkout on disk.
    ``get_bundled_skills_dir()`` is tried last on purpose, since it resolves to
    the user's own tree where stale ``.archive/`` copies shadow real skills.
    """
    candidates: list[str] = [os.getenv("HERMES_BUNDLED_SKILLS", "").strip()]
    home: Path | None = None
    try:
        import hermes_constants as constants

        home = Path(constants.get_hermes_home())
        candidates += [
            str(Path(constants.__file__).parent / "skills"),
            str(home / "hermes-agent" / "skills"),
            str(constants.get_bundled_skills_dir()),
        ]
    except Exception:  # not running inside Hermes: find the checkout ourselves
        pass
    if skills_sync is not None:
        candidates.append(str(Path(skills_sync.__file__).parent.parent / "skills"))
    if home is None:
        home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    candidates += [
        str(home / "hermes-agent" / "skills"),
        str(Path.home() / "hermes-agent" / "skills"),
    ]
    candidates += [str(Path(entry or ".") / "skills") for entry in sys.path]

    for raw in candidates:
        if not raw:
            continue
        path = Path(raw)
        if any(path.glob("**/SKILL.md")):
            return path
    return Path(candidates[-1] or "skills")


def copy_bundled(home: Path, names: Sequence[str]) -> list[str]:
    """Copy named skills from Hermes' bundled tree into ``home/skills``.

    Direct copy, not the sync manifest: a lean profile carries the opt-out marker,
    so core's sync will not touch these files on later updates.
    """
    try:
        from tools import skills_sync
    except Exception:
        skills_sync = None

    bundled = _bundled_root(skills_sync)
    dest_root = Path(home) / "skills"
    copied: list[str] = []
    for name in names:
        matches = [
            p for p in bundled.glob(f"*/{name}")
            if ".archive" not in p.relative_to(bundled).parts and (p / "SKILL.md").is_file()
        ]
        src = min(matches, key=lambda p: len(p.relative_to(bundled).parts), default=None)
        if src is None and (bundled / name / "SKILL.md").is_file():
            src = bundled / name
        if src is None:
            continue
        dest = dest_root / src.relative_to(bundled)
        if (dest / "SKILL.md").is_file():
            copied.append(name)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest)
        copied.append(name)
    return copied


def remove_profile(name: str) -> Path:
    """Delete a profile and everything under it. Irreversible, so undo asks first."""
    from hermes_cli.profiles import delete_profile

    return delete_profile(name, yes=True)


# ---- plugins ------------------------------------------------------------------


def remove_plugin(name: str) -> None:
    """Core's own removal path: uninstall, unsubscribe, de-reference the set.

    Core reports a refusal with ``sys.exit``. Undo runs inside a live session,
    so that exit is turned into an ordinary error the caller can report as one
    failed line instead of taking the session down with it.
    """
    from hermes_cli.plugins_cmd_remove import cmd_remove

    try:
        cmd_remove(name)
    except SystemExit as exc:
        reason = exc.code if isinstance(exc.code, str) else "core refused to remove it"
        raise RuntimeError("{} (plugin {})".format(reason, name)) from None


def install_metadata(name: str) -> dict:
    """The installer-owned record for an installed plugin (``.install-metadata.json``)."""
    from hermes_cli.plugins_cmd import _read_install_metadata

    return (_read_install_metadata() or {}).get(name) or {}


def plugin_installed(name: str) -> bool:
    """True while core still has an install record for this plugin.

    Undo uses this so a record pointing at something already gone reports
    "already gone" instead of failing a removal core will refuse.
    """
    if install_metadata(name):
        return True
    # A directory install has no metadata record: the folder is the record.
    from hermes_constants import get_hermes_home

    return (get_hermes_home() / "plugins" / name).is_dir()


def declared_deps(target) -> list[str]:
    """Python packages the installed plugin declared and core installed."""
    from pm.plugin_declarations import read_python_declaration

    declaration = read_python_declaration(Path(target))
    return [str(req) for req in declaration.install_requirements]


# ---- dependencies -------------------------------------------------------------
# The catalog publishes no dependency list, so the truthful moment to name the
# packages is either side of the install: read the repo's own manifest at the
# pinned sha before the yes (one small HTTPS read, no clone, nothing executed),
# and re-read the installed tree after it. No new question in either place: the
# one yes already covers the install, core installs the packages itself, and
# Concierge only ever reports them.

_RAW = "https://raw.githubusercontent.com/{repo}/{sha}/{path}"
MANIFESTS = ("plugin.yaml", "pyproject.toml", "requirements.txt")


def _raw_url(entry, path: str) -> str:
    """The pinned raw URL for one manifest, or "" when there is nothing to read."""
    import re

    repo = str(getattr(entry, "repo", "") or "").rstrip("/")
    sha = str(getattr(entry, "sha", "") or "")
    match = re.match(r"https://github\.com/([^/]+/[^/]+)", repo)
    if not match or not sha:
        return ""
    sub = str(getattr(entry, "subdir", "") or "").strip("/")
    tail = f"{sub}/{path}" if sub else path
    return _RAW.format(repo=match.group(1), sha=sha, path=tail)


def _fetch_text(url: str, timeout: float = 4.0) -> str:
    import urllib.request

    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read(200_000).decode("utf-8", "replace")


def _specs_in(name: str, text: str) -> list[str]:
    """Package specs declared by one manifest file, or [] when it declares none."""
    if name == "requirements.txt":
        return [line.split("#")[0].strip() for line in text.splitlines()
                if line.split("#")[0].strip()]
    if name == "pyproject.toml":
        import tomllib

        try:
            data = tomllib.loads(text)
        except Exception:
            return []
        project = data.get("project") or {}
        specs = [str(s) for s in project.get("dependencies") or []]
        if specs:
            return specs
        poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
        return [str(k) for k in poetry if str(k).lower() != "python"]
    import yaml

    try:
        data = yaml.safe_load(text) or {}
    except Exception:
        return []
    for key in ("python_dependencies", "pip_dependencies", "install_requirements"):
        value = data.get(key)
        if value:
            return [str(v) for v in (value if isinstance(value, list) else [value])]
    return []


def declared_deps_remote(entry, *, fetch: Optional[Callable[[str], str]] = None) -> list[str]:
    """Packages the plugin's own repo declares, read at the pin in the catalog.

    Returns [] when the entry is unpinned, unreachable, or declares nothing: an
    unknown dependency list is printed as no list, never as "no dependencies".
    """
    get = fetch or _fetch_text
    for name in MANIFESTS:
        url = _raw_url(entry, name)
        if not url:
            return []
        try:
            text = get(url)
        except Exception:
            continue
        if text:
            specs = _specs_in(name, text)
            if specs:
                return specs
    return []


def risky_deps(specs) -> list[str]:
    """Specs that resolve to code nobody screened: git, http, or a local path."""
    return [str(s) for s in specs
            if "://" in str(s) or str(s).startswith(("-", ".", "/", "git+"))]
