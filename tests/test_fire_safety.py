"""Firing names a bot, never a plugin.

`lifecycle.resolve` only matches bot records, so a plugin installed into a bot
can never be mistaken for the bot itself: `fire pdf` and `fire pdf
researcher-bot` refuse, and only a bot selector (`fire 1 researcher-bot`)
deletes.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

commands = harness.load("commands")
state = harness.load("state")


class Memory:
    def __init__(self) -> None:
        self.data: dict = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value) -> None:
        self.data[key] = value


def store(*records):
    made = state.Store(backend=Memory())
    for record in records:
        made.add(record)
    return made


class FakeSeams:
    def __init__(self, homes: dict) -> None:
        self.homes = {name: pathlib.Path(path) for name, path in homes.items()}
        self.removed: list = []

    def profile_home(self, name: str) -> pathlib.Path:
        return self.homes.get(name, pathlib.Path(tempfile.gettempdir()) / "gone" / name)

    def profile_history(self, name: str) -> dict:
        return {"sessions": 0, "memories": 0, "cron": 0}

    def remove_profile(self, name: str, yes: bool = True) -> None:
        self.removed.append(name)
        home = self.homes.pop(name, None)
        if home is not None and home.is_dir():
            import shutil

            shutil.rmtree(home)


class FireByPluginName(unittest.TestCase):
    """A plugin name is not a bot, even next to one."""

    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp())
        (self.home / "SOUL.md").write_text("x\n", encoding="utf-8")
        self.made = store(
            state.Installed(name="researcher-bot", kind="bot", title="research", profile="researcher-bot"),
            state.Installed(name="pdf", kind="skill", title="pdf", profile="researcher-bot"),
        )
        self.seams = FakeSeams({"researcher-bot": self.home})

    def test_fire_plugin_name_alone_deletes_nothing(self):
        text = commands.handle_concierge("fire pdf", store=self.made, seams=self.seams)
        self.assertIn("did not create pdf", text)
        self.assertEqual(self.seams.removed, [])
        self.assertTrue(self.home.exists())
        self.assertEqual(
            sorted(r.name for r in self.made.all()), ["pdf", "researcher-bot"]
        )

    def test_fire_plugin_name_beside_a_bot_name_deletes_nothing(self):
        text = commands.handle_concierge(
            "fire pdf researcher-bot", store=self.made, seams=self.seams
        )
        self.assertIn("did not create pdf", text)
        self.assertEqual(self.seams.removed, [])
        self.assertTrue(self.home.exists())
        self.assertEqual(
            sorted(r.name for r in self.made.all()), ["pdf", "researcher-bot"]
        )

    def test_fire_number_plus_bot_name_still_deletes(self):
        text = commands.handle_concierge(
            "fire 1 researcher-bot", store=self.made, seams=self.seams
        )
        self.assertIn("Deleted researcher-bot", text)
        self.assertEqual(self.seams.removed, ["researcher-bot"])
        self.assertFalse(self.home.exists())


if __name__ == "__main__":
    unittest.main()
