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
    """Turn the plugin on with the CLI the operator would type. Returns (enabled, notes)."""
    code, output = _run_core(["plugins", "enable", installed_name], timeout=120)
    if code != 0:
        tail = _last_lines(output, 2)
        return False, ["installed but not enabled: {}".format(tail or "hermes exited " + str(code))]
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


def current_profile() -> str:
    """The profile serving this conversation.

    Read from the *scoped* home, never the environment: one process serves many
    profiles and ``os.environ`` only holds the launch profile.
    """
    from hermes_constants import get_hermes_home

    home = Path(str(get_hermes_home()))
    if home.parent.name == "profiles":
        return home.name
    return "default"


def profile_exists(name: str) -> bool:
    from hermes_cli.profiles import profile_exists as _exists

    return bool(name) and _exists(name)


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


def link_self_plugin(target_home: Any) -> bool:
    """Give a bot its own Concierge, linked so updates flow.

    The bot gets the command so it can ask for what it needs in its own chat.
    A symlink, not a copy: one plugin to update, every bot sees it.
    """
    from pathlib import Path as _Path

    target = _Path(str(target_home))
    source = _Path(__file__).resolve().parent
    link = target / "plugins" / "concierge"
    try:
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink() and not link.exists():
            # The plugin moved: a dangling link is worse than none, because it
            # looks present and loads nothing.
            link.unlink()
        if not link.exists() and not link.is_symlink():
            link.symlink_to(source, target_is_directory=True)
    except OSError:
        return False
    try:
        from hermes_yaml import safe_dump, safe_load

        config = target / "config.yaml"
        data = {}
        if config.is_file():
            data = safe_load(config.read_text(encoding="utf-8")) or {}
        plugins = data.setdefault("plugins", {})
        enabled = plugins.setdefault("enabled", [])
        if not isinstance(enabled, list):
            return False
        if "concierge" not in enabled:
            enabled.append("concierge")
        tmp = config.with_suffix(".yaml.tmp")
        tmp.write_text(safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        tmp.replace(config)
    except Exception:
        return False
    return True


def share_credentials(target_home: Path, source_home: Optional[Path] = None) -> list:
    """Give a bot the owner's login, and keep it current.

    Copies ``.env`` and ``auth.json`` from the home that actually holds a
    credential, then merges the provider keys out of that source so a rotated
    key reaches bots that already exist instead of leaving them to fail auth.
    Channel keys are stripped, values that cannot live on one line are refused,
    and a failure is reported instead of being called a success.
    """
    import shutil
    from pathlib import Path as _Path

    source = _credential_source(source_home)
    target = _Path(str(target_home))
    notes: list = []

    for name in (".env", "auth.json"):
        origin = source / name
        if not origin.is_file():
            continue
        try:
            shutil.copy2(origin, target / name)
            (target / name).chmod(0o600)
            notes.append(name)
        except OSError as exc:
            notes.append("{} not copied ({})".format(name, exc.strerror or type(exc).__name__))

    updated, problem = _merge_provider_keys(target / ".env", source / ".env")
    if updated:
        notes.append("{} provider key(s)".format(updated))
    if problem:
        notes.append(problem)

    env = target / ".env"
    if env.is_file():
        try:
            from hermes_cli.profile_channels import strip_channel_env_file

            strip_channel_env_file(env)
        except Exception:  # no channel inventory: the copy stays, minus nothing
            pass
    return notes


def _env_value(value: str) -> Optional[str]:
    """A value that survives one line of a .env, or None if it cannot."""
    value = str(value)
    if "\n" in value or "\r" in value or "\x00" in value:
        return None
    if any(ch in value for ch in ' "#\''):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return '"{}"'.format(escaped)
    return value


def _merge_provider_keys(env_path: Path, source_env: Path) -> tuple:
    """Add missing provider keys and refresh stale ones. Never leaves a lie."""
    import os

    if not source_env.is_file():
        return 0, ""
    known = _known_provider_keys()
    wanted: dict = {}
    try:
        for line in source_env.read_text(encoding="utf-8", errors="replace").splitlines():
            key, sep, value = line.partition("=")
            key = key.strip()
            if sep and key in known and value.strip():
                cleaned = _env_value(value.strip())
                if cleaned is not None:
                    wanted[key] = cleaned
    except OSError:
        return 0, ""
    if not wanted:
        return 0, ""

    lines: list = []
    present: dict = {}
    if env_path.is_file():
        try:
            lines = env_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            return 0, ".env unreadable ({})".format(exc.strerror or "error")
        for index, line in enumerate(lines):
            key, sep, value = line.partition("=")
            if sep and key.strip():
                present[key.strip()] = index

    changed = 0
    for key, value in sorted(wanted.items()):
        if key in present:
            index = present[key]
            if lines[index].partition("=")[2].strip() != value:
                lines[index] = "{}={}".format(key, value)
                changed += 1
        else:
            lines.append("{}={}".format(key, value))
            changed += 1

    if not changed:
        return 0, ""
    try:
        env_path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
        os.chmod(env_path, 0o600)
    except OSError as exc:
        return 0, ".env not written ({})".format(exc.strerror or type(exc).__name__)
    return changed, ""


def _credential_source(preferred: Any = None) -> Path:
    """The home that actually holds the owner's login.

    A routed gateway turn reports the bot's own home, which has no .env yet, so
    the first candidate is not enough. Every plausible home is tried and the
    first one with provider keys in its .env wins; the last candidate is the
    default home, so there is always an answer.
    """
    import os as _os

    candidates = []
    if preferred is not None:
        candidates.append(Path(str(preferred)))
    candidates.append(Path(str(_os.environ.get("HERMES_HOME") or "")))
    try:
        from hermes_constants import get_hermes_home

        candidates.append(Path(str(get_hermes_home())))
    except Exception:
        pass
    candidates.append(Path.home() / ".hermes")

    known = _known_provider_keys()
    for candidate in candidates:
        if not str(candidate) or not candidate.is_dir():
            continue
        env = candidate / ".env"
        if not env.is_file():
            continue
        try:
            text = env.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(line.partition("=")[0].strip() in known and line.partition("=")[2].strip() for line in text.splitlines()):
            return candidate
    return candidates[-1]


def _known_provider_keys() -> set:
    """Every env var name Hermes treats as a provider credential."""
    names: set = set()
    try:
        from providers import list_providers

        for profile in list_providers():
            for attr in ("api_key_env_vars", "key_env", "api_key_env"):
                value = getattr(profile, attr, None)
                if isinstance(value, str) and value:
                    names.add(value)
                elif isinstance(value, (list, tuple)):
                    names.update(str(v) for v in value if v)
    except Exception:
        pass
    try:
        from hermes_cli.config_defaults import OPTIONAL_ENV_VARS

        for key, spec in (OPTIONAL_ENV_VARS or {}).items():
            if isinstance(spec, dict) and (spec.get("password") or spec.get("category") == "provider"):
                names.add(str(key))
    except Exception:
        pass
    return {name for name in names if name.isupper()}


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
        from hermes_constants import get_hermes_home

        home = Path(str(get_hermes_home()))
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
    """The installer-owned record for an installed plugin, read off its folder.

    The installer writes ``.install-metadata.json`` beside the plugin; that file
    is the record, so reading it needs no private core call.
    """
    home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    for folder in _plugin_dirs(home):
        if folder.name != name:
            continue
        record = folder / ".install-metadata.json"
        try:
            import json

            return json.loads(record.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {}


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
    from hermes_yaml import safe_load

    try:
        data = safe_load(text) or {}
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


# ---- installing into a bot ----------------------------------------------------
# A bot is a profile, and core binds HERMES_HOME when it imports. So an install
# aimed at a bot runs core's own command line as a child with `-p`: this process
# keeps serving the profile it was started in, and no global home is swapped.


def _hermes() -> str:
    return shutil.which("hermes") or "hermes"


def _run_core(args: Sequence[str], timeout: int = 600) -> tuple[int, str]:
    """Run core's CLI and return (code, output). Never raises: undo and cards report."""
    import subprocess

    try:
        done = subprocess.run(
            [_hermes(), *args], capture_output=True, text=True, timeout=timeout
        )
        return done.returncode, (done.stdout or "") + (done.stderr or "")
    except Exception as exc:  # missing binary, timeout, permissions
        return 1, "{}: {}".format(type(exc).__name__, exc)


def _last_lines(text: str, count: int = 3) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    return " / ".join(lines[-count:])


def _plugin_dirs(home: Path) -> list[Path]:
    root = Path(home) / "plugins"
    if not root.is_dir():
        return []
    return [manifest.parent for manifest in sorted(root.rglob("plugin.yaml"))
            if ".archive" not in manifest.parts]


def plugin_dir_in(home: Path, names: Sequence[str]) -> Optional[Path]:
    """The installed plugin folder in *home* that answers to one of *names*.

    Matches the folder name and the manifest name, so a catalog key that installs
    under a different directory still resolves.
    """
    wanted = {name for name in names if name}
    for folder in _plugin_dirs(home):
        if folder.name in wanted:
            return folder
        try:
            from hermes_yaml import safe_load

            data = safe_load((folder / "plugin.yaml").read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if str(data.get("name") or "") in wanted:
            return folder
    return None


def enabled_in(home: Path, name: str) -> bool:
    """True while *home* switches the plugin on. Absent from both lists counts as on."""
    try:
        from hermes_yaml import safe_load

        data = safe_load((Path(home) / "config.yaml").read_text(encoding="utf-8")) or {}
    except Exception:
        return True
    plugins = data.get("plugins") or {}
    if name in (plugins.get("disabled") or ()):
        return False
    enabled = plugins.get("enabled") or ()
    return not enabled or name in enabled


def install_in(entry, profile: str, *, replace_existing: bool = False) -> Outcome:
    """Install one catalog entry into *profile* through core's own installer.

    The child process runs core's full gate: security scan, caution decision,
    dependency consent, kill list, admission. Concierge passes the dependency
    answer the card already showed, and nothing else.
    """
    name = str(getattr(entry, "name", "") or "")
    args = ["-p", profile, "plugins", "install", name, "--yes-deps", "--enable"]
    if replace_existing:
        args.append("--force")
    code, output = _run_core(args)

    home = profile_home(profile)
    slug = str(getattr(entry, "install_identifier", "") or "").rstrip("/").rsplit("/", 1)[-1]
    target = plugin_dir_in(home, (name, slug))
    if target is None:
        return Outcome(ok=False, verdict="", blocked_reason=(
            _last_lines(output) or "core did not put a plugin in {}".format(profile)))

    outcome = Outcome(ok=True, installed_name=target.name, target=str(target), verdict="safe")
    outcome.verdict, outcome.findings = _verdict_of(entry, target)
    outcome.enabled = enabled_in(home, target.name)
    if not outcome.enabled:
        outcome.notes = ["installed but switched off in {}".format(profile)]
    return outcome


def skill_dir_in(home: Path, name: str) -> Optional[Path]:
    """Folder holding *name*'s SKILL.md under *home*/skills, or None."""
    skills = Path(home) / "skills"
    if not skills.is_dir() or not name:
        return None
    for manifest in sorted(skills.rglob("SKILL.md")):
        if ".archive" in manifest.parts:
            continue
        if manifest.parent.name == name:
            return manifest.parent
    return None


def install_skill_in(profile: str, identifier: str, *, name: str = "") -> tuple[bool, str, str]:
    """Install a skill from a hub identifier into *profile*: (ok, folder, message)."""
    code, output = _run_core(["-p", profile, "skills", "install", identifier, "--yes"])
    leaf = name or identifier.rstrip("/").rsplit("/", 1)[-1].rsplit("@", 1)[-1]
    found = skill_dir_in(profile_home(profile), leaf)
    if found is None:
        return False, "", _last_lines(output) or "core did not write a SKILL.md in {}".format(profile)
    return True, str(found), ""


def bundled_skill(name: str) -> bool:
    """True when *name* is a skill Hermes ships with, so it can be copied offline."""
    try:
        from tools import skills_sync
    except Exception:
        skills_sync = None
    root = _bundled_root(skills_sync)
    for folder in root.glob("*/" + name):
        if ".archive" not in folder.relative_to(root).parts and (folder / "SKILL.md").is_file():
            return True
    return (root / name / "SKILL.md").is_file()


def remove_plugin_in(profile: str, name: str) -> bool:
    """Remove *name* from *profile* and report whether it is really gone."""
    _run_core(["-p", profile, "plugins", "remove", name])
    return plugin_dir_in(profile_home(profile), (name,)) is None


def remove_skill_in(profile: str, name: str) -> bool:
    """Remove *name* from *profile* and report whether it is really gone."""
    _run_core(["-p", profile, "skills", "uninstall", name, "--yes"])
    return skill_dir_in(profile_home(profile), name) is None
