"""The command surface: one command, no prompts except on a catalog card."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

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

    def profile_home(self, name: str) -> pathlib.Path:
        return self.homes.get(name, pathlib.Path(tempfile.gettempdir()) / "gone" / name)

    def remove_profile(self, name: str, yes: bool = True) -> None:
        self.removed.append(name)
        home = self.homes.pop(name, None)
        if home is not None and home.is_dir():
            import shutil

            shutil.rmtree(home)


class Help(unittest.TestCase):
    def test_bare_command_is_the_menu(self):
        text = commands.handle_concierge("")
        self.assertIn("CONCIERGE", text)
        for verb in ("hire", "train", "bots", "remove", "reset", "undo", "help"):
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
            "hire chases late invoices",
            store=self.made,
            known=[],
            hire=lambda sentence: (harness.load("bots").spec(sentence), home),
        )
        self.assertIn("Hired invoices-bot", text)
        self.assertNotIn("yes", text.lower().replace("yesterday", ""))
        self.assertIsNotNone(self.made.find("invoices-bot"))
        self.assertEqual(self.made.find("invoices-bot").kind, "bot")

    def test_hire_does_not_promise_undo_when_the_record_cannot_be_saved(self):
        home = pathlib.Path(tempfile.mkdtemp())
        (home / "SOUL.md").write_text("x\n", encoding="utf-8")
        text = commands.handle_concierge(
            "hire chases late invoices",
            store=state.Store(backend=Broken()),
            known=[],
            hire=lambda sentence: (harness.load("bots").spec(sentence), home),
        )
        self.assertIn("Hired invoices-bot", text)
        self.assertNotIn("/concierge undo", text)
        self.assertIn("no undo", text)

    def test_the_sentence_survives_the_verb(self):
        seen = {}
        home = pathlib.Path(tempfile.mkdtemp())
        (home / "SOUL.md").write_text("x\n", encoding="utf-8")

        def hire(sentence):
            seen["sentence"] = sentence
            return harness.load("bots").spec(sentence), home

        commands.handle_concierge("hire keeps my inbox at zero", store=self.made, known=[], hire=hire)
        self.assertEqual(seen["sentence"], "keeps my inbox at zero")

    def test_a_taken_name_stops_and_offers_a_name(self):
        text = commands.handle_concierge("hire keeps my inbox at zero", store=self.made, known=["inbox-bot"])
        self.assertIn("inbox-bot already exists", text)
        self.assertIn("/concierge hire inbox-bot-2:", text)

    def test_default_is_never_a_bot_name(self):
        text = commands.handle_concierge("hire default: keep my inbox at zero", store=self.made, known=[])
        self.assertIn("not a bot", text)
        self.assertEqual(self.made.all(), [])


class Train(unittest.TestCase):
    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp())
        skill = self.home / "skills" / "always-label-receipts"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: always-label-receipts\ndescription: Label receipts before filing.\n---\nLabel them.\n",
            encoding="utf-8",
        )
        self.result = type(
            "Trained",
            (),
            {"bot": "inbox-bot", "slug": "always-label-receipts", "path": skill / "SKILL.md", "dir": skill},
        )()

    def test_one_sentence_trains_with_no_question(self):
        made = store(bot("inbox-bot"))
        text = commands.handle_concierge(
            "train inbox-bot: always label receipts",
            store=made,
            known=["inbox-bot"],
            train=lambda name, instruction: self.result,
        )
        self.assertIn("Trained inbox-bot", text)
        self.assertIn("/concierge undo", text)
        self.assertEqual(made.find("always-label-receipts").kind, "skill")
        self.assertEqual(made.find("always-label-receipts").profile, "inbox-bot")

    def test_train_does_not_promise_undo_when_the_record_cannot_be_saved(self):
        text = commands.handle_concierge(
            "train inbox-bot: always label receipts",
            store=state.Store(backend=Broken()),
            known=["inbox-bot"],
            train=lambda name, instruction: self.result,
        )
        self.assertIn("Trained inbox-bot", text)
        self.assertNotIn("/concierge undo", text)
        self.assertIn("no undo", text)

    def test_an_unknown_bot_lists_the_real_ones(self):
        made = store(bot("inbox-bot"))
        text = commands.handle_concierge("train invoices-bot: chase faster", store=made, known=["inbox-bot"])
        self.assertIn("No bot called invoices-bot", text)
        self.assertIn("inbox-bot", text)


class Bots(unittest.TestCase):
    def test_numbers_come_from_one_place(self):
        made = store(bot("inbox-bot", "keeps my inbox at zero"), bot("newsletter-bot", "writes my weekly newsletter"))
        text = commands.handle_concierge("bots", store=made)
        self.assertIn("BOTS  2", text)
        self.assertIn("inbox-bot", text)
        self.assertIn("newsletter-bot", text)

    def test_empty_is_not_an_error(self):
        self.assertIn("No bots yet", commands.handle_concierge("bots", store=store()))


class Remove(unittest.TestCase):
    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp())
        (self.home / "SOUL.md").write_text("x\n", encoding="utf-8")

    def test_remove_deletes_only_what_concierge_made(self):
        made = store(bot("inbox-bot"))
        seams = FakeSeams({"inbox-bot": self.home})
        text = commands.handle_concierge("remove 1", store=made, seams=seams)
        self.assertIn("Removed: inbox-bot", text)
        self.assertEqual(seams.removed, ["inbox-bot"])
        self.assertFalse(self.home.exists())
        self.assertEqual(made.all(), [])

    def test_default_cannot_be_removed(self):
        made = store(bot("inbox-bot"))
        seams = FakeSeams({})
        text = commands.handle_concierge("remove default", store=made, seams=seams)
        self.assertIn("default is never deleted", text)
        self.assertIn("/concierge reset default", text)
        self.assertEqual(seams.removed, [])

    def test_a_profile_concierge_never_made_is_refused(self):
        made = store(bot("inbox-bot"))
        made.add(state.Installed(name="work", kind="skill", profile="work", title="x"))
        seams = FakeSeams({"work": self.home})
        text = commands.handle_concierge("remove work", store=made, seams=seams)
        self.assertIn("did not create work", text)
        self.assertEqual(seams.removed, [])
        self.assertTrue(self.home.exists())

    def test_a_sentence_starting_with_remove_is_not_a_selector(self):
        made = store(bot("inbox-bot"))
        self.assertFalse(lifecycle.is_selector(made, "duplicate photos from my phone"))

    def test_out_of_range_index_says_so(self):
        text = commands.handle_concierge("remove 9", store=store(bot("inbox-bot")), seams=FakeSeams({}))
        self.assertIn("not one of the bots", text)


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
        self.assertNotIn("Hired", text)
        self.assertNotIn("Removed", text)


if __name__ == "__main__":
    unittest.main()
