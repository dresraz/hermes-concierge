"""Undo has to reverse an install in reverse order, and survive one bad step.

Every core action is injected here, so nothing in this file touches the real
cron store, the real skills directory or a real SOUL file.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

state = harness.load("state")
undo = harness.load("undo")


class MemoryBackend:
    """Stands in for core's PluginState: a dict with get/set."""

    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class AlreadyGone(unittest.TestCase):
    def test_plugin_that_is_not_there_is_reported_not_restored(self):
        """A receipt for something already absent must not fail or lie.

        Core refuses to remove a plugin it does not know, and an undo that dies
        there keeps the receipt forever. "already gone" is the honest line.
        """
        record = state.Installed(name="cognee", sha="b13274096018")
        called = []
        lines = undo.undo(
            record,
            installed=lambda name: False,
            uninstall=lambda name: called.append(name),
        )
        self.assertEqual(lines, ["already gone: plugin cognee"])
        self.assertEqual(called, [])

    def test_plugin_that_is_there_is_removed(self):
        record = state.Installed(name="cognee", sha="b13274096018")
        called = []
        lines = undo.undo(
            record,
            installed=lambda name: True,
            uninstall=lambda name: called.append(name),
        )
        self.assertEqual(lines, ["restored: plugin cognee"])
        self.assertEqual(called, ["cognee"])


class Recorder:
    """Records every injected call, in order, and can fail on demand."""

    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = dict(fail_on or {})

    def _record(self, action, *args):
        self.calls.append((action,) + args)
        if action in self.fail_on:
            raise RuntimeError(self.fail_on[action])

    def disable(self, cron_id):
        self._record("disable", cron_id)

    def uninstall(self, name):
        self._record("uninstall", name)

    def remove_skill(self, name):
        self._record("remove_skill", name)

    def restore(self, snapshot):
        self._record("restore", snapshot)

    @property
    def actions(self):
        return [call[0] for call in self.calls]


class Undo(unittest.TestCase):
    def setUp(self):
        self.rec = Recorder()
        self.record = state.Installed(
            name="hermes-memory-locus",
            sha="a" * 40,
            cron_id="job-42",
            skills=["note-taking", "obsidian"],
            soul_path="/tmp/SOUL.md",
            soul_backup="/tmp/SOUL.md.concierge-backup",
            soul_existed=True,
        )

    def run_undo(self, record=None, **kwargs):
        rec = self.rec
        return undo.undo(
            self.record if record is None else record,
            disable=rec.disable,
            uninstall=rec.uninstall,
            remove_skill=rec.remove_skill,
            restore=rec.restore,
            **kwargs,
        )

    def test_nothing_installed_has_nothing_to_undo(self):
        store = state.Store(MemoryBackend())
        self.assertEqual(store.latest(), None)
        self.assertEqual(undo.undo_latest(store), ["nothing to undo"])

    def test_empty_store_has_nothing_to_undo(self):
        class EmptyStore:
            def latest(self):
                return None

        self.assertEqual(undo.undo_latest(EmptyStore()), ["nothing to undo"])

    def test_full_record_runs_every_step_in_order(self):
        lines = self.run_undo()
        self.assertEqual(
            self.rec.actions,
            ["disable", "remove_skill", "remove_skill", "uninstall", "restore"],
        )
        self.assertEqual(self.rec.calls[0], ("disable", "job-42"))
        self.assertEqual(self.rec.calls[3], ("uninstall", "hermes-memory-locus"))
        self.assertEqual(
            lines,
            [
                "restored: cron job job-42",
                "restored: skill obsidian",
                "restored: skill note-taking",
                "restored: plugin hermes-memory-locus",
                "restored: SOUL /tmp/SOUL.md",
            ],
        )
        self.assertEqual(len(lines), 5)

    def test_restore_gets_a_snapshot_built_from_the_record(self):
        self.run_undo()
        snapshot = self.rec.calls[-1][1]
        self.assertEqual(snapshot.path, "/tmp/SOUL.md")
        self.assertEqual(snapshot.backup, "/tmp/SOUL.md.concierge-backup")
        self.assertTrue(snapshot.existed)

    def test_one_failing_step_still_lets_later_steps_run(self):
        self.rec.fail_on["disable"] = "cron is locked"
        lines = self.run_undo()
        self.assertEqual(
            self.rec.actions,
            ["disable", "remove_skill", "remove_skill", "uninstall", "restore"],
        )
        self.assertEqual(
            lines[0], "could not restore cron job job-42: RuntimeError: cron is locked"
        )
        self.assertEqual(lines[1], "restored: skill obsidian")
        self.assertEqual(lines[4], "restored: SOUL /tmp/SOUL.md")

    def test_a_failing_skill_does_not_stop_the_plugin_or_the_soul(self):
        self.rec.fail_on["remove_skill"] = "skill is busy"
        lines = self.run_undo()
        self.assertIn("could not restore skill obsidian: RuntimeError: skill is busy", lines)
        self.assertIn("could not restore skill note-taking: RuntimeError: skill is busy", lines)
        self.assertEqual(lines[-2], "restored: plugin hermes-memory-locus")
        self.assertEqual(lines[-1], "restored: SOUL /tmp/SOUL.md")

    def test_every_failure_is_reported_as_its_own_line(self):
        self.rec.fail_on["disable"] = "cron is locked"
        self.rec.fail_on["uninstall"] = "plugin is busy"
        lines = self.run_undo()
        failures = [line for line in lines if line.startswith("could not restore")]
        self.assertEqual(len(failures), 2)
        self.assertEqual(
            failures[0], "could not restore cron job job-42: RuntimeError: cron is locked"
        )
        self.assertEqual(
            failures[1],
            "could not restore plugin hermes-memory-locus: RuntimeError: plugin is busy",
        )

    def test_empty_fields_are_skipped(self):
        record = state.Installed(name="hermes-memory-locus")
        lines = self.run_undo(record=record)
        self.assertEqual(self.rec.actions, ["uninstall"])
        self.assertEqual(lines, ["restored: plugin hermes-memory-locus"])

    def test_a_record_with_nothing_to_reverse_reports_nothing(self):
        record = state.Installed(name="")
        lines = self.run_undo(record=record)
        self.assertEqual(lines, [])
        self.assertEqual(self.rec.calls, [])

    def test_skills_are_removed_in_reverse_order(self):
        record = state.Installed(
            name="hermes-memory-locus",
            skills=["first", "second", "third"],
        )
        self.run_undo(record=record)
        removed = [call[1] for call in self.rec.calls if call[0] == "remove_skill"]
        self.assertEqual(removed, ["third", "second", "first"])

    def test_undo_latest_uses_the_latest_record(self):
        store = state.Store(MemoryBackend())
        store.add(state.Installed(name="older", cron_id="job-1"))
        store.add(state.Installed(name="newer", cron_id="job-2"))
        lines = undo.undo_latest(
            store,
            disable=self.rec.disable,
            uninstall=self.rec.uninstall,
            remove_skill=self.rec.remove_skill,
            restore=self.rec.restore,
        )
        self.assertEqual(self.rec.calls[0], ("disable", "job-2"))
        self.assertEqual(lines[0], "restored: cron job job-2")


if __name__ == "__main__":
    unittest.main()
