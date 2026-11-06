"""A hire copies the owner's plugin switches, not the app's defaults."""

import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import harness  # noqa: E402
import yaml  # noqa: E402

plugins_inherit = harness.load("plugins_inherit")


def _home(root: Path, block=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    data = {"model": {"provider": "x", "default": "y"}}
    if block is not None:
        data["plugins"] = block
    (root / "config.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
    return root


def _plugin(root: Path, name: str) -> None:
    folder = root / "plugins" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "plugin.yaml").write_text("name: {}\n".format(name))


class Inherit(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="concierge-inherit-"))
        self.owner = _home(self.tmp / "owner")
        self.bot = self.tmp / "bot"
        self.bot.mkdir()

    def test_no_switches_says_stock(self):
        report = plugins_inherit.inherit(self.bot, root=self.owner)

        self.assertFalse(report.found)
        self.assertFalse(report.wrote)
        self.assertIn("stock defaults", report.lines()[0])

    def test_copies_switches_and_drops_owner_only_names(self):
        _home(
            self.owner,
            {
                "enabled": ["searxng", "web/firecrawl"],
                "disabled": ["govee", "homeassistant"],
                "entries": {"web/searxng": {"url": "http://127.0.0.1:8888"}},
            },
        )
        _plugin(self.owner, "searxng")
        _plugin(self.owner, "homeassistant")
        _plugin(self.owner, "web/searxng")

        report = plugins_inherit.inherit(self.bot, root=self.owner)

        self.assertTrue(report.wrote)
        block = yaml.safe_load((self.bot / "config.yaml").read_text())["plugins"]
        self.assertEqual(block["enabled"], ["web/firecrawl"])
        self.assertEqual(block["disabled"], ["govee"])
        self.assertNotIn("entries", block)
        self.assertEqual(sorted(report.left), ["homeassistant", "searxng", "web/searxng"])

    def test_keeps_the_profile_model_block(self):
        _home(self.owner, {"disabled": ["govee"]})
        (self.bot / "config.yaml").write_text(
            yaml.safe_dump({"model": {"default": "keep-me"}}, sort_keys=False)
        )

        plugins_inherit.inherit(self.bot, root=self.owner)

        data = yaml.safe_load((self.bot / "config.yaml").read_text())
        self.assertEqual(data["model"]["default"], "keep-me")
        self.assertEqual(data["plugins"]["disabled"], ["govee"])

    def test_line_counts_switches(self):
        _home(self.owner, {"disabled": ["a", "b"], "enabled": ["c"]})
        _plugin(self.owner, "a")

        line = plugins_inherit.inherit(self.bot, root=self.owner).lines()[0]

        self.assertIn("2 switches", line)
        self.assertIn("1 not available here", line)

    def test_left_lists_a_name_once(self):
        _home(self.owner, {"disabled": ["a"], "enabled": ["a"]})
        _plugin(self.owner, "a")

        report = plugins_inherit.inherit(self.bot, root=self.owner)

        self.assertEqual(report.left, ["a"])

    def test_missing_profile_leaves_nothing_behind(self):
        _home(self.owner, {"disabled": ["govee"]})
        gone = self.tmp / "gone"

        report = plugins_inherit.inherit(gone, root=self.owner)

        self.assertFalse(report.wrote)
        self.assertFalse(gone.exists())


if __name__ == "__main__":
    unittest.main()
