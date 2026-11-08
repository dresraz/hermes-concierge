"""Effects touch the real soul, the real cron store and the real skills.

Every test here runs against a temporary directory and a fake installer or
creator, and the import purity check runs in a fresh interpreter where the
core modules are blocked outright.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

effects = harness.load("effects")

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = Path(__file__).resolve().parent
SOURCE = PLUGIN_ROOT / "effects.py"

CHILD = r'''
import json
import sys

BLOCKED = {"hermes_cli", "cron", "tools"}


class Blocker:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED:
            raise ImportError("blocked import: " + fullname)
        return None


sys.meta_path.insert(0, Blocker())

events = []


def hook(event, args):
    if event.startswith("socket.") or event.startswith("subprocess."):
        events.append(event)
    elif event in ("os.system", "os.exec", "os.spawn", "os.posix_spawn"):
        events.append(event)


sys.addaudithook(hook)

sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])

import harness

module = harness.load("effects")
print(json.dumps({"loaded": module.__name__, "events": events}))
'''


def top_level_imports(tree):
    """Every module and name bound by an import statement at module level."""
    found = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.append(node.module.split(".")[0])
    return found


def top_level_calls(tree):
    """Every call expression that appears directly in module level code."""
    calls = []
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            calls.append(node.value)
    return calls


class SoulText(unittest.TestCase):
    def test_first_line_states_the_role(self):
        text = effects.soul_text("Concierge", ["install skills"], ["never spend money"])
        self.assertTrue(text.startswith("You are Concierge."), text.splitlines()[0])
        self.assertIn("Concierge", text.splitlines()[0])

    def test_is_deterministic(self):
        args = ("Concierge", ["install skills", "arm cron"], ["never touch real data"])
        self.assertEqual(effects.soul_text(*args), effects.soul_text(*args))

    def test_uses_no_dashes_as_punctuation(self):
        text = effects.soul_text(
            "Concierge",
            ["answer questions \u2014 always"],
            ["never run destructive commands"],
        )
        for dash in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015", "\u2212"):
            self.assertNotIn(dash, text)
        self.assertNotIn(" - ", text)

    def test_is_plain_prose_without_markup(self):
        text = effects.soul_text(
            "Concierge",
            ["install skills"],
            ["never spend money without asking"],
        )
        for line in text.splitlines():
            self.assertFalse(line.startswith(("-", "*", "#", ">")))
        self.assertNotIn("**", text)

    def test_stays_under_the_character_limit(self):
        duties = ["duty number %d is a fairly long description of work" % i for i in range(200)]
        text = effects.soul_text("Concierge", duties, ["never spend money"])
        self.assertLess(len(text), 1200)

    def test_short_text_stays_short(self):
        text = effects.soul_text("Concierge", ["install skills"], ["never spend money"])
        self.assertIn("install skills", text)
        self.assertIn("never spend money", text)


class WriteSoul(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_existing_file_is_backed_up_before_overwrite(self):
        path = self.dir / "SOUL.md"
        path.write_bytes(b"original bytes\n")
        snapshot = effects.write_soul(str(path), "new soul")
        backup = Path(str(path) + ".concierge-backup")
        self.assertTrue(snapshot.existed)
        self.assertEqual(snapshot.backup, str(backup))
        self.assertEqual(backup.read_bytes(), b"original bytes\n")
        self.assertEqual(path.read_text(), "new soul")

    def test_missing_file_is_created_without_a_backup(self):
        path = self.dir / "SOUL.md"
        snapshot = effects.write_soul(str(path), "fresh soul")
        self.assertFalse(snapshot.existed)
        self.assertEqual(snapshot.backup, "")
        self.assertEqual(snapshot.path, str(path))
        self.assertEqual(path.read_text(), "fresh soul")

    def test_parent_directories_are_created(self):
        path = self.dir / "nested" / "deeper" / "SOUL.md"
        snapshot = effects.write_soul(str(path), "nested soul")
        self.assertFalse(snapshot.existed)
        self.assertTrue(path.is_file())
        self.assertEqual(path.read_text(), "nested soul")


class RestoreSoul(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_backup_is_put_back_byte_for_byte(self):
        path = self.dir / "SOUL.md"
        original = b"line one\nline two\n"
        path.write_bytes(original)
        snapshot = effects.write_soul(str(path), "new soul")
        path.write_bytes(b"corrupted")
        effects.restore_soul(snapshot)
        self.assertEqual(path.read_bytes(), original)

    def test_created_file_is_removed(self):
        path = self.dir / "SOUL.md"
        snapshot = effects.write_soul(str(path), "fresh soul")
        self.assertTrue(path.exists())
        effects.restore_soul(snapshot)
        self.assertFalse(path.exists())

    def test_restoring_a_missing_created_file_is_not_an_error(self):
        path = self.dir / "SOUL.md"
        snapshot = effects.write_soul(str(path), "fresh soul")
        path.unlink()
        effects.restore_soul(snapshot)
        self.assertFalse(path.exists())


class InstallSkills(unittest.TestCase):
    def test_installer_runs_once_per_name_in_order(self):
        calls = []

        def installer(name):
            calls.append(name)
            return "installed:" + name

        records = effects.install_skills(["alpha", "beta", "gamma"], installer)
        self.assertEqual(calls, ["alpha", "beta", "gamma"])
        self.assertEqual(
            records,
            [
                {"name": "alpha", "result": "installed:alpha"},
                {"name": "beta", "result": "installed:beta"},
                {"name": "gamma", "result": "installed:gamma"},
            ],
        )

    def test_no_names_means_no_calls(self):
        calls = []
        records = effects.install_skills([], lambda name: calls.append(name))
        self.assertEqual(records, [])
        self.assertEqual(calls, [])

    def test_falsy_results_are_kept(self):
        records = effects.install_skills(["alpha"], lambda name: None)
        self.assertEqual(records, [{"name": "alpha", "result": None}])


class ImportPurity(unittest.TestCase):
    def test_module_level_imports_are_stdlib_only(self):
        tree = ast.parse(SOURCE.read_text())
        names = top_level_imports(tree)
        self.assertTrue(names)
        stdlib = getattr(sys, "stdlib_module_names", None)
        for name in names:
            self.assertNotIn(name, ("hermes_cli", "cron", "tools"))
            if stdlib is not None:
                self.assertIn(name, stdlib, name)

    def test_module_level_code_reads_no_environment(self):
        tree = ast.parse(SOURCE.read_text())
        for call in top_level_calls(tree):
            func = call.func
            rendered = ast.dump(func)
            self.assertNotIn("environ", rendered)
            self.assertNotIn("getenv", rendered)

    def test_import_pulls_in_no_core_no_network_no_subprocess(self):
        result = subprocess.run(
            [sys.executable, "-c", CHILD, str(PLUGIN_ROOT), str(TESTS_ROOT)],
            capture_output=True,
            text=True,
            cwd=str(TESTS_ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["loaded"], "concierge_under_test.effects")
        self.assertEqual(payload["events"], [])


if __name__ == "__main__":
    unittest.main()
