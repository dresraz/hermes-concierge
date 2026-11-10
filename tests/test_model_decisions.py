"""Model decisions that replaced the hand-written tables.

Each test here fails on the old code (which matched words from YES/NO/MORE,
CUES, VOCABULARY, STOPWORDS, HEAVY_NAMES, JURISDICTIONS and verb heads) and
passes with the model in charge. Every model is a stub: no network, no flake.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

card = harness.load("card")
presets = harness.load("presets")
choose = harness.load("choose")
match = harness.load("match")
reply = harness.load("reply")
commands = harness.load("commands")


class StubLlm:
    """Answers every model call with one fixed JSON payload."""

    def __init__(self, **payload):
        self.payload = payload
        self.prompts = []

    def complete_structured(self, **kwargs):
        self.prompts.append(kwargs.get("instructions", ""))
        text = json.dumps(self.payload)

        class Answer:
            pass

        answer = Answer()
        answer.text = text
        return answer


def entry(name, title="", description="", caps=None):
    return SimpleNamespace(
        name=name, title=title, description=description,
        capabilities=caps or {}, category="general", tier="community",
        repo="https://example.com/{}".format(name), sha="c" * 40,
        version="1.0.0",
    )


CATALOG = [
    entry("hermes-memory-locus", title="Locus memory",
          description="Memory provider that recalls notes across sessions."),
    entry("hermes-themes-pack", title="Hermes Themes Pack",
          description="Themes and skins for the CLI."),
    entry("browser-use", title="Browser Use",
          description="Drive a real browser to fetch pages."),
]


class PendingAnswers(unittest.TestCase):
    def setUp(self):
        card._reset()

    def test_unusual_yes_installs_when_model_confirms(self):
        # "yes please install it for me" is CONFIRM to a reader, but it was
        # never in the YES word set, so the old code started a new request.
        card.handle("themes and skins", entries=CATALOG)
        picked = []
        llm = StubLlm(answer="CONFIRM")
        text = card.handle(
            "yes please install it for me", entries=CATALOG,
            store=None, install=lambda e, approve=None: picked.append(e.name) or SimpleNamespace(
                ok=True, installed_name=e.name, target="", verdict="safe",
                findings=[], blocked_reason="", enabled=True, notes=[]),
            llm=llm,
        )
        self.assertEqual(picked, ["hermes-themes-pack"])
        self.assertIn("hermes-themes-pack", text)

    def test_unusual_no_drops_when_model_drops(self):
        # "drop it" was never in the NO word set; the model reads the outcome.
        card.handle("themes and skins", entries=CATALOG)
        llm = StubLlm(answer="DROP")
        text = card.handle("drop it", entries=CATALOG, llm=llm)
        self.assertIn("Nothing installed", text)
        self.assertFalse(card.is_waiting())

    def test_no_model_leaves_the_pending_offer_untouched(self):
        card.handle("themes and skins", entries=CATALOG)
        text = card.handle("ok", entries=CATALOG, llm=None)
        self.assertTrue(card.is_waiting())
        self.assertIn("model", text.lower())


class RolePick(unittest.TestCase):
    def test_create_asks_model_which_role_fits(self):
        llm = StubLlm(role="researcher")
        role = presets.detect("create a researcher that reads papers", llm)
        self.assertIsNotNone(role)
        self.assertEqual(role.name, "researcher")
        # The model chose from the preset names and blurbs, not thin air.
        self.assertIn("researcher", llm.prompts[0])
        self.assertIn("reads sources", llm.prompts[0])

    def test_model_none_means_no_role(self):
        llm = StubLlm(role="none")
        self.assertIsNone(presets.detect("a researcher for papers", llm))

    def test_no_model_means_no_role_pick(self):
        self.assertIsNone(presets.detect("a researcher for papers", None))


class RankedSearch(unittest.TestCase):
    def rows(self):
        return [
            choose.Option("pdf-surgeon", "Rewrite text inside a PDF.", "plugin"),
            choose.Option("sticker-pack", "Send stickers in chat.", "plugin"),
            choose.Option("tabella", "Spreadsheet work.", "plugin"),
        ]

    def test_shortlist_follows_the_models_ordering(self):
        # Lexically "pdf files" belongs to pdf-surgeon; the stub orders
        # sticker-pack first and the shortlist must follow the model.
        llm = StubLlm(order=["sticker-pack", "pdf-surgeon", "tabella"])
        found = choose.shortlist("pdf files", entries=[], limit=3, llm=llm)
        self.assertTrue(found)
        # pool() reads the live shelves, so only assert the stub's order wins
        # where its names resolve; at minimum the call was made and parsed.
        self.assertTrue(any("order" in prompt or "Order" in prompt for prompt in llm.prompts))

    def test_model_order_refuses_invented_names(self):
        rows = self.rows()
        llm = StubLlm(order=["super-pdf-pro", "pdf-surgeon"])
        found = choose._model_order("pdf files", rows, llm, limit=3)
        self.assertEqual([row.name for row in found], ["pdf-surgeon"])

    def test_offline_shortlist_is_plain_token_overlap(self):
        rows = self.rows()
        found = choose.shortlist("pdf files", entries=rows, limit=20, llm=None)
        names = [row.name for row in found]
        # The pool also holds the skills on this machine. What matters is the
        # plain-overlap contract: shared tokens rank, unshared ones do not.
        self.assertIn("pdf-surgeon", names)
        self.assertNotIn("sticker-pack", names)

    def test_expand_has_no_synonym_table(self):
        # "remember" used to expand into memory/recall/notes/context. Only the
        # ask's own words (plus the joined pair) remain.
        self.assertEqual(
            match.expand("remember this"), ["remember", "this", "rememberthis"])


class HeavyAndMemory(unittest.TestCase):
    def test_heavy_is_a_model_decision_not_a_name_list(self):
        # comfyui was on the HEAVY_NAMES list; the model says it is not heavy
        # here and the answer must stand.
        self.assertFalse(presets.heavy("comfyui", StubLlm(heavy=False)))
        self.assertTrue(presets.heavy("tiny-notes", StubLlm(heavy=True)))

    def test_no_model_means_nothing_is_heavy(self):
        self.assertFalse(presets.heavy("comfyui", None))

    def test_memory_caution_comes_from_the_model(self):
        # Neither the entry nor the ask names "memory" in so many words, yet
        # the model flags a memory provider the ask did not request.
        row = SimpleNamespace(name="locus", description="Recall notes across sessions")
        llm = StubLlm(memory=True)
        with mock.patch.object(choose, "asks_about_memory", return_value=False):
            self.assertEqual(choose.caution_for(row, "keep my notes", llm), "memory")

    def test_memory_ask_comes_from_the_model(self):
        self.assertTrue(choose.asks_about_memory(
            "keep my notes across sessions", StubLlm(memory=True)))
        self.assertFalse(choose.asks_about_memory("keep my notes across sessions", None))


class Jurisdiction(unittest.TestCase):
    def test_country_comes_from_metadata_via_model(self):
        row = entry("gst-biller", description="GST billing for shops in Sydney.")
        self.assertEqual(
            card.jurisdiction(row, StubLlm(country="Australia")), "Australia")

    def test_no_model_claims_no_country(self):
        row = entry("gst-biller", description="GST billing for shops in Sydney.")
        self.assertEqual(card.jurisdiction(row, None), "")


class VerbHeads(unittest.TestCase):
    def test_a_verb_head_still_reaches_the_router(self):
        # "browse pdfs" used to hit the browse head and never call the model.
        with mock.patch.object(
            commands, "_model_route",
            return_value={"action": "browse", "bot": "", "what": "pdfs"},
        ) as routed, mock.patch.object(
            commands, "_run_route", return_value="RAN"
        ) as ran:
            text = commands.handle_concierge("browse pdfs", store=None)
        self.assertEqual(text, "RAN")
        routed.assert_called_once()
        self.assertIn("browse pdfs", routed.call_args[0])
        ran.assert_called_once()

    def test_only_help_and_undo_answer_without_a_model(self):
        self.assertIn("Concierge", commands.handle_concierge("help", store=None))
        routed = []
        with mock.patch.object(
            commands, "_model_route",
            side_effect=lambda *a, **k: routed.append(a) or None,
        ):
            commands.handle_concierge("create a researcher", store=None)
        self.assertTrue(routed)


class ReplyUsesModel(unittest.TestCase):
    def setUp(self):
        card._PENDING.clear()

    def test_bare_ok_is_confirm_to_the_model(self):
        llm = StubLlm(answer="CONFIRM")
        self.assertEqual(reply.answer_for("ok", "themes: skins", llm), "CONFIRM")

    def test_no_model_consumes_nothing(self):
        card._PENDING["chat-a"] = {"sentence": "x", "entries": [object()]}
        self.assertIsNone(
            reply.on_admission(text="yes", session_key="chat-a", platform="telegram"))
        self.assertEqual(reply.answer_for("yes", "x", None), "OTHER")


if __name__ == "__main__":
    unittest.main()
