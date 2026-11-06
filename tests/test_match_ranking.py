"""Ranking rules that the live eval pinned down: capability outranks a name
mention, an entry that needs an unset API key loses to a usable one but is not
hidden when it is the only fit, and a nonsense ask still returns nothing.

Deterministic and offline: tiny synthetic catalogs plus os.environ patched so
no ambient key can leak into the result.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

match = harness.load("match")

ENV_KEY = "CONCIERGE_TEST_API_KEY"


def entry(name, title="", description="", caps=None, category="", tier="community"):
    return SimpleNamespace(
        name=name,
        title=title,
        description=description,
        capabilities=caps or {},
        category=category,
        tier=tier,
    )


def base_env(extra=None):
    """An environment with the test key explicitly unset, plus extras."""
    env = {k: v for k, v in os.environ.items() if k != ENV_KEY}
    if extra:
        env.update(extra)
    return env


class CapabilityBeatsName(unittest.TestCase):
    def test_tool_that_sends_beats_name_that_mentions_it(self):
        stickers = entry(
            "telegram-stickers",
            title="Telegram Stickers",
            description="Send telegram sticker packs and reactions.",
            category="chat",
        )
        sender = entry(
            "job-finished-notifier",
            title="Job Finished Notifier",
            description="Tells you when a job finishes.",
            caps={"provides_tools": ["telegram_send_message"]},
            category="automation",
        )
        with mock.patch.dict(os.environ, base_env(), clear=True):
            ranked = match.rank(
                "send me a telegram when a job finishes",
                [stickers, sender],
                limit=2,
            )
        self.assertTrue(ranked)
        self.assertEqual(ranked[0].name, "job-finished-notifier")


class EnvDemotion(unittest.TestCase):
    def _catalog(self):
        keyed = entry(
            "telegram-keyed",
            title="Telegram Keyed",
            description="A telegram sender that needs a bot token.",
            caps={
                "provides_tools": ["telegram_send_message"],
                "requires_env": [ENV_KEY],
            },
            category="chat",
        )
        free = entry(
            "telegram-free",
            title="Telegram Free",
            description="A telegram sender that needs nothing.",
            caps={"provides_tools": ["telegram_send_message"]},
            category="chat",
        )
        return [keyed, free]

    def test_unset_key_demotes_but_does_not_hide_the_only_candidate(self):
        entries = self._catalog()
        with mock.patch.dict(os.environ, base_env(), clear=True):
            ranked = match.rank("telegram send message", entries, limit=2)
        names = [c.name for c in ranked]
        # The usable entry wins; the keyed one is skipped because the usable
        # score is within a small margin of it.
        self.assertEqual(names, ["telegram-free"])

    def test_only_candidate_with_unset_key_is_still_returned(self):
        entries = [self._catalog()[0]]
        with mock.patch.dict(os.environ, base_env(), clear=True):
            ranked = match.rank("telegram send message", entries, limit=2)
        self.assertEqual([c.name for c in ranked], ["telegram-keyed"])

    def test_set_key_keeps_the_keyed_entry(self):
        entries = self._catalog()
        with mock.patch.dict(os.environ, base_env({ENV_KEY: "set"}), clear=True):
            ranked = match.rank("telegram send message", entries, limit=2)
        self.assertIn("telegram-keyed", [c.name for c in ranked])

    def test_ignore_non_env_placeholder_keys(self):
        weird = entry(
            "search-thing",
            title="Search Thing",
            description="A search tool.",
            caps={"requires_env": ["name"]},
            category="web",
        )
        with mock.patch.dict(os.environ, base_env(), clear=True):
            ranked = match.rank("search tool", [weird], limit=2)
        self.assertEqual([c.name for c in ranked], ["search-thing"])


class NoFit(unittest.TestCase):
    def test_nonsense_ask_returns_no_fit(self):
        catalog = [
            entry(
                "hermes-memory-locus",
                title="Locus memory",
                description="A memory provider that keeps notes across sessions.",
                category="memory",
            ),
            entry(
                "hermes-themes-pack",
                title="Hermes Themes Pack",
                description="Themes and skins for the CLI.",
                category="general",
            ),
        ]
        with mock.patch.dict(os.environ, base_env(), clear=True):
            self.assertEqual(match.rank("teach my goldfish to file taxes", catalog), [])
            self.assertIsNone(match.best("teach my goldfish to file taxes", catalog))

    def test_long_sentence_catching_two_words_is_not_enough(self):
        """A single name word plus one common word is a coincidence.

        The live eval caught "convert my sandwich into a spreadsheet tax form
        for fish" landing on a voice plugin through "form" and "fish". Six
        tokens need three earned words; a short ask still earns two.
        """
        catalog = [
            entry(
                "fish-voices",
                title="Fish Voices",
                description="Voices for fish narration, exported in audio form.",
                category="audio",
            ),
            entry(
                "hermes-themes-pack",
                title="Hermes Themes Pack",
                description="Themes and skins for the CLI.",
                category="general",
            ),
            entry(
                "hermes-memory-locus",
                title="Locus memory",
                description="A memory provider that keeps notes across sessions.",
                category="memory",
            ),
            entry(
                "telegram-stickers",
                title="Telegram Stickers",
                description="Send telegram sticker packs and reactions.",
                category="chat",
            ),
        ]
        with mock.patch.dict(os.environ, base_env(), clear=True):
            self.assertEqual(
                match.rank(
                    "convert my sandwich into a spreadsheet tax form for fish",
                    catalog,
                ),
                [],
            )
            self.assertTrue(match.rank("fish in audio form", catalog))


if __name__ == "__main__":
    unittest.main()
