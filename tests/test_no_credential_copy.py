"""A bot gets no copy of the owner's login.

Copying auth.json forks single-use OAuth grants: the first profile to refresh
revokes every other copy. Core's own route is the credential pool, and a bot
that needs its own credential gets one with `hermes -p <bot> auth add`.
"""

import pathlib
import tempfile
import unittest

from unittest import mock

from tests import harness  # noqa: F401  (declares the local surface)

from hermes_yaml import safe_dump

commands = harness.load("commands")
plugins_inherit = harness.load("plugins_inherit")


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


class NoOptionCopy(unittest.TestCase):
    """A hire copies plugin names, never their option values.

    Option dicts are arbitrary and can carry URLs with credentials; the bot
    gets the switch, not the owner's login.
    """

    def plan(self):
        class Plan:
            name = "inbox-bot"
            title = "keeps my inbox at zero"

        return Plan()

    def test_option_dict_with_credentials_does_not_reach_the_bot(self):
        import os

        owner = pathlib.Path(tempfile.mkdtemp(prefix="owner-home-"))
        bot = pathlib.Path(tempfile.mkdtemp(prefix="bot-home-"))
        (owner / "config.yaml").write_text(
            safe_dump(
                {"plugins": {"entries": {"some-plugin": {"url": "https://user:token@host"}}}}
            ),
            encoding="utf-8",
        )
        with mock.patch.dict(os.environ, {"HERMES_HOME": str(owner)}):
            commands.handle_hire(
                "keeps my inbox at zero",
                store=None,
                hire=lambda text: (self.plan(), bot),
                known=[],
            )
        body = (bot / "config.yaml").read_text(encoding="utf-8")
        self.assertIn("some-plugin", body)
        self.assertNotIn("user:token@host", body)
        self.assertNotIn("token@host", body)


class Surface(unittest.TestCase):
    def test_a_messaging_chat_is_refused(self):
        self.assertNotIn("", commands._LOCAL_SURFACES)
        saved = commands._PLATFORM
        commands._PLATFORM = "telegram"
        self.addCleanup(lambda: setattr(commands, "_PLATFORM", saved))
        text = commands.handle_concierge("make me a researcher", store=None)
        self.assertIn("does not run from a shared chat", text)


if __name__ == "__main__":
    unittest.main()
