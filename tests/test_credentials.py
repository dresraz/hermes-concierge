"""A bot needs the same login, or it cannot answer."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

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
