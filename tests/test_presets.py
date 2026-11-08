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
    def test_every_role_is_five_to_fifteen_relevant_skills(self):
        for role in presets.ROLES:
            with self.subTest(role=role.name):
                total = len(role.picks)
                self.assertGreaterEqual(total, 5, role.name)
                self.assertLessEqual(total, 15, role.name)
                self.assertGreaterEqual(len(role.bundled), 1)
                for skill in role.skills:
                    self.assertEqual(skill.count("/"), 1, skill)
                    self.assertFalse(skill.startswith("official/"))
                for name in role.bundled:
                    self.assertNotIn("/", name, name)

    def test_no_skill_is_named_twice_in_a_role(self):
        for role in presets.ROLES:
            with self.subTest(role=role.name):
                picks = list(role.picks)
                self.assertEqual(len(picks), len(set(picks)), picks)

    def test_identifiers_exist_in_the_hermes_tree(self):
        """Names are not invented: each one is a real skill on disk."""
        root = Path("/home/andres/.hermes/hermes-agent")
        optional = root / "optional-skills"
        bundled = root / "skills"
        if not (optional.is_dir() and bundled.is_dir()):
            self.skipTest("Hermes tree not present")
        for role in presets.ROLES:
            for skill in role.skills:
                with self.subTest(skill=skill):
                    self.assertTrue(
                        (optional / skill / "SKILL.md").exists(),
                        "{} is not a real optional skill".format(skill),
                    )
            for name in role.bundled:
                with self.subTest(skill=name):
                    found = list(bundled.glob("*/" + name + "/SKILL.md"))
                    self.assertTrue(found, "{} is not a real bundled skill".format(name))


class Install(unittest.TestCase):
    def _home(self) -> Path:
        tmp = tempfile.mkdtemp(prefix="preset-")
        return Path(tmp) / "profiles" / "bp-test-a"

    @staticmethod
    def _copier(home: Path):
        """Stand in for core's bundled-tree copy: put the files where verify looks."""

        def copy(path, names):
            for name in names:
                folder = Path(path) / "skills" / "misc" / name
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "SKILL.md").write_text("x")
            return list(names)

        return copy

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

        role = presets.get("watcher")
        report = presets.install("bp-test-a", home, role, runner=runner,
                                 hermes="hermes", copier=self._copier(home))
        self.assertTrue(report.ok)
        self.assertEqual(len(report.installed), len(role.picks))
        self.assertEqual(len(seen), len(role.skills))
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
        # Only the bundled picks really landed; every optional one is a failure
        # even though the installer claimed success.
        self.assertEqual(sorted(report.installed), sorted(role.bundled))
        self.assertEqual(
            sorted(report.failed), sorted(s.rsplit("/", 1)[-1] for s in role.skills)
        )
        self.assertIn("failed", report.lines()[0])

    def test_bundled_skills_land_even_if_installs_fail(self):
        home = self._home()
        role = presets.get("watcher")
        report = presets.install(
            "bp-test-a", home, role,
            runner=lambda args: (1, "no network"), hermes="hermes",
            copier=self._copier(home),
        )
        for name in role.bundled:
            self.assertIn(name, report.installed)
        self.assertEqual(sorted(report.failed),
                         sorted(s.rsplit("/", 1)[-1] for s in role.skills))

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
                                 runner=runner, hermes="hermes",
                                 copier=self._copier(home))
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
        self.assertIn("Created", out)
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
        self.assertIn("Created", out)
        self.assertNotIn("installed: ", out)


if __name__ == "__main__":
    unittest.main()
