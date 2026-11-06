"""Souls: the standing instruction set each preset role ships with.

The lint gate lives in ``scripts/soul_lint.py`` so a human can run it on any
draft; these tests make it binding. A soul that is thin, sloppy, off-topic for
its skills, or copy-pasted between roles fails the suite.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import harness  # noqa: E402
import soul_lint  # noqa: E402

presets = harness.load("presets")
souls = harness.load("souls")


class LintGate(unittest.TestCase):
    def test_every_role_ships_a_lint_clean_soul(self):
        for role in presets.ROLES:
            with self.subTest(role=role.name):
                text = souls.get(role.name)
                self.assertTrue(text, role.name)
                self.assertEqual(soul_lint.problems(text, role.picks), [])

    def test_no_two_roles_share_a_paragraph(self):
        text = {r.name: souls.get(r.name) for r in presets.ROLES}
        self.assertEqual(soul_lint.duplicates(text), [])

    def test_every_soul_is_well_under_the_cap(self):
        for role in presets.ROLES:
            with self.subTest(role=role.name):
                self.assertLess(len(souls.get(role.name)), soul_lint.MAX_CHARS)

    def test_an_unknown_role_has_no_soul(self):
        self.assertEqual(souls.get("not-a-role"), "")
        self.assertEqual(souls.get(""), "")


class LandingOnDisk(unittest.TestCase):
    def _role(self, name="researcher"):
        return next(r for r in presets.ROLES if r.name == name)

    def test_install_writes_the_role_soul_not_the_generic_one(self):
        role = self._role()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "profiles" / "bp-test-soul"
            home.mkdir(parents=True)
            (home / "SOUL.md").write_text("generic", encoding="utf-8")
            presets.install(
                "bp-test-soul",
                home,
                role,
                runner=lambda args: (0, ""),
                copier=lambda h, names: [],
            )
            on_disk = (home / "SOUL.md").read_text(encoding="utf-8")
        self.assertEqual(on_disk, souls.get(role.name))

    def test_write_soul_leaves_a_generic_soul_alone(self):
        stranger = presets.Role("stranger", "stranger", (), ("x",), "no soul here")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "SOUL.md").write_text("generic", encoding="utf-8")
            wrote = presets.write_soul(home, stranger)
            on_disk = (home / "SOUL.md").read_text(encoding="utf-8")
        self.assertEqual(wrote, 0)
        self.assertEqual(on_disk, "generic")


if __name__ == "__main__":
    unittest.main()
