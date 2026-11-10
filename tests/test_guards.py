"""Neither a memory provider nor a heavy skill arrives without being asked for."""

import json
import unittest

from tests import harness

choose = harness.load("choose")
presets = harness.load("presets")


class ModelStub:
    """Answers entry-memory and ask-memory prompts differently."""

    def __init__(self, entry_memory=False, ask_memory=False, heavy=False):
        self.entry_memory = entry_memory
        self.ask_memory = ask_memory
        self.heavy = heavy

    def complete_structured(self, **kwargs):
        instructions = kwargs.get("instructions", "")
        if "Does this person ask" in instructions:
            payload = {"memory": self.ask_memory}
        elif "Does this entry" in instructions or "Does this marketplace entry" in instructions:
            payload = {"memory": self.entry_memory}
        else:
            payload = {"memory": self.entry_memory, "heavy": self.heavy,
                       "answer": "OTHER", "role": "none", "country": ""}

        class Result:
            text = json.dumps(payload)

        return Result()


class HeavyStub:
    def __init__(self, heavy):
        self.heavy = heavy

    def complete_structured(self, **kwargs):
        heavy = self.heavy

        class Result:
            text = json.dumps({"heavy": heavy})

        return Result()


class Memory(unittest.TestCase):
    def row(self, name, description):
        return {"kind": "plugin", "name": name, "description": description}

    def test_a_memory_provider_is_flagged_for_an_unrelated_ask(self):
        picked = self.row("mem0", "Mem0 memory provider - server-side fact extraction.")
        llm = ModelStub(entry_memory=True, ask_memory=False)
        self.assertEqual(choose.caution_for(picked, "read pdf files", llm), "memory")

    def test_a_memory_provider_is_offered_plainly_when_memory_is_the_ask(self):
        picked = self.row("mem0", "Mem0 memory provider - server-side fact extraction.")
        llm = ModelStub(entry_memory=True, ask_memory=True)
        self.assertEqual(
            choose.caution_for(picked, "I want memory that remembers things across sessions", llm),
            "",
        )

    def test_an_ordinary_plugin_is_unaffected(self):
        picked = self.row("stripe", "Take card payments over MCP.")
        llm = ModelStub(entry_memory=False, ask_memory=False)
        self.assertEqual(choose.caution_for(picked, "take payments", llm), "")

    def test_a_heavy_skill_is_flagged(self):
        picked = self.row("comfyui", "Generate images, video and audio via diffusion workflows.")
        llm = ModelStub(entry_memory=False, ask_memory=False, heavy=True)
        self.assertEqual(choose.caution_for(picked, "make me some art", llm), "heavy")


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
        env["HERMES_SESSION_SOURCE"] = "telegram"
        self.assertIsNotNone(self.commands._gateway_refusal("make me a bot"), "telegram")

    def test_a_slash_worker_with_no_identity_is_the_owners_own_app(self):
        # Slash commands run in a worker that strips session variables; asking
        # core "is this a chat channel?" answers no, which is the truth.
        env = __import__("os").environ
        env.pop("HERMES_SESSION_SOURCE", None)
        env.pop("HERMES_SESSION_PLATFORM", None)
        self.assertIsNone(self.commands._gateway_refusal("make me a bot"))


class Heavy(unittest.TestCase):
    def test_no_role_carries_a_heavy_skill(self):
        for role in presets.ROLES:
            for pick in role.picks:
                self.assertFalse(
                    presets.heavy(pick, None),
                    "{} carries {}, which is too heavy for a one-sentence bot".format(role.name, pick),
                )

    def test_heavy_is_a_model_decision_not_a_name(self):
        # No name list decides: the same name is heavy or not by the model's
        # reading of its metadata.
        self.assertTrue(presets.heavy("comfyui", HeavyStub(True)))
        self.assertFalse(presets.heavy("comfyui", HeavyStub(False)))
        self.assertFalse(presets.heavy("pdf", HeavyStub(False)))
        self.assertFalse(presets.heavy("comfyui", None))


if __name__ == "__main__":
    unittest.main()
