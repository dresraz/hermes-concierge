"""The shelf: what is addable, read at the moment you look."""

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

shelf = harness.load("shelf")


class Shelf(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        (self.tmp / "skills").mkdir()
        (self.tmp / "config.yaml").write_text("model: {}\n", encoding="utf-8")
        patcher = mock.patch.dict(os.environ, {"HERMES_HOME": str(self.tmp)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_overview_counts_what_is_here(self):
        text = shelf.overview()
        self.assertIn("Concierge", text)
        self.assertIn("ready", text)
        self.assertIn("plugins in the catalog", text)

    def test_browse_numbers_what_it_shows(self):
        text = shelf.browse("notes", session_key="t")
        self.assertIn("LOOKING FOR  notes", text)
        self.assertIn("  1  ", text)
        self.assertTrue(shelf.pending("t"))

    def test_picking_an_installed_skill_says_so_and_installs_nothing(self):
        folder = self.tmp / "skills" / "note-taking" / "obsidian"
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text("---\nname: obsidian\n---\n", encoding="utf-8")
        text = shelf.browse("obsidian", session_key="t")
        row = shelf.items("obsidian")[0]
        self.assertTrue(row["installed"])
        self.assertIn("here", text)

    def test_a_pick_out_of_range_is_nothing(self):
        shelf.browse("notes", session_key="t")
        self.assertIsNone(shelf.pick(99, session_key="t"))


if __name__ == "__main__":
    unittest.main()
