"""A hired bot starts with your plugin switches, not the app's defaults.

Plugins live in a home, and a bot profile is its own home. A fresh profile's
`config.yaml` has no `plugins:` block, so every bundled plugin falls back to its
own default and the bot comes up with switches its owner never chose. This copies
the owner's block into the new profile, minus the names that only exist in the
owner's home: those folders are not inside the profile, so copying them would
write entries that point at nothing.

Skills are not this. A skill is copied into the bot's own `skills/` directory,
which is why presets can carry skills and cannot carry plugins.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

LISTS = ("enabled", "disabled")


@dataclass
class Report:
    """What the copy did, in the words the hire receipt prints."""

    switched: int = 0
    left: list = field(default_factory=list)
    wrote: bool = False
    found: bool = True

    def lines(self) -> list:
        if not self.found:
            return ["  plugins  stock defaults, your main profile sets no switches"]
        if not self.wrote:
            return ["  plugins  stock defaults, nothing to copy"]
        text = "  plugins  your setup, {} switches".format(self.switched)
        if self.left:
            text += ", {} not available here".format(len(self.left))
        return [text]


def home(root: Optional[Any] = None) -> Path:
    """The home the switches come from."""
    if root is not None:
        return Path(str(root))
    env = os.environ.get("HERMES_HOME", "")
    if env:
        return Path(env)
    try:
        from hermes_constants import get_hermes_home

        return Path(str(get_hermes_home()))
    except Exception:
        return Path.home() / ".hermes"


def owner_block(root: Optional[Any] = None) -> dict:
    """The owner's `plugins:` mapping, or an empty dict."""
    data = _read(home(root) / "config.yaml")
    block = data.get("plugins") if isinstance(data, dict) else None
    return block if isinstance(block, dict) else {}


def local_names(root: Optional[Any] = None) -> set:
    """Plugin folders installed into that home, as paths relative to `plugins/`."""
    base = home(root) / "plugins"
    names: set = set()
    if not base.is_dir():
        return names
    for marker in base.rglob("plugin.yaml"):
        parts = marker.parent.relative_to(base).parts
        if any(part.startswith(".") for part in parts):
            continue
        names.add("/".join(parts))
    return names


def _split(block: dict, local: set) -> tuple:
    kept: dict = {}
    left: list = []
    for key, value in block.items():
        if key in LISTS and isinstance(value, list):
            names = [name for name in value if isinstance(name, str)]
            keep = [name for name in names if name not in local]
            left += [name for name in names if name in local]
            if keep:
                kept[key] = keep
        elif key == "entries" and isinstance(value, dict):
            keep = {name: opts for name, opts in value.items() if name not in local}
            left += [name for name in value if name in local]
            if keep:
                kept["entries"] = keep
        else:
            kept[key] = value
    return kept, _unique(left)


def _unique(names: list) -> list:
    seen: set = set()
    out: list = []
    for name in names:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _count(block: dict) -> int:
    total = 0
    for key, value in block.items():
        if (key in LISTS and isinstance(value, list)) or (
            key == "entries" and isinstance(value, dict)
        ):
            total += len(value)
    return total


def inherit(profile_home: Any, root: Optional[Any] = None) -> Report:
    """Copy the owner's switches into a new profile. Never raises on a missing file."""
    block = owner_block(root)
    if not block:
        return Report(found=False)

    kept, left = _split(block, local_names(root))
    target = Path(str(profile_home))
    if not kept or not target.is_dir():
        return Report(left=left)

    path = target / "config.yaml"
    data = _read(path)
    if not isinstance(data, dict):
        data = {}
    data["plugins"] = kept
    if not _write(path, data):
        return Report(left=left)
    return Report(switched=_count(kept), left=left, wrote=True)


def _read(path: Path) -> dict:
    try:
        import yaml

        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write(path: Path, data: dict) -> bool:
    try:
        import yaml

        path.parent.mkdir(parents=True, exist_ok=True)
        text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        tmp = path.with_suffix(".yaml.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    except Exception:
        return False
    return True
