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
        empty = pathlib.Path(tempfile.mkdtemp())
        self.assertEqual(seams.share_credentials(self.dst, empty), [])


if __name__ == "__main__":
    unittest.main()
