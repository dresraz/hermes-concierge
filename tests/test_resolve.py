"""Name resolution is a model call over lists the plugin already has.

Typos ("obsdian"), spoken names ("writer bot") and phrases ("my researcher
bot") resolve to the listed name. Nothing is fuzzy-matched in code: the model
picks from the candidate list, and anything outside it is refused.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import harness  # noqa: E402

router = harness.load("router")
commands = harness.load("commands")
search = harness.load("search")
shelf = harness.load("shelf")
state = harness.load("state")


class FakeAnswer:
    def __init__(self, text):
        self.text = text


class FakeLlm:
    """Answers every model call with one fixed name, recording the prompt."""

    def __init__(self, name):
        self.name = name
        self.prompts = []

    def complete_structured(self, **kwargs):
        self.prompts.append(kwargs["instructions"])
        return FakeAnswer('{"name": "%s"}' % self.name)


class DispatchLlm:
    """Rule-vs-skill and name resolution share one stub in command tests."""

    def __init__(self, name):
        self.name = name
        self.calls = 0

    def complete_structured(self, **kwargs):
        self.calls += 1
        instructions = kwargs["instructions"]
        if "standing behavior" in instructions:
            return FakeAnswer('{"kind": "rule"}')
        if '"answer"' in instructions:
            # A pending-card answer: the model confirms.
            return FakeAnswer('{"answer": "CONFIRM", "name": "%s"}' % self.name)
        if "You decide what" in instructions:
            # The router: this stub only ever fires a spoken bot name.
            return FakeAnswer(
                '{"action": "fire", "bot": "researcher-bot", "what": "my researcher bot"}'
            )
        return FakeAnswer('{"name": "%s"}' % self.name)


class Ctx:
    def __init__(self, llm):
        self._llm = llm

    @property
    def llm(self):
        return self._llm


def with_llm(testcase, llm):
    saved = commands._CTX
    commands._CTX = Ctx(llm)
    testcase.addCleanup(lambda: setattr(commands, "_CTX", saved))


def store(*records):
    made = state.Store(backend=_Memory())
    for record in records:
        made.add(record)
    return made


class _Memory:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


THINGS = [
    {"kind": "skill", "name": "obsidian", "description": "Notes.", "payload": {}},
    {"kind": "skill", "name": "writer-bot", "description": "Writes.", "payload": {}},
    {"kind": "skill", "name": "notes", "description": "Notes.", "payload": {}},
]


class ResolveName(unittest.TestCase):
    def test_a_typo_resolves_to_the_listed_name(self):
        llm = FakeLlm("obsidian")
        with mock.patch.object(search, "build", return_value=THINGS):
            self.assertEqual(router.resolve_name("obsdian", "thing", llm), "obsidian")
        # The model chose from the list, not from thin air.
        self.assertIn("obsidian", llm.prompts[0])
        self.assertIn("misspell", llm.prompts[0].lower())

    def test_a_spoken_name_resolves_to_its_hyphens(self):
        with mock.patch.object(search, "build", return_value=THINGS):
            self.assertEqual(
                router.resolve_name("writer bot", "thing", FakeLlm("writer-bot")),
                "writer-bot",
            )

    def test_my_researcher_bot_resolves(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "profiles" / "researcher-bot").mkdir(parents=True)
        (tmp / "profiles" / "researcher-bot" / "config.yaml").write_text(
            "model: {}\n", encoding="utf-8"
        )
        patcher = mock.patch.dict(os.environ, {"HERMES_HOME": str(tmp)})
        patcher.start()
        self.addCleanup(patcher.stop)
        llm = FakeLlm("researcher-bot")
        self.assertEqual(
            router.resolve_name("my researcher bot", "bot", llm), "researcher-bot"
        )

    def test_an_unknown_name_still_returns_empty(self):
        with mock.patch.object(search, "build", return_value=THINGS):
            self.assertEqual(
                router.resolve_name("obsdian", "thing", FakeLlm("ghost-xyz")), ""
            )

    def test_a_name_outside_the_list_is_refused(self):
        llm = FakeLlm("obsidian")
        with mock.patch.object(search, "build", return_value=THINGS):
            self.assertEqual(router.resolve_name("", "thing", llm), "")
            self.assertEqual(router.resolve_name("obsdian", "nope", llm), "")

    def test_no_model_means_no_resolution(self):
        self.assertEqual(router.resolve_name("obsdian", "thing", None), "")

    def test_only_plausible_names_go_on_the_call(self):
        rows = [
            {"kind": "skill", "name": "design-{}".format(i), "description": "", "payload": {}}
            for i in range(250)
        ]
        rows.append({"kind": "skill", "name": "design-pro", "description": "", "payload": {}})
        with mock.patch.object(search, "build", return_value=rows):
            names = router._thing_candidates("designpro")
            llm = FakeLlm("design-pro")
            resolved = router.resolve_name("designpro", "thing", llm)
        self.assertLessEqual(len(names), 201)
        self.assertIn("design-pro", names)
        self.assertEqual(resolved, "design-pro")
        self.assertLess(len(llm.prompts[0]), 6000)


class InstallReceipt(unittest.TestCase):
    def test_install_reads_obsdian_as_obsidian(self):
        card = harness.load("card")
        entry = SimpleNamespace(
            name="obsidian", title="Obsidian", description="Reads Obsidian notes.",
            capabilities={}, category="notes", tier="official",
            repo="https://github.com/example/obsidian", sha="a" * 40, version="1.0.0",
        )
        seen = []
        with_llm(self, DispatchLlm("obsidian"))
        with mock.patch.object(search, "build", return_value=THINGS), \
             mock.patch.object(card, "_install", lambda *a, **k: seen.append(1) or "ok\n"), \
             mock.patch.object(harness.load("seams"), "declared_deps_remote", lambda entry: []):
            text = commands.handle_install("obsdian", catalog=[entry], session_key="note-1")
        card.forget("note-1")
        self.assertIn("Read obsdian as obsidian.", text.splitlines()[0])
        self.assertEqual(seen, [1])


class FireSpoken(unittest.TestCase):
    def test_fire_my_researcher_bot(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        home = tmp / "researcher-bot"
        home.mkdir(parents=True)
        (home / "SOUL.md").write_text("x\n", encoding="utf-8")
        disks = tmp / "profiles" / "researcher-bot"
        disks.mkdir(parents=True)
        (disks / "config.yaml").write_text("model: {}\n", encoding="utf-8")
        patcher = mock.patch.dict(os.environ, {"HERMES_HOME": str(tmp)})
        patcher.start()
        self.addCleanup(patcher.stop)

        class Seams:
            def profile_home(self, name):
                return home

            def profile_history(self, name):
                return {"sessions": 0, "memories": 0, "cron": 0}

            def remove_profile(self, name, yes=True):
                import shutil

                shutil.rmtree(home, ignore_errors=True)

        made = store(state.Installed(name="researcher-bot", kind="bot",
                                     title="research", profile="researcher-bot",
                                     enabled=True))
        with_llm(self, DispatchLlm("researcher-bot"))
        text = commands.handle_concierge(
            "fire my researcher bot", store=made, seams=Seams()
        )
        self.assertIn("Read my researcher bot as researcher-bot.", text.splitlines()[0])
        self.assertIn("Deleted researcher-bot", text)


class ImproveSpoken(unittest.TestCase):
    def test_improve_resolves_before_the_no(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        bot = tmp / "profiles" / "researcher-bot"
        bot.mkdir(parents=True)
        (bot / "config.yaml").write_text("model: {}\n", encoding="utf-8")
        patcher = mock.patch.dict(os.environ, {"HERMES_HOME": str(tmp)})
        patcher.start()
        self.addCleanup(patcher.stop)
        with_llm(self, DispatchLlm("researcher-bot"))
        text = commands.handle_improve("my researcher bot: always cite sources",
                                       store=store())
        self.assertIn("Read ", text.splitlines()[0])
        self.assertIn("researcher-bot", text.splitlines()[0])
        self.assertIn("Improved researcher-bot", text)


class OneSearch(unittest.TestCase):
    ROWS = [
        {"kind": "skill", "name": "design-{}".format(i),
         "description": "Design skill {}.".format(i), "payload": {}}
        for i in range(8)
    ]

    class FakeIndex:
        def __init__(self, rows):
            self.rows = rows

        def search(self, query, limit=20):
            query = query.lower()
            hits = [dict(r) for r in self.rows
                    if query in r["name"].lower()
                    or query in r.get("description", "").lower()]
            return hits[:limit]

    def setUp(self):
        self.saved = search._INDEX
        search._INDEX = self.FakeIndex(list(self.ROWS))
        self.addCleanup(lambda: setattr(search, "_INDEX", self.saved))

    def test_install_and_browse_share_one_candidate_list(self):
        names = [row["name"] for row in search.candidates("design", limit=8)]
        shown = [row["name"] for row in shelf.items("design") if row["kind"] != "bot"]
        self.assertEqual(names, shown)

        choose = harness.load("choose")
        market = harness.load("market")
        offered = []
        with_llm(self, DispatchLlm(""))
        with mock.patch.object(choose, "pick", return_value=None), \
             mock.patch.object(market, "handle", lambda *a, **k: offered.append(a[0]) or "OFFER"), \
             mock.patch.object(search, "build", return_value=list(self.ROWS)):
            text = commands.handle_install("design", catalog=[], session_key="agree-1")
        self.assertEqual(text, "OFFER")
        self.assertEqual(offered, [names[0]])
        self.assertIn(offered[0], shown)


if __name__ == "__main__":
    unittest.main()
