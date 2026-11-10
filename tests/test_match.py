"""Ranking behaviour: the card promises one match, so the matcher must earn it."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

match = harness.load("match")


def entry(name, title="", description="", caps=None, category="", tier="community"):
    return SimpleNamespace(
        name=name,
        title=title,
        description=description,
        capabilities=caps or {},
        category=category,
        tier=tier,
    )


CATALOG = [
    entry(
        "hermes-memory-locus",
        title="Locus memory",
        description="A memory provider that keeps notes across sessions and recalls them.",
        caps={"provides_middleware": ["memory"]},
        category="memory",
    ),
    entry(
        "hermes-themes-pack",
        title="Hermes Themes Pack",
        description="Themes and skins for the CLI, the TUI and Desktop.",
        category="general",
    ),
    entry(
        "browser-use",
        title="Browser Use",
        description="Drive a real browser to fetch and extract pages.",
        caps={"provides_tools": ["browser_navigate", "browser_extract"]},
        category="web",
    ),
]


class Ranking(unittest.TestCase):
    def test_a_sentence_finds_the_plugin_that_does_it(self):
        top = match.rank("memory provider that recalls notes across sessions", CATALOG, limit=1)[0]
        self.assertEqual(top.name, "hermes-memory-locus")

    def test_overlapping_words_reach_the_entry(self):
        # Plain token overlap: the ask shares words with the entry itself.
        top = match.rank("themes and skins for the terminal", CATALOG, limit=1)[0]
        self.assertEqual(top.name, "hermes-themes-pack")

    def test_exact_name_wins_outright(self):
        top = match.rank("browser-use", CATALOG, limit=1)[0]
        self.assertEqual(top.name, "browser-use")

    def test_no_overlap_means_no_candidate(self):
        self.assertEqual(match.rank("quarterly payroll export", CATALOG), [])

    def test_candidates_carry_the_words_that_earned_them(self):
        top = match.rank("drive a real browser", CATALOG, limit=1)[0]
        self.assertIn("browser", top.matched)
        self.assertTrue(top.why())

    def test_ranking_is_deterministic(self):
        first = [c.name for c in match.rank("themes and memory", CATALOG, limit=3)]
        second = [c.name for c in match.rank("themes and memory", CATALOG, limit=3)]
        self.assertEqual(first, second)

    def test_limit_is_respected_and_order_is_by_score(self):
        ranked = match.rank("themes and memory and browser", CATALOG, limit=2)
        self.assertEqual(len(ranked), 2)
        self.assertGreaterEqual(ranked[0].score, ranked[1].score)

    def test_stopwords_alone_match_nothing(self):
        self.assertEqual(match.rank("I want it for me, please", CATALOG), [])

    def test_rank_returns_nothing_rather_than_a_bad_match(self):
        self.assertEqual(match.rank("quarterly payroll export", CATALOG), [])


if __name__ == "__main__":
    unittest.main()
