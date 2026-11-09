"""Neither a memory provider nor a heavy skill arrives without being asked for."""

import unittest

from tests import harness

choose = harness.load("choose")
presets = harness.load("presets")


class Memory(unittest.TestCase):
    def row(self, name, description):
        return {"kind": "plugin", "name": name, "description": description}

    def test_a_memory_provider_is_refused_for_an_unrelated_ask(self):
        picked = self.row("mem0", "Mem0 memory provider - server-side fact extraction.")
        self.assertFalse(choose._allowed(picked, "read pdf files"))

    def test_a_memory_provider_is_allowed_when_memory_is_the_ask(self):
        picked = self.row("mem0", "Mem0 memory provider - server-side fact extraction.")
        self.assertTrue(choose._allowed(picked, "I want it to remember things across sessions"))

    def test_an_ordinary_plugin_is_unaffected(self):
        picked = self.row("stripe", "Take card payments over MCP.")
        self.assertTrue(choose._allowed(picked, "take payments"))


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
