"""Presets: the role picked from a sentence, and the skills that land with it."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

commands = harness.load("commands")
presets = harness.load("presets")
state = harness.load("state")


class Memory:
    """Where core's PluginState would sit in production."""

    def __init__(self) -> None:
        self.data: dict = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value) -> None:
        self.data[key] = value


def store():
    return state.Store(Memory())


class Detection(unittest.TestCase):
    def test_sentences_land_on_the_right_role(self):
        cases = {
            "hire a researcher for papers": "researcher",
            "something that watches a page and pings me": "watcher",
            "keep an eye on prices for me": "watcher",
            "my inbox is a mess": "assistant",
            "write my blog": "writer",
            "debug this repo": "coder",
            "design a landing page": "designer",
            "analyse my sales spreadsheet": "analyst",
            "teach me spanish": "tutor",
            "keep me on track with the roadmap": "planner",
            "growth for my instagram": "marketer",
        }
        for sentence, role in cases.items():
            with self.subTest(sentence=sentence):
                found = presets.detect(sentence)
                self.assertIsNotNone(found, sentence)
                self.assertEqual(found.name, role)

    def test_generic_words_do_not_pick_a_role(self):
        for sentence in ("hire a bot", "make me an assistant", ""):
            with self.subTest(sentence=sentence):
                self.assertIsNone(presets.detect(sentence))

    def test_roster_is_ten_and_named(self):
        self.assertEqual(len(presets.ROLES), 10)
        self.assertEqual(
            presets.names(),
            ["researcher", "writer", "coder", "assistant", "marketer",
             "watcher", "designer", "analyst", "tutor", "planner"],
        )


class Contract(unittest.TestCase):
    def test_every_skill_is_three_to_five_and_namespaced(self):
        for role in presets.ROLES:
            with self.subTest(role=role.name):
                self.assertGreaterEqual(len(role.skills), 3)
                self.assertLessEqual(len(role.skills), 5)
                for skill in role.skills:
                    self.assertEqual(skill.count("/"), 1, skill)
                    self.assertFalse(skill.startswith("official/"))

    def test_identifiers_exist_in_the_hermes_tree(self):
        """Names are not invented: each one is a real optional skill on disk."""
        roots = [
            Path("/home/andres/.hermes/hermes-agent/optional-skills"),
            Path("/home/andres/.hermes/hermes-agent/skills"),
        ]
        if not any(root.is_dir() for root in roots):
            self.skipTest("Hermes tree not present")
        for role in presets.ROLES:
            for skill in role.skills:
                with self.subTest(skill=skill):
                    self.assertTrue(
                        any((root / skill / "SKILL.md").exists() for root in roots),
                        "{} is not a real skill".format(skill),
                    )


class Install(unittest.TestCase):
    def _home(self) -> Path:
        tmp = tempfile.mkdtemp(prefix="preset-")
        return Path(tmp) / "profiles" / "bp-test-a"

    def test_commands_are_scoped_to_the_profile(self):
        home = self._home()
        seen = []

        def runner(args):
            seen.append(list(args))
            name = args[-2].rsplit("/", 1)[-1]
            folder = home / "skills" / name
            folder.mkdir(parents=True)
            (folder / "SKILL.md").write_text("x")
            return 0, "ok"

        report = presets.install("bp-test-a", home, presets.get("watcher"),
                                 runner=runner, hermes="hermes")
        self.assertTrue(report.ok)
        self.assertEqual(len(report.installed), 3)
        for args in seen:
            self.assertEqual(args[:4], ["hermes", "-p", "bp-test-a", "skills"])
            self.assertEqual(args[4], "install")
            self.assertTrue(args[5].startswith("official/"))
            self.assertEqual(args[6], "--yes")

    def test_disk_beats_exit_code(self):
        """A zero exit with nothing on disk is a failure, not a success."""
        home = self._home()
        role = presets.get("tutor")
        report = presets.install(
            "bp-test-a", home, role,
            runner=lambda args: (0, "installed"), hermes="hermes",
        )
        self.assertFalse(report.ok)
        self.assertEqual(report.installed, [])
        self.assertEqual(len(report.failed), len(role.skills))
        self.assertIn("failed", report.lines()[0])

    def test_partial_install_reports_both(self):
        home = self._home()

        def runner(args):
            name = args[-2].rsplit("/", 1)[-1]
            if name == "rss-feeds":
                return 1, "scan refused"
            folder = home / "skills" / name
            folder.mkdir(parents=True)
            (folder / "SKILL.md").write_text("x")
            return 0, "ok"

        report = presets.install("bp-test-a", home, presets.get("researcher"),
                                 runner=runner, hermes="hermes")
        self.assertFalse(report.ok)
        self.assertEqual(report.failed, ["rss-feeds"])
        self.assertIn("parallel-cli", report.installed)


class Surface(unittest.TestCase):
    def test_hire_shows_the_preset_line(self):
        home = Path(tempfile.mkdtemp(prefix="preset-hire-")) / "profile"
        home.mkdir()
        name = "researcher"

        original_install = presets.install
        presets.install = lambda profile, path, role, **kw: presets.Report(
            role.name, ["parallel-cli"], ["parallel-cli"], []
        )
        try:
            out = commands.handle_hire(
                "a researcher for papers",
                store=store(),
                hire=lambda text: (type("P", (), {"name": name, "title": "t"})(), home),
                known=[],
            )
        finally:
            presets.install = original_install
        self.assertIn("Hired", out)
        self.assertIn("skills   researcher 1/1 installed: parallel-cli", out)

    def test_hire_without_a_role_shows_no_preset_line(self):
        home = Path(tempfile.mkdtemp(prefix="preset-plain-")) / "profile"
        home.mkdir()
        out = commands.handle_hire(
            "keep my desk tidy",
            store=store(),
            hire=lambda text: (type("P", (), {"name": "desk", "title": "t"})(), home),
            known=[],
        )
        self.assertIn("Hired", out)
        self.assertNotIn("installed: ", out)


if __name__ == "__main__":
    unittest.main()
