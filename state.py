"""What Concierge remembers about what it put where.

One record per profile, written after a successful install and read by undo. The
store is injected so tests never touch `~/.hermes`. The default store is core's
own `PluginState`, which is atomic, profile-scoped and quota bounded, so this
module owns no locking and no paths of its own.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

RECORD_KEY = "installs"


def _default_store() -> Any:
    from hermes_cli.plugins_state import PluginState

    return PluginState("concierge")


@dataclass
class Installed:
    """Everything undo needs, in the order it was written."""

    name: str
    kind: str = ""  # "" for a catalog plugin, "bot" for /hire, "skill" for /train
    sha: str = ""
    title: str = ""
    target: str = ""
    profile: str = ""
    enabled: bool = False
    cron_id: str = ""
    skills: list = field(default_factory=list)
    soul_path: str = ""
    soul_backup: str = ""
    soul_existed: bool = False
    installed_at: str = ""

    def stamp(self) -> "Installed":
        if not self.installed_at:
            self.installed_at = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
        return self

    @classmethod
    def from_dict(cls, raw: dict) -> "Installed":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})


class Store:
    """A list of `Installed` records behind a get/set pair."""

    def __init__(self, backend: Optional[Any] = None) -> None:
        self._backend = backend

    @property
    def backend(self) -> Any:
        if self._backend is None:
            self._backend = _default_store()
        return self._backend

    def all(self) -> list:
        raw = self.backend.get(RECORD_KEY, []) or []
        return [Installed.from_dict(item) for item in raw if isinstance(item, dict)]

    def save(self, records: list) -> None:
        self.backend.set(RECORD_KEY, [asdict(r) for r in records])

    def add(self, record: Installed) -> Installed:
        records = [r for r in self.all() if r.name != record.name]
        records.append(record.stamp())
        self.save(records)
        return record

    def find(self, name: str) -> Optional[Installed]:
        for record in self.all():
            if record.name == name:
                return record
        return None

    def drop(self, name: str) -> bool:
        records = self.all()
        kept = [r for r in records if r.name != name]
        if len(kept) == len(records):
            return False
        self.save(kept)
        return True

    def latest(self) -> Optional[Installed]:
        records = self.all()
        return records[-1] if records else None
