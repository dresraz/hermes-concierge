"""The bare word a messaging chat may type instead of the command."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

card = harness.load("card")
reply = harness.load("reply")


class BareAnswer(unittest.TestCase):
    def setUp(self):
        card._PENDING.clear()

    def test_a_bare_word_is_recognised(self):
        self.assertEqual(reply.answer_for("yes"), "yes")
        self.assertEqual(reply.answer_for("  Yep "), "yes")
        self.assertEqual(reply.answer_for("nope"), "no")
        self.assertEqual(reply.answer_for("more"), "more")

    def test_a_sentence_is_left_to_the_agent(self):
        self.assertEqual(reply.answer_for("yes but change the colors to blue"), "")


class Admission(unittest.TestCase):
    """post_gateway_admission: after auth, with the conversation's session key."""

    def setUp(self):
        card._PENDING.clear()

    def test_no_card_means_the_word_is_not_consumed(self):
        self.assertIsNone(reply.on_admission(text="yes", session_key="chat-a"))

    def test_the_chat_that_was_shown_the_card_gets_the_answer(self):
        card._PENDING["chat-a"] = {"entry": object(), "entries": []}
        result = reply.on_admission(text="no", session_key="chat-a")
        self.assertEqual(result["action"], "handled")
        self.assertIn("Nothing installed", result["reply"])

    def test_another_chat_cannot_answer_it(self):
        card._PENDING["chat-a"] = {"entry": object(), "entries": []}
        self.assertIsNone(reply.on_admission(text="yes", session_key="chat-b"))

    def test_a_sentence_is_not_consumed(self):
        card._PENDING["chat-a"] = {"entry": object(), "entries": []}
        self.assertIsNone(reply.on_admission(text="yes, and also make it blue", session_key="chat-a"))

    def test_no_session_key_means_no_answer(self):
        card._PENDING[""] = {"entry": object(), "entries": []}
        self.assertIsNone(reply.on_admission(text="yes"))


if __name__ == "__main__":
    unittest.main()
