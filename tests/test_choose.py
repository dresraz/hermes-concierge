"""The picker: the list stays lexical, the model only chooses from it."""

import unittest
from unittest import mock

from concierge import choose


class Row:
    def __init__(self, name, description="", kind="plugin", score=0.0):
        self.name = name
        self.description = description
        self.title = description
        self.kind = kind
        self.score = score


class FakeLlm:
    """Answers as the model would, and remembers what it was shown."""

    def __init__(self, pick):
        self.pick = pick
        self.seen = ""

    def complete_structured(self, **kwargs):
        self.seen = kwargs["instructions"]

        class Answer:
            text = '{"pick": "%s", "why": "test"}' % self.pick

        return Answer()


def options():
    return [
        Row("pdf", "Read and edit PDF files.", "skill", 5.0),
        Row("pdf-surgeon", "Rewrite text inside a PDF.", "plugin", 4.8),
        Row("tabella", "Spreadsheet work.", "plugin", 2.0),
    ]


class Choice(unittest.TestCase):
    def pick(self, ask, llm, rows):
        with mock.patch.object(choose, "shortlist", lambda *a, **k: rows):
            return choose.pick(ask, llm=llm, entries=[])

    def test_a_decisive_lead_is_taken_without_a_model_call(self):
        llm = FakeLlm("tabella")
        rows = [Row("pdf", "PDF files.", "skill", 20.0), Row("tabella", "Sheets.", "plugin", 2.0)]
        picked = self.pick("read pdf files", llm, rows)
        self.assertEqual(picked.name, "pdf")
        self.assertEqual(llm.seen, "")

    def test_a_tie_goes_to_the_model(self):
        llm = FakeLlm("pdf-surgeon")
        picked = self.pick("read pdf files", llm, options())
        self.assertEqual(picked.name, "pdf-surgeon")
        self.assertIn("pdf-surgeon [get]", llm.seen)

    def test_a_name_the_model_invented_is_refused(self):
        picked = self.pick("read pdf files", FakeLlm("super-pdf-pro"), options())
        self.assertIsNone(picked)

    def test_nothing_is_an_answer(self):
        self.assertIsNone(self.pick("teleport my dog to mars", FakeLlm("NOTHING"), options()))

    def test_the_prompt_shows_every_candidate_with_its_kind(self):
        llm = FakeLlm("pdf")
        self.pick("read pdf files", llm, options())
        self.assertIn("pdf [here]", llm.seen)
        self.assertIn("pdf-surgeon [get]", llm.seen)

    def test_no_model_and_no_decisive_lead_is_no_fit(self):
        self.assertIsNone(self.pick("read pdf files", None, options()))

    def test_an_empty_shortlist_is_no_fit(self):
        self.assertIsNone(self.pick("anything", FakeLlm("pdf"), []))
