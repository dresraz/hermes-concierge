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

    def test_no_card_means_the_word_is_left_alone(self):
        self.assertIsNone(reply.rewrite("yes", "chat-a"))

    def test_the_chat_that_was_shown_the_card_may_answer_with_one_word(self):
        card._PENDING["chat-a"] = {"entry": object(), "entries": []}
        self.assertEqual(reply.rewrite("yes", "chat-a"), "/concierge yes")
        self.assertEqual(reply.rewrite("  Yep ", "chat-a"), "/concierge yes")
        self.assertEqual(reply.rewrite("nope", "chat-a"), "/concierge no")
        self.assertEqual(reply.rewrite("more", "chat-a"), "/concierge more")

    def test_another_chat_cannot_answer_it(self):
        card._PENDING["chat-a"] = {"entry": object(), "entries": []}
        self.assertIsNone(reply.rewrite("yes", "chat-b"))

    def test_a_sentence_is_left_to_the_agent(self):
        card._PENDING["chat-a"] = {"entry": object(), "entries": []}
        self.assertIsNone(reply.rewrite("yes but change the colors to blue", "chat-a"))


class GatewayDispatch(unittest.TestCase):
    def setUp(self):
        card._PENDING.clear()

    def _event(self, text):
        return SimpleNamespace(text=text, source=SimpleNamespace(chat_id="42"))

    def _gateway(self, key="chat-a"):
        return SimpleNamespace(_session_key_for_source=lambda source: key)

    def test_a_bare_yes_becomes_the_command(self):
        card._PENDING["chat-a"] = {"entry": object(), "entries": []}
        result = reply.on_gateway_dispatch(event=self._event("yes"), gateway=self._gateway())
        self.assertEqual(result, {"action": "rewrite", "text": "/concierge yes"})

    def test_ordinary_messages_pass_through_untouched(self):
        card._PENDING["chat-a"] = {"entry": object(), "entries": []}
        self.assertIsNone(
            reply.on_gateway_dispatch(event=self._event("what is on the card again?"), gateway=self._gateway())
        )
        self.assertIsNone(reply.on_gateway_dispatch(event=self._event("yes"), gateway=self._gateway("chat-b")))

    def test_an_event_without_a_source_is_ignored(self):
        self.assertIsNone(
            reply.on_gateway_dispatch(event=SimpleNamespace(text="yes", source=None), gateway=self._gateway())
        )

    def test_a_gateway_without_the_key_helper_installs_nothing(self):
        card._PENDING["chat-a"] = {"entry": object(), "entries": []}
        self.assertIsNone(reply.on_gateway_dispatch(event=self._event("yes"), gateway=object()))


if __name__ == "__main__":
    unittest.main()
