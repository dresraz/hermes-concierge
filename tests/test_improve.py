"""improve: a bot gets what the job needs, from the marketplace on disk."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

improve = harness.load("improve")


class Plan(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.bot = self.tmp / "profiles" / "demo-bot"
        self.bot.mkdir(parents=True)
        (self.bot / "config.yaml").write_text("model: {}\n", encoding="utf-8")
        patcher = mock.patch.dict(os.environ, {"HERMES_HOME": str(self.tmp)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_capability_comes_from_the_marketplace(self):
        plan = improve.plan("demo-bot", "it needs to read scanned pdfs")
        self.assertIsNotNone(plan)
        self.assertEqual([item.name for item in plan.items], ["pdf"])
        self.assertEqual(plan.items[0].kind, "skill")

    def test_a_rule_is_a_rule_not_a_skill(self):
        plan = improve.plan("demo-bot", "always show the source first")
        self.assertEqual([item.kind for item in plan.items], ["rule"])

    def test_an_unknown_bot_is_none_not_a_crash(self):
        self.assertIsNone(improve.plan("no-such-bot", "it needs to read pdfs"))

    def test_installed_skills_are_not_proposed_twice(self):
        folder = self.bot / "skills" / "productivity" / "pdf"
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text("---\nname: pdf\n---\n", encoding="utf-8")
        plan = improve.plan("demo-bot", "it needs to read scanned pdfs")
        self.assertNotIn("pdf", [item.name for item in plan.items])


class Apply(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.bot = self.tmp / "profiles" / "demo-bot"
        self.bot.mkdir(parents=True)
        (self.bot / "config.yaml").write_text("model: {}\n", encoding="utf-8")
        patcher = mock.patch.dict(os.environ, {"HERMES_HOME": str(self.tmp)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_rule_lands_in_soul_where_every_turn_reads_it(self):
        plan = improve.plan("demo-bot", "never send without asking")
        improve.apply(plan, store=harness.load("state").Store())
        soul = (self.bot / "SOUL.md").read_text(encoding="utf-8")
        self.assertIn("## Learned rules", soul)
        self.assertIn("- never send without asking", soul)

    def test_a_skill_lands_in_the_bot_tree(self):
        plan = improve.plan("demo-bot", "it needs to read scanned pdfs")
        lines = improve.apply(plan, store=harness.load("state").Store())
        self.assertTrue(any("pdf" in line for line in lines))
        self.assertTrue((self.bot / "skills" / "productivity" / "pdf" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
