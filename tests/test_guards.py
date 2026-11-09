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
