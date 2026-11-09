"""A sentence about the bot you are talking to, not a bot called "yourself"."""

from __future__ import annotations

import unittest

import harness


class SelfImprove(unittest.TestCase):
    def setUp(self):
        self.commands = harness.load("commands")
        self.improve = harness.load("improve")

    def test_a_capability_asked_for_by_self_is_about_this_bot(self):
        for text in (
            "add pdf capabilities to yourself",
            "I need you to improve yourself and be capable of handling pdfs",
        ):
            self.assertTrue(self.commands._self_improve(text), text)
        for text in ("make me a researcher", "install pdf", "what can you do"):
            self.assertFalse(self.commands._self_improve(text), text)

    def test_already_having_it_is_not_a_miss(self):
        plan = self.improve.Plan(bot="assistant-bot", home=__import__("pathlib").Path("."), sentence="handle pdfs")
        plan.have = ["pdf"]
        text = self.improve.receipt(plan, [])
        self.assertIn("already has pdf", text)
        self.assertNotIn("Nothing in the marketplace fits", text)

    def test_behaviour_is_a_rule_without_the_word_always(self):
        self.assertTrue(self.improve.is_rule("start replies with the answer"))
        self.assertFalse(self.improve.is_rule("handle pdfs"))


if __name__ == "__main__":
    unittest.main()
