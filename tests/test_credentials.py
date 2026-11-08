"""A bot needs the same login, or it cannot answer."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

seams = harness.load("seams")


class Share(unittest.TestCase):
    def setUp(self):
        self.src = pathlib.Path(tempfile.mkdtemp())
        self.dst = pathlib.Path(tempfile.mkdtemp())
        (self.src / ".env").write_text(
            "OPENAI_API_KEY=sk-test\nTELEGRAM_BOT_TOKEN=123:abc\n", encoding="utf-8"
        )
        (self.src / "auth.json").write_text('{"provider": "x"}', encoding="utf-8")

    def test_the_login_is_copied(self):
        copied = seams.share_credentials(self.dst, self.src)
        self.assertEqual(sorted(copied), [".env", "auth.json"])
        self.assertTrue((self.dst / "auth.json").is_file())
        self.assertIn("OPENAI_API_KEY", (self.dst / ".env").read_text())

    def test_a_bot_token_is_not_copied(self):
        seams.share_credentials(self.dst, self.src)
        text = (self.dst / ".env").read_text()
        self.assertNotIn("TELEGRAM_BOT_TOKEN", text)

    def test_a_profile_without_credentials_says_so(self):
        from unittest import mock

        empty = pathlib.Path(tempfile.mkdtemp())
        with mock.patch.object(seams, "_credential_source", lambda _p=None: empty):
            self.assertEqual(seams.share_credentials(self.dst, empty), [])

    def test_a_rotated_key_reaches_an_existing_bot(self):
        with mock.patch.object(seams, "_known_provider_keys", lambda: {"OPENCODE_GO_API_KEY"}):
            seams.share_credentials(self.dst, self.src)
            (self.src / ".env").write_text("OPENCODE_GO_API_KEY=sk-new\n", encoding="utf-8")
            notes = seams.share_credentials(self.dst, self.src)
        self.assertIn("OPENCODE_GO_API_KEY=sk-new", (self.dst / ".env").read_text())
        self.assertEqual(notes[0], ".env")

    def test_a_value_that_cannot_fit_one_line_is_refused(self):
        # .env is line-oriented, so a value with a real newline can only arrive
        # from somewhere else. It must never be written as a second key line.
        self.assertIsNone(seams._env_value("line one\nINJECTED=1"))
        self.assertIsNone(seams._env_value("carriage\rreturn"))
        self.assertEqual(seams._env_value("plain"), "plain")
        self.assertEqual(seams._env_value("has space"), '"has space"')

    def test_a_read_only_env_is_reported_not_called_a_success(self):
        env = self.dst / ".env"
        env.write_text("OPENCODE_GO_API_KEY=old\n", encoding="utf-8")
        env.chmod(0o400)
        try:
            with mock.patch.object(seams, "_known_provider_keys", lambda: {"OPENCODE_GO_API_KEY"}):
                notes = seams.share_credentials(self.dst, self.src)
        finally:
            env.chmod(0o600)
        self.assertTrue(any("not written" in note or "not copied" in note for note in notes))

    def test_the_owner_home_is_found_even_when_the_turn_is_scoped_elsewhere(self):
        from unittest import mock

        real = pathlib.Path(tempfile.mkdtemp())
        (real / ".env").write_text("OPENCODE_GO_API_KEY=sk-x\n", encoding="utf-8")
        scoped = pathlib.Path(tempfile.mkdtemp())  # a fresh bot home, no .env
        with mock.patch.object(seams, "_credential_source", lambda _p=None: real):
            copied = seams.share_credentials(self.dst, scoped)
        self.assertIn(".env", copied)
        self.assertIn("OPENCODE_GO_API_KEY", (self.dst / ".env").read_text())


if __name__ == "__main__":
    unittest.main()
