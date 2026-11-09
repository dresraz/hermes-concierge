"""A bot gets no copy of the owner's login.

Copying auth.json forks single-use OAuth grants: the first profile to refresh
revokes every other copy. Core's own route is the credential pool, and a bot
that needs its own credential gets one with `hermes -p <bot> auth add`.
"""

import pathlib
import tempfile
import unittest

from tests import harness  # noqa: F401  (declares the local surface)

commands = harness.load("commands")


class NoCopy(unittest.TestCase):
    def setUp(self):
        self.owner = pathlib.Path(tempfile.mkdtemp(prefix="owner-home-"))
        (self.owner / ".env").write_text(
            "OPENROUTER_API_KEY=sk-or-secret\nTELEGRAM_BOT_TOKEN=123:abc\n", encoding="utf-8"
        )
        (self.owner / "auth.json").write_text(
            '{"openai": {"access_token": "one-time"}}', encoding="utf-8"
        )
        self.bot = pathlib.Path(tempfile.mkdtemp(prefix="bot-home-"))
        saved = commands._HOME
        commands._HOME = self.owner
        self.addCleanup(lambda: setattr(commands, "_HOME", saved))

    def plan(self):
        class Plan:
            name = "inbox-bot"
            title = "keeps my inbox at zero"

        return Plan()

    def test_the_bot_home_gets_no_env_and_no_auth_file(self):
        commands.handle_hire(
            "keeps my inbox at zero",
            store=None,
            hire=lambda text: (self.plan(), self.bot),
            known=[],
        )
        self.assertFalse((self.bot / ".env").exists())
        self.assertFalse((self.bot / "auth.json").exists())

    def test_the_receipt_does_not_claim_a_login_was_handed_over(self):
        text = commands.handle_hire(
            "keeps my inbox at zero",
            store=None,
            hire=lambda text: (self.plan(), self.bot),
            known=[],
        )
        self.assertNotIn("keys ", text)
        self.assertNotIn("your login", text)
        self.assertNotIn("auth.json", text)


class Surface(unittest.TestCase):
    def test_an_unknown_surface_is_not_the_owner_session(self):
        self.assertNotIn("", commands._LOCAL_SURFACES)
        saved = commands._PLATFORM
        commands._PLATFORM = ""
        self.addCleanup(lambda: setattr(commands, "_PLATFORM", saved))
        text = commands.handle_concierge("make me a researcher", store=None)
        self.assertIn("does not run from a shared chat", text)


if __name__ == "__main__":
    unittest.main()
