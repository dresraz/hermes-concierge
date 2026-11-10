"""The bare word a messaging chat may type instead of the command."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

card = harness.load("card")
commands = harness.load("commands")
reply = harness.load("reply")


class StubLlm:
    def __init__(self, answer):
        self.answer = answer

    def complete_structured(self, **kwargs):
        answer = self.answer

        class Result:
            text = json.dumps({"answer": answer})

        return Result()


class Ctx:
    def __init__(self, llm):
        self._llm = llm

    @property
    def llm(self):
        return self._llm


def pending(name="pdf", description="Read PDF files."):
    return {
        "sentence": "install {}".format(name),
        "entries": [SimpleNamespace(name=name, description=description)],
    }


class BareAnswer(unittest.TestCase):
    def setUp(self):
        card._PENDING.clear()

    def test_a_confirm_is_read_by_the_model(self):
        self.assertEqual(reply.answer_for("ok", "themes", StubLlm("CONFIRM")), "CONFIRM")
        self.assertEqual(reply.answer_for("yep, do it", "themes", StubLlm("CONFIRM")), "CONFIRM")

    def test_a_drop_is_read_by_the_model(self):
        self.assertEqual(reply.answer_for("nope", "themes", StubLlm("DROP")), "DROP")

    def test_other_leaves_the_sentence_alone(self):
        self.assertEqual(reply.answer_for("tell me more first", "themes", StubLlm("OTHER")), "OTHER")

    def test_no_model_means_other(self):
        self.assertEqual(reply.answer_for("yes", "themes", None), "OTHER")


class Admission(unittest.TestCase):
    """post_gateway_admission: after auth, with the conversation's session key."""

    def setUp(self):
        card._PENDING.clear()
        self.saved_ctx = commands._CTX
        self.saved_platform = commands._PLATFORM
        commands._CTX = Ctx(StubLlm("DROP"))

    def tearDown(self):
        commands._CTX = self.saved_ctx
        commands._PLATFORM = self.saved_platform
        card._PENDING.clear()

    def test_no_card_means_the_word_is_not_consumed(self):
        self.assertIsNone(reply.on_admission(text="yes", session_key="chat-a"))

    def test_the_chat_that_was_shown_the_card_gets_the_answer(self):
        card._PENDING["chat-a"] = pending()
        result = reply.on_admission(text="no, drop it", session_key="chat-a", platform="telegram")
        self.assertEqual(result["action"], "handled")
        self.assertIn("Nothing installed", result["reply"])

    def test_another_chat_cannot_answer_it(self):
        card._PENDING["chat-a"] = pending()
        self.assertIsNone(reply.on_admission(text="yes", session_key="chat-b", platform="telegram"))

    def test_an_undecided_sentence_is_not_consumed(self):
        commands._CTX = Ctx(StubLlm("OTHER"))
        card._PENDING["chat-a"] = pending()
        self.assertIsNone(reply.on_admission(text="tell me more first", session_key="chat-a", platform="telegram"))

    def test_no_session_key_means_no_answer(self):
        card._PENDING[""] = {"sentence": "", "entries": []}
        self.assertIsNone(reply.on_admission(text="yes"))


if __name__ == "__main__":
    unittest.main()
