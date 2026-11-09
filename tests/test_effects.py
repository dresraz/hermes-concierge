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
    """The fallback soul: a job sentence, second person, no names, no markup."""

    BOUNDS = ["ask before sending anything to a real person", "never spend money without asking"]

    def test_a_job_sentence_becomes_you_help(self):
        text = effects.soul_text("Advertises and sells my house in Lima", self.BOUNDS)
        self.assertEqual(text.splitlines()[0], "You help advertise and sell my house in Lima.")

    def test_a_noun_phrase_stays_a_role(self):
        text = effects.soul_text("A tutor for biology", self.BOUNDS)
        self.assertEqual(text.splitlines()[0], "You are a tutor for biology.")

    def test_third_person_verbs_are_normalised(self):
        cases = {
            "Keeps my inbox at zero": "You help keep my inbox at zero.",
            "Watches three competitors": "You help watch three competitors.",
            "Goes through the receipts": "You help go through the receipts.",
            "Carries the launch": "You help carry the launch.",
        }
        for sentence, expected in cases.items():
            self.assertEqual(effects.soul_text(sentence, self.BOUNDS).splitlines()[0], expected)

    def test_no_comment_no_duplicate_heading_no_glued_heading(self):
        text = effects.soul_text("Sells my house in Lima", self.BOUNDS)
        self.assertNotIn("<!--", text)
        self.assertNotIn("added by concierge", text.lower())
        self.assertIn("\n\nLimits\n", text)
        self.assertNotIn("Your duties are", text)

    def test_is_deterministic(self):
        args = ("Keeps my inbox at zero", self.BOUNDS)
        self.assertEqual(effects.soul_text(*args), effects.soul_text(*args))

    def test_uses_no_dashes_as_punctuation(self):
        text = effects.soul_text("Sells my house \u2014 in Lima", self.BOUNDS)
        for dash in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015", "\u2212"):
            self.assertNotIn(dash, text)

    def test_stays_under_the_character_limit(self):
        text = effects.soul_text("Sells my house in Lima " + "and much more " * 200, self.BOUNDS)
        self.assertLess(len(text), 1200)

    def test_boundaries_land_as_limits(self):
        text = effects.soul_text("Sells my house in Lima", self.BOUNDS)
        self.assertIn("- Ask before sending anything to a real person.", text)
        self.assertIn("- Never spend money without asking.", text)


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
