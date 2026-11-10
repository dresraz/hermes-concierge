"""The picker: a wide menu for the model, an exact name taken without one."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

choose = harness.load("choose")


class Row:
    def __init__(self, name, description="", kind="plugin", score=0.0):
        self.name = name
        self.description = description
        self.title = description
        self.kind = kind
        self.score = score


class FakeLlm:
    """Answers as the model would, and remembers what it was shown."""

    def __init__(self, pick, tool=""):
        self.pick = pick
        self.tool = tool
        self.seen = ""
        self.seen_all = []

    def complete_structured(self, **kwargs):
        self.seen = kwargs["instructions"]
        self.seen_all.append(kwargs["instructions"])
        pick, tool = self.pick, self.tool

        class Answer:
            text = '{"pick": "%s", "tool": "%s", "why": "test", "memory": false, "heavy": false}' % (pick, tool)

        return Answer()


def options():
    return [
        Row("pdf", "Read and edit PDF files.", "skill", 5.0),
        Row("pdf-surgeon", "Rewrite text inside a PDF.", "plugin", 4.8),
        Row("tabella", "Spreadsheet work.", "plugin", 2.0),
    ]


class Choice(unittest.TestCase):
    def pick(self, ask, llm, rows, skills=None):
        with mock.patch.object(choose, "shortlist", lambda *a, **k: rows), \
             mock.patch.object(choose, "_skills", lambda: [] if skills is None else skills):
            return choose.pick(ask, llm=llm, entries=[])

    def test_a_name_asked_by_name_is_taken_without_a_pick_call(self):
        llm = FakeLlm("tabella")
        rows = [Row("pdf", "PDF files.", "skill", 20.0), Row("tabella", "Sheets.", "plugin", 2.0)]
        picked = self.pick("pdf", llm, rows)
        self.assertEqual(picked.name, "pdf")
        # The pick itself takes no model call; only the caution guard reads.
        for prompt in llm.seen_all:
            self.assertNotIn("Every entry in the Hermes marketplace", prompt)
            self.assertNotIn("Choose what answers the ask", prompt)
            self.assertNotIn("You are choosing one item from a shortlist", prompt)

    def test_the_model_is_shown_every_name_in_the_marketplace(self):
        llm = FakeLlm("pdf")
        picked = self.pick("read pdf files", llm, options())
        # The whole-list prompt carries the marketplace, not a shortlist; the
        # pick resolves against the index, so a name it invents is refused.
        self.assertTrue(picked is None or picked.name == "pdf")
        self.assertTrue(any(
            "Every entry in the Hermes marketplace" in prompt for prompt in llm.seen_all
        ))

    def test_the_model_may_pick_a_skill_that_was_not_on_the_shortlist(self):
        skills = [Row("arxiv", "Search arXiv papers.", "skill", 0.0)]
        picked = self.pick("find recent papers on rag", FakeLlm("arxiv"), [], skills=skills)
        self.assertEqual(picked.name, "arxiv")

    def test_a_name_the_model_invented_is_refused(self):
        self.assertIsNone(self.pick("read pdf files", FakeLlm("super-pdf-pro"), options()))

    def test_nothing_is_an_answer(self):
        self.assertIsNone(self.pick("teleport my dog to mars", FakeLlm("NOTHING"), options()))

    def test_built_in_is_an_answer(self):
        picked = self.pick("what is the weather", FakeLlm("BUILT_IN", "web search"), [])
        self.assertEqual(picked.kind, "builtin")
        self.assertEqual(picked.description, "web search")

    def test_no_model_and_no_decisive_lead_is_no_fit(self):
        self.assertIsNone(self.pick("read pdf files", None, options()))

    def test_an_empty_shortlist_without_a_model_is_no_fit(self):
        self.assertIsNone(self.pick("anything", None, []))
