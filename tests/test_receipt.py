"""Receipts read the disk: skills counted are skills, not folders and lock files."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

bots = harness.load("bots")


def _skill(root: Path, *parts: str) -> None:
    marker = root.joinpath(*parts, "SKILL.md")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("---\nname: x\n---\nDo the thing.\n", encoding="utf-8")


class SkillCount(unittest.TestCase):
    def _home(self, tmp: str) -> Path:
        home = Path(tmp) / "profiles" / "bp-test-receipt"
        home.mkdir(parents=True)
        (home / "SOUL.md").write_text("You are a bot.\n", encoding="utf-8")
        return home

    def test_bookkeeping_entries_are_not_counted_as_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self._home(tmp)
            skills = home / "skills"
            (skills / ".hub").mkdir(parents=True)
            (skills / ".usage.json").write_text("{}", encoding="utf-8")
            _skill(skills, "research", "qmd")
            _skill(skills, "research", "parallel-cli")
            _skill(skills, "note-taking", "obsidian")
            self.assertEqual(bots._skills_on_disk(home), 3)

    def test_an_archived_skill_is_not_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self._home(tmp)
            skills = home / "skills"
            _skill(skills, "research", "qmd")
            _skill(skills, ".archive", "research", "qmd")
            self.assertEqual(bots._skills_on_disk(home), 1)

    def test_receipt_reports_the_real_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = self._home(tmp)
            skills = home / "skills"
            skills.mkdir()
            (skills / ".usage.json").write_text("{}", encoding="utf-8")
            _skill(skills, "research", "qmd")
            _skill(skills, "research", "parallel-cli")
            plan = bots.Spec(name="bp-test-receipt", title="t", duties=[], boundaries=[])
            lines, _ = bots.receipt(plan, home, known=[plan.name])
            self.assertIn("2 skills installed.", lines)


if __name__ == "__main__":
    unittest.main()
