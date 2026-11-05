"""Undo is the other half of install: reverse every step, in reverse order, and say so.

Every action that touches the machine is injected, so a test can run undo
without a cron store, a skills directory or a real SOUL file. The defaults are
lazy factories: they import core only when a step actually has work to do, so
an empty field never triggers an import.
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

__all__ = ["undo", "undo_latest"]


@dataclass(frozen=True)
class _Snapshot:
    """Same shape as effects.Snapshot, used while effects.py is not there yet."""

    path: str
    backup: str
    existed: bool


def _first_callable(module_names: Sequence[str], attr_names: Sequence[str], what: str) -> Callable:
    """Return the first callable core offers for `what`.

    Core spells these helpers in more than one place, so try the known modules
    and the known spellings before giving up.
    """
    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        for attr in attr_names:
            candidate = getattr(module, attr, None)
            if callable(candidate):
                return candidate
    raise AttributeError("no core {} found in {}".format(what, ", ".join(module_names)))


def _default_disable() -> Callable[[str], Any]:
    """Core call that takes a cron job id away."""
    return _first_callable(
        ("cron.jobs", "cron.scheduler", "hermes_cli.cron", "hermes_cli.cron_cli"),
        (
            "remove_job",
            "delete_job",
            "disable_job",
            "remove_cron_job",
            "delete_cron_job",
            "disable_cron_job",
        ),
        "cron job removal",
    )


def _default_remove_skill() -> Callable[[str], Any]:
    """Core's hub uninstaller: the one call that removes a skill it installed.

    It also refuses builtins, which is the behaviour we want: a skill Concierge
    did not put there must survive undo.
    """
    from tools.skills_hub_install import uninstall_skill

    def _remove(skill_name: str) -> None:
        ok, message = uninstall_skill(skill_name)
        if not ok:
            raise RuntimeError(message)

    return _remove


def _default_uninstall() -> Callable[[str], Any]:
    """Core's own plugin removal, reached through the module that owns that seam."""
    if not __package__:
        seams = importlib.import_module("seams")
    else:
        seams = importlib.import_module(".seams", __package__)
    return seams.remove_plugin


def _default_restore() -> Callable[[Any], Any]:
    """Core call that puts the SOUL file back as it was."""
    from .effects import restore_soul

    return restore_soul


def _effects_snapshot(path: str, backup: str, existed: bool) -> Any:
    """Build the snapshot handed to restore.

    effects.py owns the real Snapshot, but it may not exist yet, so fall back
    to a local shape with the same fields instead of blocking on it. A broken
    effects.py is a real error and is allowed to surface.
    """
    if not __package__:
        # Loaded flat (a test harness, a REPL): effects sits next to us by name.
        module = sys.modules.get("effects")
        if module is None:
            try:
                module = importlib.import_module("effects")
            except ImportError:
                module = None
        if module is None:
            return _Snapshot(path=path, backup=backup, existed=existed)
        return module.Snapshot(path=path, backup=backup, existed=existed)
    try:
        module = importlib.import_module(".effects", __package__)
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        if missing not in (".effects", "{}.effects".format(__package__)):
            raise
        return _Snapshot(path=path, backup=backup, existed=existed)
    return module.Snapshot(path=path, backup=backup, existed=existed)


def _run(lines: list, what: str, action: Callable[[], Any]) -> None:
    """Run one action. A failure becomes a line, never a stop."""
    try:
        action()
    except Exception as exc:
        lines.append("could not restore {}: {}: {}".format(what, type(exc).__name__, exc))
    else:
        lines.append("restored: {}".format(what))


def undo(
    record: Any,
    *,
    disable: Optional[Callable[[str], Any]] = None,
    uninstall: Optional[Callable[[str], Any]] = None,
    remove_skill: Optional[Callable[[str], Any]] = None,
    restore: Optional[Callable[[Any], Any]] = None,
) -> list:
    """Reverse one install, in reverse order, and report one plain line per action.

    The order is the reverse of the install: cron job, then skills, then the
    plugin itself, then the SOUL file. A field that is empty is skipped
    silently. A step that raises is reported and the remaining steps still run.
    """
    lines: list = []

    cron_id = getattr(record, "cron_id", "") or ""
    if cron_id:

        def _do_disable() -> None:
            step = disable if disable is not None else _default_disable()
            step(cron_id)

        _run(lines, "cron job {}".format(cron_id), _do_disable)

    skills = list(getattr(record, "skills", None) or [])
    extra_skills = list(getattr(record, "remove_skills", None) or [])
    if skills or extra_skills:

        def _remove(skill_name: str) -> None:
            step = remove_skill if remove_skill is not None else _default_remove_skill()
            step(skill_name)

        already = set(skills)
        for skill_name in reversed(skills):
            _run(lines, "skill {}".format(skill_name), lambda n=skill_name: _remove(n))
        for skill_name in reversed(extra_skills):
            if skill_name in already:
                continue
            already.add(skill_name)
            _run(lines, "skill {}".format(skill_name), lambda n=skill_name: _remove(n))

    name = getattr(record, "name", "") or ""
    if name:

        def _do_uninstall() -> None:
            step = uninstall if uninstall is not None else _default_uninstall()
            step(name)

        _run(lines, "plugin {}".format(name), _do_uninstall)

    soul_path = getattr(record, "soul_path", "") or ""
    if soul_path:
        soul_backup = getattr(record, "soul_backup", "") or ""
        soul_existed = bool(getattr(record, "soul_existed", False))

        def _do_restore() -> None:
            step = restore if restore is not None else _default_restore()
            step(_effects_snapshot(soul_path, soul_backup, soul_existed))

        _run(lines, "SOUL {}".format(soul_path), _do_restore)

    return lines


def undo_latest(store: Any, **kwargs: Any) -> list:
    """Undo the most recent install the store knows about."""
    record = store.latest()
    if record is None:
        return ["nothing to undo"]
    return undo(record, **kwargs)
