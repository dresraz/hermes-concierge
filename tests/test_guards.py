"""Neither a memory provider nor a heavy skill arrives without being asked for."""

import unittest

from tests import harness

choose = harness.load("choose")
presets = harness.load("presets")


class Memory(unittest.TestCase):
    def row(self, name, description):
        return {"kind": "plugin", "name": name, "description": description}

    def test_a_memory_provider_is_flagged_for_an_unrelated_ask(self):
        picked = self.row("mem0", "Mem0 memory provider - server-side fact extraction.")
        self.assertEqual(choose.caution_for(picked, "read pdf files"), "memory")

    def test_a_memory_provider_is_offered_plainly_when_memory_is_the_ask(self):
        picked = self.row("mem0", "Mem0 memory provider - server-side fact extraction.")
        self.assertEqual(choose.caution_for(picked, "I want it to remember things across sessions"), "")

    def test_an_ordinary_plugin_is_unaffected(self):
        picked = self.row("stripe", "Take card payments over MCP.")
        self.assertEqual(choose.caution_for(picked, "take payments"), "")

    def test_a_heavy_skill_is_flagged(self):
        picked = self.row("comfyui", "Generate images, video and audio via diffusion workflows.")
        self.assertEqual(choose.caution_for(picked, "make me some art"), "heavy")


class Surface(unittest.TestCase):
    """The desktop app and the TUI bind a session source, not a platform."""

    def setUp(self):
        commands = harness.load("commands")
        self.commands = commands
        self.saved_platform = commands._PLATFORM
        self.saved_env = __import__("os").environ.get("HERMES_SESSION_SOURCE")
        commands._PLATFORM = ""

    def tearDown(self):
        self.commands._PLATFORM = self.saved_platform
        env = __import__("os").environ
        if self.saved_env is None:
            env.pop("HERMES_SESSION_SOURCE", None)
        else:
            env["HERMES_SESSION_SOURCE"] = self.saved_env

    def test_each_surface_is_read_from_the_session_source(self):
        env = __import__("os").environ
        for source in ("desktop", "tui", "cli"):
            env["HERMES_SESSION_SOURCE"] = source
            self.assertIsNone(self.commands._gateway_refusal("make me a bot"), source)
        for source in ("telegram", ""):
            env["HERMES_SESSION_SOURCE"] = source
            self.assertIsNotNone(self.commands._gateway_refusal("make me a bot"), source)


class Heavy(unittest.TestCase):
    def test_no_role_carries_a_heavy_skill(self):
        for role in presets.ROLES:
            for pick in role.picks:
                self.assertFalse(
                    presets.heavy(pick),
                    "{} carries {}, which is too heavy for a one-sentence bot".format(role.name, pick),
                )

    def test_comfyui_is_named_heavy(self):
        self.assertTrue(presets.heavy("comfyui"))
        self.assertTrue(presets.heavy("creative/comfyui"))
        self.assertFalse(presets.heavy("pdf"))


if __name__ == "__main__":
    unittest.main()
