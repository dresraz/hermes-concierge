"""Undo's default path, against real core, in a throwaway home.

The old undo tests injected their own uninstall callable, so they passed while
production raised "no uninstall function". This file injects nothing: it calls
the defaults and checks the machine afterwards. A temp HERMES_HOME keeps every
write away from the real agent home, and the test skips if core refuses to
honour the redirect.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

undo = harness.load("undo")

PLUGIN = "concierge-probe-plugin"
SKILL = "concierge-probe-skill"


def _under(child: Path, parent: Path) -> bool:
    child_real = Path(os.path.realpath(child))
    parent_real = Path(os.path.realpath(parent))
    return child_real == parent_real or parent_real in child_real.parents


class DefaultsEndToEnd(unittest.TestCase):
    def setUp(self):
        self._previous_home = os.environ.get("HERMES_HOME")
        self._home = Path(tempfile.mkdtemp(prefix="concierge-undo-"))
        os.environ["HERMES_HOME"] = str(self._home)
        try:
            from hermes_constants import get_hermes_home
        except Exception as exc:
            shutil.rmtree(self._home, ignore_errors=True)
            self.skipTest("Hermes core is not importable here: {}".format(exc))
        resolved = Path(get_hermes_home())
        if not _under(resolved, self._home):
            shutil.rmtree(self._home, ignore_errors=True)
            self.skipTest(
                "core did not honour HERMES_HOME (resolved {}); refusing to touch "
                "the real home".format(resolved)
            )

    def tearDown(self):
        if self._previous_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._previous_home
        shutil.rmtree(self._home, ignore_errors=True)

    def _installed_plugin(self) -> Path:
        target = self._home / "plugins" / PLUGIN
        target.mkdir(parents=True)
        (target / "plugin.yaml").write_text("name: {}\nversion: 0.0.1\n".format(PLUGIN))
        return target

    def _hub_skill(self) -> Path:
        target = self._home / "skills" / SKILL
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("---\nname: {}\n---\n".format(SKILL))
        lock = self._home / "skills" / ".hub" / "lock.json"
        lock.parent.mkdir(parents=True)
        lock.write_text(json.dumps({
            "version": 1,
            "installed": {
                SKILL: {
                    "install_path": SKILL,
                    "source": "skills.sh",
                    "trust_level": "verified",
                }
            },
        }))
        return target

    def test_default_uninstall_removes_a_real_plugin(self):
        target = self._installed_plugin()
        undo._default_uninstall()(PLUGIN)
        self.assertFalse(target.exists(), "undo removed nothing: {}".format(target))

    def test_default_uninstall_reports_a_missing_plugin_without_exiting(self):
        with self.assertRaises(RuntimeError):
            undo._default_uninstall()("no-such-plugin-xyz")

    def test_default_remove_skill_removes_a_real_hub_skill(self):
        target = self._hub_skill()
        undo._default_remove_skill()(SKILL)
        self.assertFalse(target.exists(), "undo removed nothing: {}".format(target))
        lock = json.loads((self._home / "skills" / ".hub" / "lock.json").read_text())
        self.assertNotIn(SKILL, lock["installed"])

    def test_default_remove_skill_refuses_a_builtin(self):
        builtin = self._home / "skills" / "always-on"
        builtin.mkdir(parents=True)
        with self.assertRaises(RuntimeError):
            undo._default_remove_skill()("always-on")
        self.assertTrue(builtin.exists(), "a skill Concierge did not install was deleted")

    def test_concierge_undo_removes_the_plugin_with_nothing_injected(self):
        """The whole production chain: the word 'undo' to a plugin that is gone."""
        target = self._installed_plugin()
        commands = harness.load("commands")
        state = harness.load("state")

        store = state.Store()
        store.add(state.Installed(name=PLUGIN, title="probe"))

        out = commands.handle_concierge("undo", store=store)

        self.assertFalse(target.exists(), "undo reported and left the plugin: {}".format(out))
        self.assertNotIn("could not", out.lower())
        self.assertIsNone(store.find(PLUGIN), "a successful undo kept its record: {}".format(out))


if __name__ == "__main__":
    unittest.main()
