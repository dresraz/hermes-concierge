"""A rule is the model's call: standing behavior, not a marketplace thing."""

from __future__ import annotations

import unittest

import harness


class _KindLlm:
    """A stub model that answers rule-vs-skill with one fixed kind."""

    def __init__(self, kind):
        self.kind = kind

    def complete_structured(self, **kwargs):
        kind = self.kind

        class _Result:
            text = '{"kind": "%s"}' % kind

        return _Result()


class SelfImprove(unittest.TestCase):
    def setUp(self):
        self.commands = harness.load("commands")
        self.improve = harness.load("improve")

    def test_a_rule_is_the_model_calling_it_behavior(self):
        self.assertTrue(
            self.improve.is_rule("add pdf capabilities to yourself", _KindLlm("rule"))
        )
        self.assertFalse(
            self.improve.is_rule("add pdf capabilities to yourself", _KindLlm("skill"))
        )
        self.assertFalse(self.improve.is_rule("add pdf capabilities to yourself"))

    def test_behaviour_is_a_rule_when_the_model_says_so(self):
        self.assertTrue(
            self.improve.is_rule("start replies with the answer", _KindLlm("rule"))
        )
        self.assertFalse(
            self.improve.is_rule("handle pdfs", _KindLlm("skill"))
        )

    def test_already_having_it_is_not_a_miss(self):
        plan = self.improve.Plan(bot="assistant-bot", home=__import__("pathlib").Path("."), sentence="handle pdfs")
        plan.have = ["pdf"]
        text = self.improve.receipt(plan, [])
        self.assertIn("already has pdf", text)
        self.assertNotIn("Nothing in the marketplace fits", text)


if __name__ == "__main__":
    unittest.main()
