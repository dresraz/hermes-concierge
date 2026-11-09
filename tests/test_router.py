"""The sentence is read by the model; the action set stays closed."""

from __future__ import annotations

import json
import unittest

import harness


class FakeAnswer:
    def __init__(self, text):
        self.text = text


class FakeLlm:
    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    def complete_structured(self, **kwargs):
        self.prompts.append(kwargs["instructions"])
        return FakeAnswer(json.dumps(self.payload))


class Router(unittest.TestCase):
    def setUp(self):
        self.router = harness.load("router")

    def test_it_reads_an_action_and_a_target(self):
        llm = FakeLlm({"action": "improve", "bot": "assistant-bot", "what": "handle pdfs"})
        route = self.router.route(
            "add pdf capabilities to yourself",
            here="assistant-bot",
            bots=["assistant-bot", "default"],
            llm=llm,
        )
        self.assertEqual(route, {"action": "improve", "bot": "assistant-bot", "what": "handle pdfs"})
        self.assertIn("inside_bot: assistant-bot", llm.prompts[0])
        # Looking is browsing: a question must not be answered with "already has".
        self.assertIn("Words that ask to LOOK are browse", llm.prompts[0])

    def test_an_invented_action_is_refused(self):
        llm = FakeLlm({"action": "format_disk", "bot": "", "what": ""})
        self.assertIsNone(self.router.route("x", here="", bots=[], llm=llm))

    def test_an_invented_bot_name_is_dropped(self):
        llm = FakeLlm({"action": "improve", "bot": "ghost-bot", "what": "handle pdfs"})
        route = self.router.route("improve ghost-bot", here="", bots=["assistant-bot"], llm=llm)
        self.assertEqual(route["bot"], "ghost-bot")  # typed by the user, so it is theirs
        llm = FakeLlm({"action": "improve", "bot": "phantom-bot", "what": "handle pdfs"})
        route = self.router.route("make it better", here="", bots=["assistant-bot"], llm=llm)
        self.assertEqual(route["bot"], "")

    def test_no_model_means_no_route(self):
        self.assertIsNone(self.router.route("anything", here="", bots=[], llm=None))


class Dispatch(unittest.TestCase):
    def setUp(self):
        self.commands = harness.load("commands")
        import os

        os.environ.pop("HERMES_SESSION_PLATFORM", None)

    def test_the_action_runs_through_the_code_that_owns_it(self):
        llm = FakeLlm({"action": "improve", "bot": "assistant-bot", "what": "handle pdfs"})

        class Ctx:
            home_path = ""

            @property
            def llm(self):
                return llm

        self.commands._CTX = Ctx()
        self.commands._PLATFORM = "app"
        saved_is_bot_profile = self.commands._is_bot_profile
        saved_self_name = self.commands._self_name
        self.commands._is_bot_profile = lambda: True
        self.commands._self_name = lambda: "assistant-bot"
        try:
            text = self.commands.handle_concierge("add pdf capabilities to yourself", store=None)
        finally:
            self.commands._CTX = None
            self.commands._PLATFORM = ""
            self.commands._is_bot_profile = saved_is_bot_profile
            self.commands._self_name = saved_self_name
        self.assertIn("assistant-bot", text)
        self.assertNotIn("Nothing in the marketplace fits", text)


if __name__ == "__main__":
    unittest.main()
