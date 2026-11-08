"""intent.py: the model decides, the rules catch it when there is no model."""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from concierge import intent  # noqa: E402


class _Result:
    def __init__(self, parsed=None, text=""):
        self.parsed = parsed
        self.text = text


class _Llm:
    def __init__(self, answer=None, error=None):
        self.answer = answer
        self.error = error
        self.calls = []

    def complete_structured(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        if isinstance(self.answer, str):
            return _Result(text=self.answer)
        return _Result(parsed=self.answer)


def fallback(text):
    return "install", "", text


class ModelDecides(unittest.TestCase):
    def test_a_bot_request_creates_even_with_no_role_word(self):
        llm = _Llm({"intent": "create", "role": "assistant"})
        got = intent.classify(
            "I want to make a general assistant bot",
            llm=llm,
            bots=["default", "lima-house-seller"],
            roles=["assistant", "researcher"],
            fallback=fallback,
        )
        self.assertEqual(got[0], "create")
        self.assertEqual(got[2], "I want to make a general assistant bot")

    def test_a_change_to_a_known_bot_improves_it(self):
        llm = _Llm(
            {"intent": "improve", "bot": "lima-house-seller", "query": "mention the new price"}
        )
        got = intent.classify(
            "make my house bot mention the new price",
            llm=llm,
            bots=["lima-house-seller"],
            roles=["assistant"],
            fallback=fallback,
        )
        self.assertEqual(got, ("improve", "lima-house-seller", "mention the new price"))

    def test_a_capability_installs(self):
        llm = _Llm({"intent": "install", "query": "obsidian"})
        got = intent.classify(
            "install obsidian", llm=llm, bots=["default"], roles=["assistant"], fallback=fallback
        )
        self.assertEqual(got, ("install", "", "obsidian"))

    def test_json_in_text_is_read(self):
        llm = _Llm('Sure: {"intent": "create", "role": "coder"}')
        got = intent.classify(
            "make me a coder", llm=llm, bots=["default"], roles=["coder"], fallback=fallback
        )
        self.assertEqual(got[0], "create")

    def test_an_invented_intent_falls_back_to_the_rules(self):
        llm = _Llm({"intent": "summon a demon"})
        got = intent.classify(
            "install obsidian", llm=llm, bots=["default"], roles=["coder"], fallback=fallback
        )
        self.assertEqual(got[0], "install")
        self.assertEqual(got[2], "install obsidian")

    def test_an_invented_bot_is_not_used(self):
        llm = _Llm({"intent": "improve", "bot": "made-up-bot", "query": "always cite"})
        got = intent.classify(
            "improve it", llm=llm, bots=["lima-house-seller"], roles=["coder"], fallback=fallback
        )
        self.assertEqual(got[1], "")

    def test_a_failed_call_falls_back(self):
        llm = _Llm(error=RuntimeError("provider down"))
        got = intent.classify(
            "install obsidian", llm=llm, bots=["default"], roles=["coder"], fallback=fallback
        )
        self.assertEqual(got[2], "install obsidian")

    def test_no_model_means_the_rules(self):
        got = intent.classify("install obsidian", llm=None, fallback=fallback)
        self.assertEqual(got[0], "install")
