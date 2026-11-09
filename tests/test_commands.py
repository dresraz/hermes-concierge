"""The command surface: one command, no prompts except on a catalog card."""

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


class Memory:
    """A get/set pair where core's PluginState would sit in production."""

    def __init__(self) -> None:
        self.data: dict = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value) -> None:
        self.data[key] = value


class Broken(Memory):
    """A store whose write fails, like a full disk."""

    def set(self, key, value) -> None:
        raise OSError("disk full")


def store(*records) -> object:
    made = state.Store(backend=Memory())
    for record in records:
        made.add(record)
    return made


def bot(name: str, title: str = "") -> object:
    return state.Installed(name=name, kind="bot", title=title or name, profile=name, enabled=True)


class FakeSeams:
    """Records every profile call so a test can prove what was and was not done."""

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


class Help(unittest.TestCase):
    def test_bare_command_is_the_shelf(self):
        text = commands.handle_concierge("")
        self.assertIn("Concierge", text)
        self.assertIn("here", text)
        self.assertIn("browse", text)

    def test_the_menu_is_still_one_word_away(self):
        text = commands.handle_concierge("help")
        for verb in ("create", "improve", "bots", "fire", "reset", "undo"):
            self.assertIn(verb, text)

    def test_help_word_is_the_same_text(self):
        self.assertEqual(commands.handle_concierge("help"), commands.HELP)

    def test_no_other_command_is_offered(self):
        source = pathlib.Path(commands.__file__).read_text(encoding="utf-8")
        self.assertEqual(source.count("ctx.register_command("), 1)
        self.assertIn('"concierge"', source)


class Hire(unittest.TestCase):
    def setUp(self):
        self.made = store()

    def test_one_sentence_hires_with_no_question(self):
        home = pathlib.Path(tempfile.mkdtemp())
        (home / "SOUL.md").write_text("I chase invoices.\n", encoding="utf-8")
        text = commands.handle_concierge(
            "create chases late invoices",
            store=self.made,
            known=[],
            hire=lambda sentence: (harness.load("bots").spec(sentence), home),
        )
        self.assertIn("Created invoices-bot", text)
        self.assertNotIn("yes", text.lower().replace("yesterday", ""))
        self.assertIsNotNone(self.made.find("invoices-bot"))
        self.assertEqual(self.made.find("invoices-bot").kind, "bot")

    def test_hire_does_not_promise_undo_when_the_record_cannot_be_saved(self):
        home = pathlib.Path(tempfile.mkdtemp())
        (home / "SOUL.md").write_text("x\n", encoding="utf-8")
        text = commands.handle_concierge(
            "create chases late invoices",
            store=state.Store(backend=Broken()),
            known=[],
            hire=lambda sentence: (harness.load("bots").spec(sentence), home),
        )
        self.assertIn("Created invoices-bot", text)
        self.assertNotIn("/concierge undo", text)
        self.assertIn("no undo", text)

    def test_the_sentence_survives_the_verb(self):
        seen = {}
        home = pathlib.Path(tempfile.mkdtemp())
        (home / "SOUL.md").write_text("x\n", encoding="utf-8")

        def hire(sentence):
            seen["sentence"] = sentence
            return harness.load("bots").spec(sentence), home

        commands.handle_concierge("create keeps my inbox at zero", store=self.made, known=[], hire=hire)
        self.assertEqual(seen["sentence"], "keeps my inbox at zero")

    def test_default_is_never_a_bot_name(self):
        text = commands.handle_concierge("create default: keep my inbox at zero", store=self.made, known=[])
        self.assertIn("not a bot", text)
        self.assertEqual(self.made.all(), [])


class Improve(unittest.TestCase):
    """improve works on any bot: a rule lands in SOUL, a skill in the tree."""

    def setUp(self):
        import os
        from unittest import mock

        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.bot = self.tmp / "profiles" / "inbox-bot"
        self.bot.mkdir(parents=True)
        (self.bot / "config.yaml").write_text("model: {}\n", encoding="utf-8")
        patcher = mock.patch.dict(os.environ, {"HERMES_HOME": str(self.tmp)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_rule_lands_in_soul_with_one_undo_line(self):
        made = store()
        text = commands.handle_concierge(
            "improve inbox-bot: always label receipts", store=made
        )
        self.assertIn("Improved inbox-bot", text)
        self.assertIn("always label receipts", text)
        self.assertIn("/concierge undo", text)
        soul = (self.bot / "SOUL.md").read_text(encoding="utf-8")
        self.assertIn("- always label receipts", soul)
        self.assertIn("Learned rules", soul)

    def test_an_unknown_bot_lists_the_real_ones(self):
        text = commands.handle_concierge(
            "improve invoices-bot: chase faster", store=store()
        )
        self.assertIn("No bot called invoices-bot", text)
        self.assertIn("inbox-bot", text)

    def test_a_hand_made_bot_can_be_improved(self):
        text = commands.handle_concierge(
            "improve inbox-bot: never send without asking", store=store()
        )
        self.assertIn("Improved inbox-bot", text)
        self.assertTrue((self.bot / "SOUL.md").is_file())

    def test_nothing_in_the_marketplace_says_so(self):
        text = commands.handle_concierge(
            "improve inbox-bot: quantum flux capacitor", store=store()
        )
        self.assertIn("Nothing in the marketplace fits that", text)


class Router(unittest.TestCase):
    """One sentence, one decision, using the bots that exist."""

    def test_a_new_role_creates(self):
        with mock.patch.object(commands, "_bot_names", lambda: ["default"]):
            self.assertEqual(commands._route("a researcher that reads papers")[0], "create")

    def test_a_role_that_exists_is_improved_not_duplicated(self):
        with mock.patch.object(commands, "_bot_names", lambda: ["default", "researcher-bot"]):
            kind, bot, _ = commands._route("make my researcher better at citations")
            self.assertEqual((kind, bot), ("improve", "researcher-bot"))

    def test_no_role_is_an_install(self):
        with mock.patch.object(commands, "_bot_names", lambda: ["default"]):
            self.assertEqual(commands._route("stripe payments")[0], "install")


class Gateway(unittest.TestCase):
    """A shared chat may look, never change, unless the owner opts in."""

    def setUp(self):
        self.saved = commands._CTX
        self.addCleanup(lambda: setattr(commands, "_CTX", self.saved))

    class Ctx:
        def __init__(self, surface):
            self.surface = surface

        def session_surface(self):
            return self.surface

    def test_a_gateway_refuses_a_changing_sentence(self):
        commands._CTX = self.Ctx("telegram")
        text = commands.handle_concierge("make me a researcher", store=store())
        self.assertIn("does not run from a shared chat", text)

    def test_a_gateway_may_still_look(self):
        commands._CTX = self.Ctx("telegram")
        self.assertIn("Concierge", commands.handle_concierge("", store=store()))
        self.assertTrue(commands.handle_concierge("browse notes", store=store()).startswith("  LOOKING FOR"))

    def test_the_owner_can_open_the_gateway(self):
        commands._CTX = self.Ctx("telegram")
        saved = commands._allow_gateway
        commands._allow_gateway = lambda: True
        try:
            text = commands.handle_concierge("help")
        finally:
            commands._allow_gateway = saved
        self.assertNotIn("shared chat", text)

    def test_the_local_session_is_never_gated(self):
        commands._CTX = self.Ctx("cli")
        self.assertNotIn("shared chat", commands.handle_concierge("help"))


class OldWords(unittest.TestCase):
    """hire and train are gone, and a stale habit gets a pointer, not a bot."""

    def test_hire_points_at_create(self):
        text = commands.handle_concierge("hire a researcher for papers", store=store())
        self.assertIn("hire is gone", text)
        self.assertIn("/concierge create", text)

    def test_train_points_at_improve(self):
        text = commands.handle_concierge("train inbox-bot: always cite", store=store())
        self.assertIn("train is gone", text)
        self.assertIn("/concierge improve", text)


class Bots(unittest.TestCase):
    def test_numbers_come_from_one_place(self):
        made = store(bot("inbox-bot", "keeps my inbox at zero"), bot("newsletter-bot", "writes my weekly newsletter"))
        text = commands.handle_concierge("bots", store=made)
        self.assertIn("Bots  2", text)
        self.assertIn("inbox-bot", text)
        self.assertIn("newsletter-bot", text)

    def test_empty_is_not_an_error(self):
        self.assertIn("No bots yet", commands.handle_concierge("bots", store=store()))


class Fire(unittest.TestCase):
    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp())
        (self.home / "SOUL.md").write_text("x\n", encoding="utf-8")

    def test_fire_deletes_only_what_concierge_made(self):
        made = store(bot("inbox-bot"))
        seams = FakeSeams({"inbox-bot": self.home})
        text = commands.handle_concierge("fire 1", store=made, seams=seams)
        self.assertIn("Fired: inbox-bot", text)
        self.assertEqual(seams.removed, ["inbox-bot"])
        self.assertFalse(self.home.exists())
        self.assertEqual(made.all(), [])

    def test_fire_refuses_a_used_bot_until_its_name_is_typed(self):
        made = store(bot("inbox-bot"))
        seams = FakeSeams({"inbox-bot": self.home})
        seams.history["inbox-bot"] = {"sessions": 14, "memories": 2, "cron": 0}
        text = commands.handle_concierge("fire 1", store=made, seams=seams)
        self.assertIn("has history: 14 sessions, 2 memory files", text)
        self.assertIn("fire 1 inbox-bot", text)
        self.assertEqual(seams.removed, [])
        self.assertTrue(self.home.exists())
        self.assertEqual([r.name for r in made.all()], ["inbox-bot"])

    def test_fire_with_the_name_typed_goes_through(self):
        made = store(bot("inbox-bot"))
        seams = FakeSeams({"inbox-bot": self.home})
        seams.history["inbox-bot"] = {"sessions": 14, "memories": 0, "cron": 0}
        text = commands.handle_concierge("fire 1 inbox-bot", store=made, seams=seams)
        self.assertIn("Fired: inbox-bot", text)
        self.assertEqual(seams.removed, ["inbox-bot"])
        self.assertFalse(self.home.exists())

    def test_default_cannot_be_fired(self):
        made = store(bot("inbox-bot"))
        seams = FakeSeams({})
        text = commands.handle_concierge("fire default", store=made, seams=seams)
        self.assertIn("default is never deleted", text)
        self.assertIn("/concierge reset default", text)
        self.assertEqual(seams.removed, [])

    def test_a_profile_concierge_never_made_is_refused(self):
        made = store(bot("inbox-bot"))
        made.add(state.Installed(name="work", kind="skill", profile="work", title="x"))
        seams = FakeSeams({"work": self.home})
        text = commands.handle_concierge("fire work", store=made, seams=seams)
        self.assertIn("did not create work", text)
        self.assertEqual(seams.removed, [])
        self.assertTrue(self.home.exists())

    def test_a_sentence_starting_with_fire_is_not_a_selector(self):
        made = store(bot("inbox-bot"))
        self.assertFalse(lifecycle.is_selector(made, "the intern before friday"))

    def test_out_of_range_index_says_so(self):
        text = commands.handle_concierge("fire 9", store=store(bot("inbox-bot")), seams=FakeSeams({}))
        self.assertIn("not one of the bots", text)

    def test_undo_never_deletes_a_bot_that_has_been_used(self):
        made = store(bot("inbox-bot"))
        seams = FakeSeams({"inbox-bot": self.home})
        seams.history["inbox-bot"] = {"sessions": 3, "memories": 1, "cron": 0}
        text = commands.handle_concierge("undo", store=made, seams=seams)
        self.assertIn("Not undone: inbox-bot", text)
        self.assertIn("undo never deletes a used bot", text)
        self.assertIn("/concierge fire", text)
        self.assertEqual(seams.removed, [])
        self.assertTrue(self.home.exists())
        self.assertEqual([r.name for r in made.all()], ["inbox-bot"])

    def test_undo_takes_back_a_stock_hire(self):
        made = store(bot("inbox-bot"))
        seams = FakeSeams({"inbox-bot": self.home})
        text = commands.handle_concierge("undo", store=made, seams=seams)
        self.assertIn("Undone: inbox-bot", text)
        self.assertEqual(seams.removed, ["inbox-bot"])
        self.assertFalse(self.home.exists())
        self.assertEqual(made.all(), [])


class Reset(unittest.TestCase):
    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp())

    def test_reset_replays_only_our_records(self):
        made = store(bot("inbox-bot"))
        made.add(state.Installed(name="always-label", kind="skill", profile="inbox-bot", title="label"))
        seams = FakeSeams({"inbox-bot": self.home})
        text = commands.handle_concierge("reset 1", store=made, seams=seams)
        self.assertIn("Reset: inbox-bot", text)
        self.assertEqual([r.name for r in made.all()], ["inbox-bot"])
        self.assertEqual(seams.removed, [])
        self.assertTrue(self.home.exists())

    def test_reset_leaves_the_bot_standing(self):
        made = store(bot("inbox-bot"))
        seams = FakeSeams({"inbox-bot": self.home})
        text = commands.handle_concierge("reset inbox-bot", store=made, seams=seams)
        self.assertIn("kept: the bot itself", text)
        self.assertIn("Nothing inside it to take back yet", text)
        self.assertEqual(seams.removed, [])
        self.assertTrue(self.home.exists())

    def test_default_is_reset_never_wiped(self):
        made = store()
        made.add(state.Installed(name="always-label", kind="skill", profile="default", title="label"))
        seams = FakeSeams({"default": self.home})
        text = commands.handle_concierge("reset default", store=made, seams=seams)
        self.assertIn("Reset: default", text)
        self.assertEqual(seams.removed, [])
        self.assertTrue(self.home.exists())

    def test_reset_with_nothing_to_reset_says_so(self):
        text = commands.handle_concierge("reset default", store=store(), seams=FakeSeams({}))
        self.assertIn("nothing to take back", text)


class BareYes(unittest.TestCase):
    def test_a_yes_with_no_card_is_not_a_command(self):
        text = commands.handle_concierge("yes", store=store())
        self.assertNotIn("Created", text)
        self.assertNotIn("Fired", text)


if __name__ == "__main__":
    unittest.main()


class SelfOnly(unittest.TestCase):
    """A bot gets its own Concierge, scoped to itself.

    The scoped home, not the env var, is what core hands a served profile: one
    process serves many profiles, so ``os.environ`` only holds the launch one.
    """

    def setUp(self):
        from hermes_constants import reset_hermes_home_override, set_hermes_home_override

        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.bot = self.tmp / "profiles" / "helper-two"
        self.bot.mkdir(parents=True)
        (self.bot / "config.yaml").write_text("model: {}\n", encoding="utf-8")
        token = set_hermes_home_override(str(self.bot))
        self.addCleanup(reset_hermes_home_override, token)

    def test_a_bot_cannot_make_bots(self):
        text = commands.handle_concierge("create a researcher", store=store())
        self.assertIn("cannot make other bots", text)

    def test_a_bot_cannot_improve_another_bot(self):
        text = commands.handle_concierge("improve coder-bot: always cite", store=store())
        self.assertIn("only improve itself", text)

    def test_a_bot_can_improve_itself(self):
        text = commands.handle_concierge("improve me: always answer in one line", store=store())
        self.assertIn("Improved helper-two", text)
        self.assertTrue((self.bot / "SOUL.md").is_file())

    def test_a_plain_sentence_inside_a_bot_is_a_self_improve(self):
        intent, bot, _ = commands._route("it needs to read scanned pdfs")
        self.assertEqual((intent, bot), ("improve", "helper-two"))

    def test_the_owner_profile_keeps_full_power(self):
        from hermes_constants import reset_hermes_home_override, set_hermes_home_override

        token = set_hermes_home_override(str(self.tmp))
        self.addCleanup(reset_hermes_home_override, token)
        self.assertFalse(commands._is_bot_profile())


class AskingForABot(unittest.TestCase):
    """How a person actually asks for a bot."""

    def test_i_want_to_make_a_general_assistant_bot_creates_one(self):
        for sentence in (
            "I want to make a general assistant bot",
            "make me a general assistant",
            "create an assistant bot for me",
            "I need an assistant",
        ):
            self.assertEqual(commands._route(sentence)[0], "create", sentence)

    def test_a_research_assistant_is_a_researcher_not_the_generic_one(self):
        from concierge import presets

        role = presets.detect("hire a research assistant")
        self.assertIsNotNone(role)
        self.assertEqual(role.name, "researcher")

    def test_a_bot_ask_with_no_known_role_still_makes_a_bot(self):
        intent, _, _ = commands._route("make me a bot that answers the door")
        self.assertEqual(intent, "create")

    def test_a_plain_capability_is_still_an_install(self):
        self.assertEqual(commands._route("install obsidian")[0], "install")


class BotAskGuard(unittest.TestCase):
    """An install card must never answer a request for a bot."""

    def test_a_bot_sentence_is_never_an_install(self):
        for sentence in (
            "I want to make a general assistant bot",
            "I need a bot that answers the door",
            "could you build me an agent for invoices",
            "I'd like another researcher",
        ):
            self.assertTrue(commands._asks_for_bot(sentence), sentence)

    def test_a_capability_sentence_is_not_a_bot(self):
        for sentence in (
            "I need a skill that reads spreadsheets",
            "install obsidian",
            "add pdf support",
            "install obsidian into lima-house-seller",
        ):
            self.assertFalse(commands._asks_for_bot(sentence), sentence)


class TheCardStillWorks(unittest.TestCase):
    """One card, one yes: the loop the README promises."""

    def test_a_waiting_card_owns_the_yes(self):
        from unittest import mock

        card = harness.load("card")

        card._PENDING["chat-x"] = {"sentence": "install pdf", "entries": ["one"], "target": ""}
        self.addCleanup(card._PENDING.pop, "chat-x", None)
        with mock.patch.object(card, "handle", return_value="CARD ANSWER") as sent:
            text = commands.handle_concierge("yes", store=store(), session_key="chat-x")
        self.assertEqual(text, "CARD ANSWER")
        self.assertEqual(sent.call_count, 1)

    def test_a_waiting_card_owns_more_and_one(self):
        from unittest import mock

        card = harness.load("card")

        for word in ("more", "1", "no"):
            card._PENDING["chat-y"] = {"sentence": "install pdf", "entries": ["one"], "target": ""}
            self.addCleanup(card._PENDING.pop, "chat-y", None)
            with mock.patch.object(card, "handle", return_value="CARD ANSWER"):
                self.assertEqual(
                    commands.handle_concierge(word, store=store(), session_key="chat-y"),
                    "CARD ANSWER",
                    word,
                )
