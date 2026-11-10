"""Minimal behaviour: one model call, plain execution, no hidden lists."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from concierge import commands, presets, router, search, store, text


class Answer:
    def __init__(self, payload):
        self.text = json.dumps(payload)


class Llm:
    def __init__(self, payload):
        self.payload = payload
        self.seen = []

    def complete_structured(self, **kwargs):
        self.seen.append(kwargs.get("instructions", ""))
        return Answer(self.payload)


def _ctx(payload):
    class Ctx:
        home_path = ""

        @property
        def llm(self):
            return Llm(payload)

    return Ctx()


class Text(unittest.TestCase):
    def test_words_and_slug(self):
        self.assertEqual(text.words("Writer Bot!"), ["writer", "bot"])
        self.assertEqual(text.slug("Writer Bot!"), "writer-bot")


class Router(unittest.TestCase):
    def setUp(self):
        self.real_names = search.names_for_model
        search.names_for_model = lambda query, limit=200: ["obsidian", "pdf"]

    def tearDown(self):
        search.names_for_model = self.real_names

    def test_full_plan_comes_back(self):
        llm = Llm({"action": "install", "bot": "", "thing": "obsidian",
                   "role": "", "answer": "OTHER", "what": "obsidian"})
        plan = router.route("install obsdian", bots=[], llm=llm)
        self.assertEqual(plan["action"], "install")
        self.assertEqual(plan["thing"], "obsidian")

    def test_bad_action_is_no_plan(self):
        llm = Llm({"action": "format_disk", "bot": "", "thing": "",
                   "role": "", "answer": "OTHER", "what": ""})
        self.assertIsNone(router.route("x", bots=[], llm=llm))

    def test_no_model_is_no_plan(self):
        self.assertIsNone(router.route("anything", bots=[], llm=None))


class Presets(unittest.TestCase):
    def test_roles_are_data(self):
        self.assertIn("researcher", presets.ROLES)
        self.assertIn("designer", presets.ROLES)
        self.assertTrue(all(presets.skills_for(name) for name in presets.names()))

    def test_souls_stay_short_plain_and_generic(self):
        for name in presets.names():
            soul = presets.soul_for(name)
            self.assertTrue(soul, name)
            self.assertLessEqual(len(soul), 500, name)
            self.assertNotIn("\u2014", soul, name)
            self.assertNotIn("http", soul, name)
            lowered = soul.lower()
            self.assertNotIn("each morning", lowered, name)
            self.assertNotIn("every morning", lowered, name)
            for row in presets.skills_for(name):
                if "-" in row:
                    self.assertNotIn(row, soul, name)
        self.assertEqual(presets.soul_for("nope"), "")


class Tables(unittest.TestCase):
    def test_only_six_anchored_patterns(self):
        import ast

        root = pathlib.Path(__file__).resolve().parents[1]
        allowed = {"_SEARCH_RX", "_UNDO_RX", "_BOTS_RX", "_INSTALL_RX", "_YES_RX", "_NO_RX"}
        names = set()
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in tree.body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    name = getattr(node.targets[0], "id", "")
                    if name.endswith("_RX"):
                        names.add(name)
                        pattern = node.value.args[0].value
                        self.assertTrue(pattern.startswith("^"), "{}:{}".format(path.name, pattern))
                        self.assertNotIn(".*", pattern.replace("(.*)$", ""), path.name)
        self.assertEqual(names, allowed)

    def test_only_vocabulary_tables(self):
        import ast

        root = pathlib.Path(__file__).resolve().parents[1]
        # Vocabulary, not phrasing: the action names, the answers, and the names
        # of the surfaces the owner is actually sitting at.
        allowed = {"ACTIONS", "OUTCOMES", "_LOCAL_SURFACES"}
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in tree.body:
                if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                    continue
                name = getattr(node.targets[0], "id", "")
                if not name.isupper():
                    continue
                value = node.value
                if isinstance(value, ast.Call) and getattr(value.func, "id", "") in ("frozenset", "set", "tuple"):
                    value = value.args[0] if value.args else None
                if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
                    parts = value.elts
                    if len(parts) >= 3 and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in parts):
                        self.assertIn(name, allowed, "{}:{}".format(path.name, name))


class Flows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = self.tmp.name
        commands._CTX = None
        commands._PLATFORM = "test"

    def tearDown(self):
        if self.saved is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self.saved
        commands._CTX = None
        self.tmp.cleanup()

    def test_overview_and_help_need_no_model(self):
        self.assertIn("On the shelf", commands.handle_concierge("", session_key="t1"))
        self.assertIn("One sentence", commands.handle_concierge("help", session_key="t2"))

    def test_nothing_fits_says_so(self):
        commands._CTX = _ctx({"action": "none", "bot": "", "thing": "",
                              "role": "", "answer": "OTHER", "heavy": False, "what": ""})
        out = commands.handle_concierge("book me a flight", session_key="t3")
        self.assertIn("Nothing here fits", out)

    def test_install_undo_cycle(self):
        created = []

        def fake_install(name, profile=""):
            folder = pathlib.Path(self.tmp.name) / "skills" / name
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "SKILL.md").write_text("# x")
            created.append(str(folder))
            return (True, str(folder), "ok")

        commands._CTX = _ctx({"action": "install", "bot": "", "thing": "pdf",
                              "role": "", "answer": "OTHER", "what": "pdf"})
        real_skills = search.skills
        real_plugins = search.plugins
        real_connectors = search.connectors
        real_names = search.names_for_model
        search.skills = lambda: [{"name": "pdf", "description": "read pdfs", "source": "x"}]
        search.plugins = lambda: []
        search.connectors = lambda: []
        search.names_for_model = lambda query, limit=200: ["pdf"]
        real_install = store.install_skill
        store.install_skill = fake_install
        try:
            out = commands.handle_concierge("install pdf", session_key="t4")
            self.assertIn("Installed skill pdf", out)
            self.assertTrue(pathlib.Path(created[0]).exists())
            out2 = commands.handle_concierge("undo", session_key="t5")
            self.assertIn("Undone: pdf", out2)
            self.assertFalse(pathlib.Path(created[0]).exists())
        finally:
            search.skills = real_skills
            search.plugins = real_plugins
            search.connectors = real_connectors
            search.names_for_model = real_names
            store.install_skill = real_install

    def test_install_into_unknown_bot_is_refused(self):
        commands._CTX = _ctx({"action": "install", "bot": "ghost-bot", "thing": "pdf",
                              "role": "", "answer": "OTHER", "what": "pdf"})
        real_skills = search.skills
        real_plugins = search.plugins
        real_connectors = search.connectors
        real_names = search.names_for_model
        real_bots = commands._bot_names
        search.skills = lambda: [{"name": "pdf", "description": "read pdfs", "source": "x"}]
        search.plugins = lambda: []
        search.connectors = lambda: []
        search.names_for_model = lambda query, limit=200: ["pdf"]
        commands._bot_names = lambda: ["researcher-bot"]
        try:
            out = commands.handle_concierge("add pdf to ghost-bot", session_key="t6")
            self.assertIn("No bot called ghost-bot", out)
        finally:
            search.skills = real_skills
            search.plugins = real_plugins
            search.connectors = real_connectors
            search.names_for_model = real_names
            commands._bot_names = real_bots

    def test_install_crash_is_an_honest_no(self):
        def boom(name, profile=""):
            raise RuntimeError("simulated failure")

        commands._CTX = _ctx({"action": "install", "bot": "", "thing": "pdf",
                              "role": "", "answer": "OTHER", "what": "pdf"})
        real_skills = search.skills
        real_plugins = search.plugins
        real_connectors = search.connectors
        real_names = search.names_for_model
        search.skills = lambda: [{"name": "pdf", "description": "read pdfs", "source": "x"}]
        search.plugins = lambda: []
        search.connectors = lambda: []
        search.names_for_model = lambda query, limit=200: ["pdf"]
        real_install = store.install_skill
        store.install_skill = boom
        try:
            out = commands.handle_concierge("install pdf", session_key="t7")
            self.assertIn("did not install", out)
        finally:
            search.skills = real_skills
            search.plugins = real_plugins
            search.connectors = real_connectors
            search.names_for_model = real_names
            store.install_skill = real_install


class OfflineHeads(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = self.tmp.name
        commands._CTX = None
        commands._PLATFORM = "test"
        self._real = (search.skills, search.plugins, search.connectors,
                      search.names_for_model, store.install_skill,
                      store.has_bot_record, store.delete_bot, commands._bot_names)
        search.skills = lambda: [{"name": "pdf", "description": "read pdfs", "source": "x"}]
        search.plugins = lambda: []
        search.connectors = lambda: []
        search.names_for_model = lambda query, limit=200: ["pdf"]

    def tearDown(self):
        (search.skills, search.plugins, search.connectors,
         search.names_for_model, store.install_skill,
         store.has_bot_record, store.delete_bot,
         commands._bot_names) = self._real
        commands._PENDING.clear()
        if self.saved is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self.saved
        commands._CTX = None
        self.tmp.cleanup()

    def test_search_words_browse_without_model(self):
        for sentence in ("search pdf", "find pdf", "look for pdf", "lookup pdf", "searching pdf"):
            out = commands.handle_concierge(sentence, session_key="h1")
            self.assertIn("1. pdf (skill)", out, sentence)
        out = commands.handle_concierge("search", session_key="h2")
        self.assertIn("Look through what?", out)

    def test_undo_and_bots_words_need_no_model(self):
        for sentence in ("take it back", "revert", "take that back"):
            out = commands.handle_concierge(sentence, session_key="h3")
            self.assertIn("Nothing to undo", out, sentence)
        commands._bot_names = lambda: ["researcher-bot"]
        for sentence in ("my bots", "list bots", "show my bots"):
            out = commands.handle_concierge(sentence, session_key="h4")
            self.assertIn("researcher-bot", out, sentence)

    def test_install_name_works_without_model(self):
        created = []
        store.install_skill = lambda name, profile="": created.append(name) or (True, "/x/" + name, "ok")
        out = commands.handle_concierge("install pdf", session_key="h5")
        self.assertIn("Installed skill pdf", out)
        self.assertEqual(created, ["pdf"])
        out = commands.handle_concierge("install zzyzx", session_key="h6")
        self.assertIn('Nothing here fits "zzyzx"', out)

    def test_present_skill_never_reinstalls(self):
        calls = []
        store.install_skill = lambda name, profile="": calls.append(name) or (True, "/x/" + name, "ok")
        real_find = store.find_skill_dir
        store.find_skill_dir = lambda home, name: "/x/pdf"
        try:
            out = commands.handle_concierge("install pdf", session_key="h7")
            self.assertIn("pdf is already here", out)
            self.assertEqual(calls, [])
        finally:
            store.find_skill_dir = real_find

    def test_plan_install_into_other_bot_refused_in_bot_mode(self):
        real_profile = commands._is_bot_profile
        real_current = commands._current_profile
        commands._is_bot_profile = lambda: True
        commands._current_profile = lambda: "researcher-bot"
        commands._CTX = _ctx({"action": "install", "bot": "coder-bot", "thing": "github",
                              "role": "", "answer": "OTHER", "heavy": False, "what": "give coder-bot github"})
        try:
            out = commands.handle_concierge("give coder-bot the github skill", session_key="h8")
            self.assertIn("only change itself", out)
        finally:
            commands._is_bot_profile = real_profile
            commands._current_profile = real_current

    def test_plan_install_stays_in_bot_without_named_bot(self):
        real_profile = commands._is_bot_profile
        real_current = commands._current_profile
        real_bots = commands._bot_names
        commands._is_bot_profile = lambda: True
        commands._current_profile = lambda: "researcher-bot"
        commands._bot_names = lambda: ["researcher-bot"]
        store.install_skill = lambda name, profile="": (True, "/x/" + name, "ok")
        commands._CTX = _ctx({"action": "install", "bot": "", "thing": "pdf",
                              "role": "", "answer": "OTHER", "heavy": False, "what": "add pdf"})
        try:
            out = commands.handle_concierge("add pdf here", session_key="h9")
            self.assertIn("researcher-bot", out)
        finally:
            commands._is_bot_profile = real_profile
            commands._current_profile = real_current
            commands._bot_names = real_bots

    def test_tokenizer_splits_camel_and_folds(self):
        self.assertEqual(text.words("blogWatcher"), ["blog", "watcher"])
        self.assertEqual(text.words("read PDFs,"), ["read", "pdfs"])
        self.assertIn("meeting", search._tokens("meetings"))
        self.assertIn("mexic", search._tokens("mexico"))
        self.assertIn("mexic", search._tokens("mexican"))
        self.assertIn("summa", search._tokens("summaries"))
        self.assertIn("summa", search._tokens("summarize"))

    def test_yes_no_answer_pending_without_model(self):
        store.has_bot_record = lambda name: True
        store.delete_bot = lambda name: (0, "ok")
        commands._bot_names = lambda: ["x-bot"]
        commands._PENDING["k1"] = {"key": "fire:x-bot", "summary": "delete x-bot",
                                   "bot": "x-bot", "confirmed": True}
        out = commands.handle_concierge("yep", session_key="k1")
        self.assertIn("Deleted x-bot", out)
        commands._PENDING["k2"] = {"key": "fire:x-bot", "summary": "delete x-bot",
                                   "bot": "x-bot", "confirmed": True}
        out = commands.handle_concierge("nah", session_key="k2")
        self.assertIn("x-bot is still here", out)
        out = commands.handle_concierge("no", session_key="k3")
        self.assertIn("Nothing is waiting", out)

    def test_wrong_digit_does_not_confirm_delete(self):
        deleted = []
        store.has_bot_record = lambda name: True
        store.delete_bot = lambda name: deleted.append(name) or (0, "ok")
        commands._bot_names = lambda: ["x-bot", "y-bot"]
        commands._PENDING["k9"] = {"key": "fire:y-bot", "summary": "delete y-bot",
                                   "bot": "y-bot", "confirmed": True}
        out = commands.handle_concierge("9999", session_key="k9")
        self.assertIn("That deletes y-bot", out)
        self.assertEqual(deleted, [])
        out = commands.handle_concierge("2", session_key="k9")
        self.assertIn("Deleted y-bot", out)
        self.assertEqual(deleted, ["y-bot"])

    def test_fire_prompt_clears_browse_rows(self):
        installed = []
        store.install_skill = lambda name, profile="": installed.append(name) or (True, "/x/" + name, "ok")
        store.has_bot_record = lambda name: True
        store.delete_bot = lambda name: (0, "ok")
        commands._bot_names = lambda: ["x-bot"]
        real_candidates = search.candidates
        search.candidates = lambda query, limit=10: [{"name": "pdf", "description": "read", "source": "x", "kind": "skill"}]
        try:
            out = commands.handle_concierge("browse pdf", session_key="k10")
            self.assertIn("1. pdf (skill)", out)
            commands._CTX = _ctx({"action": "fire", "bot": "x-bot", "thing": "",
                                  "role": "", "answer": "OTHER", "heavy": False, "what": "fire x-bot"})
            out = commands.handle_concierge("fire x-bot", session_key="k10")
            self.assertIn("To delete", out)
            out = commands.handle_concierge("1", session_key="k10")
            self.assertIn("Deleted x-bot", out)
            self.assertEqual(installed, [])
        finally:
            search.candidates = real_candidates
            import importlib

            importlib.reload(commands)

    def test_create_uses_core_clone_and_leaves_auth_json_out(self):
        home = pathlib.Path(self.tmp.name)
        made = []

        def fake_run(args, target, timeout=180):
            if args[:3] == ["hermes", "profile", "create"]:
                bot = home / "profiles" / args[3]
                bot.mkdir(parents=True, exist_ok=True)
                (bot / ".env").write_text("OPENROUTER_API_KEY=kept\n", encoding="utf-8")
                (bot / "auth.json").write_text('{"openai":{"access_token":"one-time"}}', encoding="utf-8")
                made.append(args)
            return (0, "ok")

        real_run = store._run
        store._run = fake_run
        try:
            ok, _out, _done, _failed = store.create_bot("probe-bot", [])
            self.assertTrue(ok)
            self.assertIn("--clone", made[0])
            self.assertFalse((home / "profiles" / "probe-bot" / "auth.json").exists())
            self.assertTrue((home / "profiles" / "probe-bot" / ".env").exists())
        finally:
            store._run = real_run

    def test_create_writes_the_preset_soul_not_the_owners(self):
        home = pathlib.Path(self.tmp.name)
        (home / ".env").write_text("OPENROUTER_API_KEY=kept\n", encoding="utf-8")

        def fake_run(args, target, timeout=180):
            if args[:3] == ["hermes", "profile", "create"]:
                bot = home / "profiles" / args[3]
                bot.mkdir(parents=True, exist_ok=True)
                (bot / "SOUL.md").write_text("owner private stuff\n", encoding="utf-8")
            return (0, "ok")

        real_run = store._run
        store._run = fake_run
        try:
            ok, _out, _done, _failed = store.create_bot("soul-bot", [], soul=presets.soul_for("writer"))
            self.assertTrue(ok)
            text = (home / "profiles" / "soul-bot" / "SOUL.md").read_text(encoding="utf-8")
            self.assertIn("writing bot", text)
            self.assertNotIn("owner private stuff", text)
        finally:
            store._run = real_run

    def test_hook_refuses_a_named_messaging_surface(self):
        deleted = []
        store.has_bot_record = lambda name: True
        store.delete_bot = lambda name: deleted.append(name) or (0, "ok")
        commands._bot_names = lambda: ["x-bot"]
        commands._PENDING["h3"] = {"key": "fire:x-bot", "summary": "delete x-bot",
                                   "bot": "x-bot", "confirmed": True}
        self.assertIsNone(commands.on_admission(text="yes", session_key="h3", platform="telegram"))
        self.assertIsNone(commands.on_admission(text="yes", session_key="h3", platform="something-new"))
        self.assertEqual(deleted, [])
        out = commands.on_admission(text="yes", session_key="h3", platform="desktop")
        self.assertEqual(out.get("action"), "handled")
        self.assertEqual(deleted, ["x-bot"])
        commands._PENDING.clear()

    def test_hook_answers_a_pending_delete_only(self):
        deleted = []
        store.has_bot_record = lambda name: True
        store.delete_bot = lambda name: deleted.append(name) or (0, "ok")
        commands._bot_names = lambda: ["x-bot"]
        commands._PENDING["h1"] = {"key": "fire:x-bot", "summary": "delete x-bot",
                                   "bot": "x-bot", "confirmed": True}
        out = commands.on_admission(text="yes", session_key="h1")
        self.assertEqual(out.get("action"), "handled")
        self.assertIn("Deleted x-bot", out.get("reply", ""))
        self.assertEqual(deleted, ["x-bot"])

    def test_hook_leaves_normal_chat_alone(self):
        commands._bot_names = lambda: ["x-bot"]
        commands._PENDING["h2"] = {"key": "fire:x-bot", "summary": "delete x-bot",
                                   "bot": "x-bot", "confirmed": True}
        self.assertIsNone(commands.on_admission(text="write me a poem", session_key="h2"))
        self.assertIsNone(commands.on_admission(text="yes", session_key="nobody"))
        self.assertIsNone(commands.on_admission(text="", session_key="h2"))
        commands._PENDING.clear()

    def test_push_refuses_non_dict_and_undo_skips_junk(self):
        self.assertFalse(store.push(None))
        self.assertFalse(store.push("junk"))
        self.assertFalse(store.push(42))
        stack_file = pathlib.Path(self.tmp.name) / "cache" / "concierge" / "undo.json"
        stack_file.parent.mkdir(parents=True, exist_ok=True)
        stack_file.write_text(json.dumps(["junk", 42, None]))
        out = commands.handle_concierge("undo", session_key="k11")
        self.assertIn("Cleared an unreadable receipt", out)
        out = commands.handle_concierge("undo", session_key="k12")
        self.assertIn("Nothing to undo", out)

    def test_hardlinked_soul_refused(self):
        home = pathlib.Path(self.tmp.name)
        soul = home / "SOUL.md"
        soul.write_text("base\n")
        link = home / "linked.md"
        try:
            os.link(soul, home / "SOUL.md.concierge-backup")
        except Exception:
            self.skipTest("hardlinks unavailable")
        store.push({"kind": "rule", "name": "default", "paths": [], "profile": "default",
                    "soul_path": str(soul), "soul_backup": str(home / "SOUL.md.concierge-backup"),
                    "soul_existed": True})
        out = commands.handle_concierge("undo", session_key="k13")
        self.assertIn("points outside this home", out)
        self.assertEqual(soul.read_text(), "base\n")

    def test_cross_profile_soul_refused(self):
        home = pathlib.Path(self.tmp.name)
        other = home / "profiles" / "other-bot"
        (other).mkdir(parents=True, exist_ok=True)
        victim = other / "SOUL.md"
        victim.write_text("victim\n")
        store.push({"kind": "rule", "name": "x-bot", "paths": [], "profile": "x-bot",
                    "soul_path": str(victim), "soul_backup": "", "soul_existed": True})
        out = commands.handle_concierge("undo", session_key="k14")
        self.assertIn("points outside this home", out)
        self.assertEqual(victim.read_text(), "victim\n")

    def test_improve_rule_is_single_line(self):
        written = {}

        def _fake_add(bot, sentence):
            written["s"] = sentence
            return (True, "", "")

        real_add = store.add_rule
        store.add_rule = _fake_add
        commands._bot_names = lambda: ["x-bot"]
        try:
            commands._CTX = _ctx({"action": "improve", "bot": "x-bot", "thing": "",
                                  "role": "", "answer": "OTHER", "heavy": False,
                                  "what": "line one\n- injected\n## forged"})
            out = commands.handle_concierge("do evil", session_key="k15")
            self.assertNotIn("\n- injected", written.get("s", ""))
            self.assertLessEqual(len(written.get("s", "")), 300)
        finally:
            store.add_rule = real_add


class FireConfirm(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.saved = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = self.tmp.name
        commands._CTX = None

    def tearDown(self):
        if self.saved is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self.saved
        commands._CTX = None
        commands._PENDING.clear()
        self.tmp.cleanup()

    def test_fire_needs_confirm_answer(self):
        deleted = []
        commands._bot_names = lambda: ["researcher-bot"]
        store.push({"kind": "bot", "name": "researcher-bot", "paths": [], "profile": "researcher-bot", "role": "researcher"})
        real_delete = store.delete_bot
        store.delete_bot = lambda name: deleted.append(name) or (0, "ok")
        try:
            commands._CTX = _ctx({"action": "fire", "bot": "researcher-bot", "thing": "",
                                  "role": "", "answer": "OTHER", "heavy": False, "what": "fire researcher-bot"})
            first = commands.handle_concierge("fire researcher-bot", session_key="f1")
            self.assertIn("To delete", first)
            self.assertEqual(deleted, [])
            commands._CTX = _ctx({"action": "fire", "bot": "researcher-bot", "thing": "",
                                  "role": "", "answer": "CONFIRM", "heavy": False, "what": "yes"})
            second = commands.handle_concierge("yes", session_key="f1")
            self.assertIn("Deleted researcher-bot", second)
            self.assertEqual(deleted, ["researcher-bot"])
        finally:
            store.delete_bot = real_delete
            import importlib

            importlib.reload(commands)


    def test_fire_repeat_command_confirms(self):
        deleted = []
        commands._bot_names = lambda: ["researcher-bot"]
        store.push({"kind": "bot", "name": "researcher-bot", "paths": [], "profile": "researcher-bot", "role": "researcher"})
        real_delete = store.delete_bot
        real_record = store.has_bot_record
        store.delete_bot = lambda name: deleted.append(name) or (0, "ok")
        store.has_bot_record = lambda name: True
        try:
            commands._CTX = _ctx({"action": "fire", "bot": "researcher-bot", "thing": "",
                                  "role": "", "answer": "OTHER", "heavy": False, "what": "fire researcher-bot"})
            first = commands.handle_concierge("fire researcher-bot", session_key="f3")
            self.assertIn("To delete", first)
            self.assertEqual(deleted, [])
            second = commands.handle_concierge("fire 1 researcher-bot", session_key="f3")
            self.assertIn("Deleted researcher-bot", second)
            self.assertEqual(deleted, ["researcher-bot"])
        finally:
            store.delete_bot = real_delete
            store.has_bot_record = real_record
            import importlib

            importlib.reload(commands)

    def test_fire_digit_confirms(self):
        deleted = []
        commands._bot_names = lambda: ["researcher-bot"]
        store.push({"kind": "bot", "name": "researcher-bot", "paths": [], "profile": "researcher-bot", "role": "researcher"})
        real_delete = store.delete_bot
        real_record = store.has_bot_record
        store.delete_bot = lambda name: deleted.append(name) or (0, "ok")
        store.has_bot_record = lambda name: True
        try:
            commands._CTX = _ctx({"action": "fire", "bot": "researcher-bot", "thing": "",
                                  "role": "", "answer": "OTHER", "heavy": False, "what": "fire researcher-bot"})
            first = commands.handle_concierge("fire researcher-bot", session_key="f4")
            self.assertIn("To delete", first)
            commands._CTX = None
            second = commands.handle_concierge("1", session_key="f4")
            self.assertIn("Deleted researcher-bot", second)
            self.assertEqual(deleted, ["researcher-bot"])
        finally:
            store.delete_bot = real_delete
            store.has_bot_record = real_record
            import importlib

            importlib.reload(commands)

    def test_fire_without_receipt_is_refused(self):
        commands._bot_names = lambda: ["researcher-bot", "stranger-bot"]
        try:
            commands._CTX = _ctx({"action": "fire", "bot": "stranger-bot", "thing": "",
                                  "role": "", "answer": "OTHER", "what": "fire 2 stranger-bot"})
            out = commands.handle_concierge("fire 2 stranger-bot", session_key="f2")
            self.assertIn("did not create stranger-bot", out)
        finally:
            import importlib

            importlib.reload(commands)


class UndoRule(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.saved = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = self.tmp.name
        commands._CTX = None
        commands._PENDING.clear()

    def tearDown(self):
        if self.saved is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self.saved
        commands._CTX = None
        commands._PENDING.clear()
        self.tmp.cleanup()

    def test_rule_without_prior_soul_undoes_clean(self):
        soul = pathlib.Path(self.tmp.name) / "SOUL.md"
        self.assertFalse(soul.exists())
        ok, backup, note = store.add_rule("default", "always cite sources")
        self.assertTrue(ok)
        self.assertTrue(soul.exists())
        self.assertEqual(backup, "")
        store.push({"kind": "rule", "name": "default", "paths": [], "profile": "default",
                    "soul_path": str(soul), "soul_backup": "", "soul_existed": False})
        commands._CTX = _ctx({"action": "undo", "bot": "", "thing": "",
                              "role": "", "answer": "OTHER", "what": ""})
        out = commands.handle_concierge("undo", session_key="u1")
        self.assertIn("Undone: rule in default", out)
        self.assertFalse(soul.exists())


    def test_undo_bot_already_gone_deletes_nothing(self):
        deleted = []
        real_delete = store.delete_bot
        store.delete_bot = lambda name: deleted.append(name) or (0, "ok")
        try:
            store.push({"kind": "bot", "name": "ghost-bot", "paths": ["/tmp/ghost"], "profile": "ghost-bot"})
            out = commands.handle_concierge("undo", session_key="u9")
            self.assertIn("already gone", out)
            self.assertEqual(deleted, [])
        finally:
            store.delete_bot = real_delete

    def test_install_uses_marketplace_spelling(self):
        seen = {}

        def fake_install(name, profile=""):
            seen["name"] = name
            folder = pathlib.Path(self.tmp.name) / "skills" / name
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "SKILL.md").write_text("# x")
            return (True, str(folder), "ok")

        commands._CTX = _ctx({"action": "install", "bot": "", "thing": "PDF",
                              "role": "", "answer": "OTHER", "what": "pdf"})
        real_skills = search.skills
        real_plugins = search.plugins
        real_connectors = search.connectors
        real_names = search.names_for_model
        search.skills = lambda: [{"name": "pdf", "description": "read pdfs", "source": "x"}]
        search.plugins = lambda: []
        search.connectors = lambda: []
        search.names_for_model = lambda query, limit=200: ["pdf"]
        real_install = store.install_skill
        store.install_skill = fake_install
        try:
            out = commands.handle_concierge("install PDF", session_key="t8")
            self.assertIn("Installed skill pdf", out)
            self.assertEqual(seen.get("name"), "pdf")
        finally:
            search.skills = real_skills
            search.plugins = real_plugins
            search.connectors = real_connectors
            search.names_for_model = real_names
            store.install_skill = real_install


    def test_symlink_skill_is_never_removed(self):
        real = pathlib.Path(self.tmp.name) / "skills" / "real"
        real.mkdir(parents=True, exist_ok=True)
        (real / "SKILL.md").write_text("# x")
        link = pathlib.Path(self.tmp.name) / "skills" / "link"
        try:
            link.symlink_to(real, target_is_directory=True)
        except Exception:
            self.skipTest("symlinks unavailable")
        self.assertFalse(store.remove_skill_dir(str(link)))
        self.assertTrue((real / "SKILL.md").exists())

    def test_forged_soul_path_is_refused(self):
        store.push({"kind": "rule", "name": "default", "paths": [], "profile": "default",
                    "soul_path": "/tmp/evil/SOUL.md", "soul_backup": "", "soul_existed": True})
        out = commands.handle_concierge("undo", session_key="u10")
        self.assertIn("outside this home", out)

    def test_dash_and_path_names_are_not_things(self):
        real_skills = search.skills
        real_plugins = search.plugins
        real_connectors = search.connectors
        search.skills = lambda: [{"name": "obsidian", "description": "local notes", "source": "x", "kind": "skill"}]
        search.plugins = lambda: []
        search.connectors = lambda: []
        try:
            self.assertEqual(commands._canonical_thing("-rf"), ("", False, False))
            self.assertEqual(commands._canonical_thing("a/b"), ("", False, False))
            self.assertEqual(commands._canonical_thing(".."), ("", False, False))
            self.assertEqual(commands._canonical_thing("pdf*"), ("", False, False))
            self.assertEqual(commands._canonical_thing("obsidian -- local notes")[0], "obsidian")
        finally:
            search.skills = real_skills
            search.plugins = real_plugins
            search.connectors = real_connectors

    def test_menu_lines_carry_descriptions(self):
        real_names = search.names_for_model
        try:
            search.names_for_model = lambda query, limit=200: ["pdf -- read pdfs", "obsidian"]
            lines = search.names_for_model("pdf")
            self.assertTrue(lines[0].startswith("pdf -- "))
        finally:
            search.names_for_model = real_names

    def test_ranking_prefers_name_hits_and_folding(self):
        rows = [
            {"name": "990tax", "description": "IRS public records on tax-exempt organizations", "source": "x", "kind": "plugin"},
            {"name": "fiscalisto", "description": "Mexican electronic invoicing and SAT taxes", "source": "x", "kind": "plugin"},
            {"name": "artil", "description": "a bridge adapter", "source": "x", "kind": "plugin"},
            {"name": "email-inbox-triage", "description": "Triage an inbox", "source": "x", "kind": "skill"},
            {"name": "meeting-action-items", "description": "Turn meeting notes into decisions", "source": "x", "kind": "skill"},
            {"name": "baoyu-infographic", "description": "Infographics layouts", "source": "x", "kind": "skill"},
            {"name": "adaptyv", "description": "design systems", "source": "x", "kind": "skill"},
        ]
        real_skills = search.skills
        real_plugins = search.plugins
        real_connectors = search.connectors
        search.skills = lambda: [r for r in rows if r["kind"] == "skill"]
        search.plugins = lambda: [r for r in rows if r["kind"] == "plugin"]
        search.connectors = lambda: []
        try:
            top = [r["name"] for r in search.candidates("inbox zero", limit=3)]
            self.assertEqual(top[0], "email-inbox-triage")
            top = [r["name"] for r in search.candidates("design infographic", limit=3)]
            self.assertEqual(top[0], "baoyu-infographic")
            top = [r["name"] for r in search.candidates("run meetings", limit=3)]
            self.assertEqual(top[0], "meeting-action-items")
            names = [r["name"] for r in search.candidates("tax filing mexico", limit=10)]
            self.assertIn("fiscalisto", names)
        finally:
            search.skills = real_skills
            search.plugins = real_plugins
            search.connectors = real_connectors

    def test_duplicate_names_appear_once(self):
        rows = [
            {"name": "pdf", "description": "read pdfs", "source": "x", "kind": "skill"},
            {"name": "pdf", "description": "read pdfs again", "source": "x", "kind": "skill"},
            {"name": "pdf", "description": "pdf plugin", "source": "x", "kind": "plugin"},
        ]
        real_skills = search.skills
        real_plugins = search.plugins
        real_connectors = search.connectors
        search.skills = lambda: [r for r in rows if r["kind"] == "skill"]
        search.plugins = lambda: [r for r in rows if r["kind"] == "plugin"]
        search.connectors = lambda: []
        try:
            names = [r["name"] for r in search.candidates("read pdfs", limit=10)]
            self.assertEqual(names, ["pdf"])
        finally:
            search.skills = real_skills
            search.plugins = real_plugins
            search.connectors = real_connectors

    def test_read_only_commands_need_no_model(self):
        commands._CTX = None
        out = commands.handle_concierge("bots", session_key="r1")
        self.assertIn("No bots yet", out)
        real_candidates = search.candidates
        real_skills = search.skills
        real_install = store.install_skill
        search.candidates = lambda query, limit=10: [{"name": "pdf", "description": "read pdfs", "source": "x", "kind": "skill"}]
        search.skills = lambda: [{"name": "pdf", "description": "read pdfs", "source": "x"}]
        store.install_skill = lambda name, profile="": (True, "/x/pdf", "ok")
        try:
            out = commands.handle_concierge("browse pdf", session_key="r2")
            self.assertIn("1. pdf (skill)", out)
            out = commands.handle_concierge("install pdf", session_key="r3")
            self.assertIn("Installed skill pdf", out)
        finally:
            search.candidates = real_candidates
            search.skills = real_skills
            store.install_skill = real_install

    def test_bad_profile_and_plugin_names_never_run(self):
        calls = []
        real_run = store._run
        store._run = lambda args, target, timeout=180: calls.append(args) or (0, "nope")
        try:
            self.assertEqual(store.delete_bot("../x"), (False, "bad name"))
            self.assertEqual(store.install_skill("pdf", profile="../x"), (False, "", "bad profile"))
            self.assertEqual(store.remove_plugin("-x"), (1, "bad name"))
            self.assertEqual(store.create_bot("../x", ["pdf"]), (False, "bad name", 0, []))
            self.assertEqual(store.create_bot("default", ["pdf"]), (False, "that one stays", 0, []))
            self.assertEqual(calls, [])
            with self.assertRaises(ValueError):
                store.profile_dir("../../etc")
            self.assertEqual(store.add_rule("../x", "do evil"), (False, "", "bad bot"))
        finally:
            store._run = real_run


if __name__ == "__main__":
    unittest.main()
