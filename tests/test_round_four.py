"""Round four: gate the answer, honest connectors, real reset, clean partials, plain replies."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

commands = harness.load("commands")
lifecycle = harness.load("lifecycle")
state = harness.load("state")
card = harness.load("card")
shelf = harness.load("shelf")
search = harness.load("search")
router = harness.load("router")
choose = harness.load("choose")
training = harness.load("training")
improve = harness.load("improve")
presets = harness.load("presets")


class Memory:
    def __init__(self) -> None:
        self.data: dict = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value) -> None:
        self.data[key] = value


def store(*records):
    made = state.Store(backend=Memory())
    for record in records:
        made.add(record)
    return made


def bot(name, title="", role="", skills=None):
    return state.Installed(name=name, kind="bot", title=title or name,
                           profile=name, enabled=True, role=role,
                           skills=list(skills or []))


class FakeSeams:
    def __init__(self, homes: dict) -> None:
        self.homes = {name: pathlib.Path(path) for name, path in homes.items()}
        self.removed: list = []
        self.history: dict = {}

    def current_profile(self) -> str:
        return "default"

    def profile_home(self, name: str) -> pathlib.Path:
        return self.homes.get(name, pathlib.Path(tempfile.gettempdir()) / "gone" / name)

    def profile_history(self, name: str) -> dict:
        return self.history.get(name, {"sessions": 0, "memories": 0, "cron": 0})

    def remove_profile(self, name: str, yes: bool = True) -> None:
        self.removed.append(name)
        home = self.homes.pop(name, None)
        if home is not None and home.is_dir():
            import shutil
            shutil.rmtree(home)


class AnswerGate(unittest.TestCase):
    def setUp(self):
        self.saved_platform = commands._PLATFORM
        self.saved_answer = commands._PLATFORM_ANSWER
        self.saved_messaging = commands._messaging
        card._PENDING.clear()
        shelf._LAST.clear()

    def tearDown(self):
        commands._PLATFORM = self.saved_platform
        commands._PLATFORM_ANSWER = self.saved_answer
        commands._messaging = self.saved_messaging
        card._PENDING.clear()

    def test_yes_on_telegram_does_not_install_app_does(self):
        made = store(bot("inbox-bot"))
        with mock.patch.object(card, "handle", return_value="CARD ANSWER") as sent:
            card._PENDING["chat-x"] = {"sentence": "install pdf", "entries": ["one"], "target": ""}
            commands._PLATFORM = "telegram"
            commands._messaging = lambda: False
            text = commands.handle_concierge("yes", store=made, session_key="chat-x")
            self.assertIn("shared chat", text)
            self.assertEqual(sent.call_count, 0)
            # The owner's app answers the same card.
            card._PENDING["chat-x"] = {"sentence": "install pdf", "entries": ["one"], "target": ""}
            commands._PLATFORM = "app"
            text = commands.handle_concierge("yes", store=made, session_key="chat-x")
            self.assertEqual(text, "CARD ANSWER")
            self.assertEqual(sent.call_count, 1)
        # A safe answer still drops the card on a shared chat.
        card._PENDING["chat-x"] = {"sentence": "install pdf", "entries": ["one"], "target": ""}
        import importlib
        reply = harness.load("reply")
        result = reply.on_admission(text="no", session_key="chat-x", platform="telegram")
        self.assertIsNotNone(result)
        self.assertIn("Nothing installed", result["reply"])


class ConnectorsHonest(unittest.TestCase):
    def test_nothing_advertises_connectors_and_asks_are_honest(self):
        self.assertNotIn("connector", shelf.overview().lower())
        self.assertNotIn("connector", router.INSTRUCTIONS.lower().replace("connectors are", ""))
        # The install line specifically must not promise connectors.
        for line in router.INSTRUCTIONS.splitlines():
            if line.strip().startswith("install"):
                self.assertNotIn("connector", line.lower())
        self.assertNotIn("connector", choose.WHOLE_PROMPT.lower())
        rows = search.build()
        self.assertFalse(any(str(r.get("kind", "")).lower() == "connector" for r in rows))
        with mock.patch.object(search, "_connectors",
                               return_value=[{"kind": "connector", "name": "gmail",
                                              "description": "hosted", "payload": "gmail"}]):
            text = commands.handle_install("gmail", store=store())
            self.assertIn("does not install connectors", text.lower())
            self.assertIn("nothing was installed", text.lower())


class HireResetReal(unittest.TestCase):
    def test_preset_skills_survive_and_rule_is_gone(self):
        import os
        from unittest import mock as _mock

        tmp = pathlib.Path(tempfile.mkdtemp())
        bot_home = tmp / "profiles" / "researcher-bot"
        bot_home.mkdir(parents=True)
        (bot_home / "config.yaml").write_text("model: {}\n", encoding="utf-8")
        (bot_home / "SOUL.md").write_text("generic\n", encoding="utf-8")
        patcher = _mock.patch.dict(os.environ, {"HERMES_HOME": str(tmp)})
        patcher.start()
        self.addCleanup(patcher.stop)

        made = store()

        def fake_hire(sentence):
            from concierge_under_test import bots as _bots
            try:
                from concierge import bots as _bots2  # noqa
            except Exception:
                pass
            plan = harness.load("bots").spec(sentence)
            return plan, bot_home

        # A preset that really lands files, without network.
        def fake_apply(text, name, path):
            role = presets.detect(text) or presets.get("assistant")
            home = Path(str(path))
            for skill in list(role.bundled)[:2]:
                folder = home / "skills" / "misc" / skill
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "SKILL.md").write_text("x", encoding="utf-8")
            presets.write_soul(home, role)
            return ["preset line"]

        with _mock.patch.object(commands, "_apply_preset", side_effect=fake_apply):
            with _mock.patch.object(commands, "_inherit_plugins", return_value=[]):
                with _mock.patch.object(harness.load("seams"), "link_self_plugin", return_value=True):
                    text = commands.handle_hire("a researcher for papers", store=made, hire=fake_hire, known=[])
        self.assertIn("Created researcher-bot", text)
        record = made.find("researcher-bot", kind="bot")
        self.assertIsNotNone(record)
        # Hire recorded its stock, not just the profile.
        self.assertEqual(getattr(record, "role", ""), "researcher")
        self.assertTrue(list(getattr(record, "skills", []) or []))

        # Improve with a standing rule.
        class _KindLlm:
            def complete_structured(self, **kwargs):
                class _R:
                    text = '{"kind": "rule"}'
                return _R()

        class _Ctx:
            @property
            def llm(self):
                return _KindLlm()

        saved_ctx = commands._CTX
        commands._CTX = _Ctx()
        try:
            improved = commands.handle_improve("researcher-bot: always cite sources", store=made)
        finally:
            commands._CTX = saved_ctx
        self.assertIn("researcher-bot", improved)
        soul = (bot_home / "SOUL.md").read_text(encoding="utf-8")
        self.assertIn("always cite sources", soul)

        seams = FakeSeams({"researcher-bot": bot_home})
        reset_text = commands.handle_concierge("reset 1", store=made, seams=seams)
        self.assertIn("researcher-bot", reset_text)
        soul_after = (bot_home / "SOUL.md").read_text(encoding="utf-8")
        self.assertNotIn("always cite sources", soul_after)
        # Preset skills are back: the hire-time tree survived the reset.
        have = set(presets.verify(bot_home, presets.get("researcher")))
        self.assertTrue(have)


class PartialWrites(unittest.TestCase):
    def test_failed_copy_leaves_nothing_behind(self):
        import shutil as _shutil

        tmp = pathlib.Path(tempfile.mkdtemp())
        home = tmp / "profiles" / "demo-bot"
        (home / "skills").mkdir(parents=True)
        src = tmp / "src" / "pdf"
        src.mkdir(parents=True)
        (src / "SKILL.md").write_text("x", encoding="utf-8")

        item = improve.Item(kind="skill", name="pdf", path=src, source="bundled",
                            identifier="official/docs/pdf")
        real_copy = _shutil.copytree

        def flaky(*args, **kwargs):
            # Copy half, then fail: the classic partial write.
            target = pathlib.Path(args[1])
            target.mkdir(parents=True, exist_ok=True)
            (target / "half.txt").write_text("half", encoding="utf-8")
            raise OSError("disk hiccup")

        with mock.patch.object(_shutil, "copytree", side_effect=flaky):
            ok = improve._install_one("demo-bot", item, home=home)
        self.assertFalse(ok)
        target = home / "skills" / src.parent.name / "pdf"
        self.assertFalse(target.exists(), "half-written skill dir must be cleaned")
        # A retry starts clean instead of failing with FileExistsError.
        with mock.patch.object(_shutil, "copytree", side_effect=flaky) as _:
            ok2 = improve._install_one("demo-bot", item, home=home)
        self.assertFalse(ok2)
        self.assertFalse(target.exists())

        # Presets clean the same way and report one honest line.
        home2 = tmp / "profiles" / "bp-preset"
        home2.mkdir(parents=True)
        seams_mod = harness.load("seams")
        with mock.patch.object(seams_mod, "copy_bundled", return_value=[]):
            with mock.patch("shutil.copytree", side_effect=OSError("nope")):
                got = presets._copy_bundled(home2, ["pdf"])
        self.assertEqual(got, [])
        leftovers = list((home2 / "skills").rglob("*")) if (home2 / "skills").is_dir() else []
        self.assertEqual([p for p in leftovers if p.is_dir() and p.name == "pdf"], [])


class PlainReplies(unittest.TestCase):
    def test_dead_ends_point_forward_without_scolding(self):
        made = store(bot("inbox-bot"))
        no_text = commands.handle_concierge("no", store=made, session_key="quiet-1")
        self.assertIn("Nothing installed", no_text)
        self.assertIn("/concierge", no_text)
        num_text = commands.handle_concierge("2", store=made, session_key="quiet-2")
        self.assertIn("/concierge", num_text)
        self.assertNotIn("the list", num_text.lower())
        unknown = commands.handle_improve("no-such-bot: do things", store=store())
        self.assertIn("No bot called no-such-bot", unknown)
        self.assertIn("/concierge bots", unknown)
        need_number = commands.handle_concierge("fire", store=made)
        self.assertIn("Deleting a bot needs its number", need_number)
        self.assertNotIn("guess", need_number.lower())
        self.assertNotIn("#", need_number)
        saved = commands._is_bot_profile
        commands._is_bot_profile = lambda: True
        try:
            scold = commands.handle_hire("create a researcher", store=store())
        finally:
            commands._is_bot_profile = saved
        self.assertIn("Ask the owner", scold)
        self.assertNotIn("improve yourself", scold)


class SpokenBotName(unittest.TestCase):
    def test_writer_bot_matches_writer_bot(self):
        class FakeAnswer:
            def __init__(self, text):
                self.text = text

        class FakeLlm:
            def __init__(self, payload):
                self.payload = payload

            def complete_structured(self, **kwargs):
                import json
                return FakeAnswer(json.dumps(self.payload))

        llm = FakeLlm({"action": "improve", "bot": "writer bot", "what": "handle pdfs"})
        route = router.route("improve writer bot", here="", bots=["writer-bot"], llm=llm)
        self.assertEqual(route["bot"], "writer-bot")
        found, rest = training.guess_bot("writer bot always cite sources", ["writer-bot"])
        self.assertEqual(found, "writer-bot")
        self.assertEqual(rest, "always cite sources")


if __name__ == "__main__":
    unittest.main()
