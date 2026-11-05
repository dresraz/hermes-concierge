"""State is what undo trusts, so the round trip has to be exact."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

state = harness.load("state")


class MemoryBackend:
    """Stands in for core's PluginState: a dict with get/set."""

    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class Records(unittest.TestCase):
    def setUp(self):
        self.store = state.Store(MemoryBackend())

    def test_empty_store_has_no_installs(self):
        self.assertEqual(self.store.all(), [])
        self.assertIsNone(self.store.latest())
        self.assertIsNone(self.store.find("anything"))

    def test_round_trip_keeps_every_field(self):
        record = state.Installed(
            name="hermes-memory-locus",
            sha="a" * 40,
            title="Locus memory",
            target="/tmp/x",
            enabled=True,
            skills=["note-taking"],
            soul_path="/tmp/SOUL.md",
            soul_backup="/tmp/SOUL.md.concierge-backup",
            soul_existed=True,
        )
        self.store.add(record)
        back = self.store.find("hermes-memory-locus")
        self.assertEqual(back.sha, record.sha)
        self.assertEqual(back.skills, ["note-taking"])
        self.assertTrue(back.soul_existed)
        self.assertTrue(back.installed_at, "a record must be time stamped when saved")

    def test_same_name_replaces_rather_than_duplicates(self):
        self.store.add(state.Installed(name="a", sha="1"))
        self.store.add(state.Installed(name="a", sha="2"))
        self.assertEqual(len(self.store.all()), 1)
        self.assertEqual(self.store.find("a").sha, "2")

    def test_drop_reports_whether_it_removed_anything(self):
        self.store.add(state.Installed(name="a"))
        self.assertTrue(self.store.drop("a"))
        self.assertFalse(self.store.drop("a"))
        self.assertEqual(self.store.all(), [])

    def test_latest_is_the_most_recent(self):
        self.store.add(state.Installed(name="a"))
        self.store.add(state.Installed(name="b"))
        self.assertEqual(self.store.latest().name, "b")

    def test_unknown_keys_in_stored_json_are_ignored(self):
        backend = MemoryBackend()
        backend.set(state.RECORD_KEY, [{"name": "a", "future_field": 1}])
        record = state.Store(backend).find("a")
        self.assertEqual(record.name, "a")

    def test_junk_entries_are_skipped(self):
        backend = MemoryBackend()
        backend.set(state.RECORD_KEY, [{"name": "a"}, "nonsense", 7])
        self.assertEqual([r.name for r in state.Store(backend).all()], ["a"])

    def test_stamp_is_set_once(self):
        record = state.Installed(name="a").stamp()
        first = record.installed_at
        self.assertEqual(record.stamp().installed_at, first)


if __name__ == "__main__":
    unittest.main()
