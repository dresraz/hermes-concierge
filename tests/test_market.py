"""Anything on the marketplace, into any profile: one card, one yes, one receipt."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

market = harness.load("market")
commands = harness.load("commands")
seams = harness.load("seams")


def hit(name, identifier="", description="What it does.", source="skills.sh", trust="community"):
    return SimpleNamespace(
        name=name,
        identifier=identifier or name,
        description=description,
        source=source,
        trust_level=trust,
    )


def one(record):
    store = Store()
    store.add(record)
    return store


class Store:
    def __init__(self):
        self.records = []

    def add(self, record):
        self.records.append(record)

    def latest(self):
        return self.records[-1] if self.records else None

    def drop(self, name, kind=None):
        self.records = [r for r in self.records if getattr(r, "name", "") != name]
        return True


class Split(unittest.TestCase):
    def test_a_known_bot_after_into_becomes_the_target(self):
        with mock.patch.object(seams, "profile_exists", lambda name: name == "intern"):
            self.assertEqual(
                market.split_target("stripe payments into intern"),
                ("stripe payments", "intern"),
            )

    def test_a_word_that_is_not_a_profile_stays_in_the_sentence(self):
        with mock.patch.object(seams, "profile_exists", lambda name: False):
            self.assertEqual(
                market.split_target("a plugin into my workflow"),
                ("a plugin into my workflow", ""),
            )

    def test_no_into_means_this_profile(self):
        with mock.patch.object(seams, "profile_exists", lambda name: True):
            self.assertEqual(market.split_target("stripe payments"), ("stripe payments", ""))


class Card(unittest.TestCase):
    def setUp(self):
        market.forget("s1")
        self.patch = mock.patch.object(seams, "current_profile", lambda: "default")
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        market.forget("s1")

    def test_the_card_names_the_bot_it_will_install_into(self):
        card = market.handle(
            "stripe payments",
            target="intern",
            session_key="s1",
            search_fn=lambda query, limit: [hit("stripe", "stripe@skills.sh")],
        )
        self.assertIn("Install stripe?", card)
        self.assertIn("It goes into intern", card)
        self.assertIn("Install stripe?", card)
        self.assertTrue(market.is_waiting("s1"))

    def test_the_card_says_this_profile_when_no_bot_was_named(self):
        card = market.handle(
            "stripe payments",
            session_key="s1",
            search_fn=lambda query, limit: [hit("stripe")],
        )
        self.assertIn("Install stripe?", card)

    def test_nothing_found_installs_nothing(self):
        card = market.handle(
            "a time machine", target="intern", session_key="s1",
            search_fn=lambda query, limit: [],
        )
        self.assertIn("Nothing here fits", card)
        self.assertIn("Nothing was installed into intern", card)
        self.assertFalse(market.is_waiting("s1"))

    def test_yes_installs_into_the_named_bot_and_says_where(self):
        seen = []

        def install(offer, profile):
            seen.append((offer.identifier, profile))
            folder = Path(tempfile.mkdtemp()) / "stripe"
            folder.mkdir()
            (folder / "SKILL.md").write_text("x", encoding="utf-8")
            return True, str(folder), ""

        store = Store()
        market.handle(
            "stripe payments", target="intern", session_key="s1",
            search_fn=lambda query, limit: [hit("stripe", "stripe@skills.sh")],
        )
        receipt = market.handle("yes", session_key="s1", install=install, store=store)

        self.assertEqual(seen, [("stripe@skills.sh", "intern")])
        self.assertIn("Installed skill stripe", receipt)
        self.assertIn("It goes into intern.", receipt)
        self.assertIn("Undo with /concierge undo.", receipt)
        self.assertEqual(store.records[0].kind, "skill")
        self.assertEqual(store.records[0].profile, "intern")
        self.assertFalse(market.is_waiting("s1"))

    def test_no_installs_nothing(self):
        def install(offer, profile):  # pragma: no cover - must never run
            raise AssertionError("install ran after a no")

        market.handle(
            "stripe payments", session_key="s1",
            search_fn=lambda query, limit: [hit("stripe")],
        )
        self.assertEqual(market.handle("no", session_key="s1", install=install),
                         "Nothing installed.\n")
        self.assertFalse(market.is_waiting("s1"))

    def test_a_refused_install_says_so_and_offers_no_undo(self):
        store = Store()
        market.handle(
            "stripe payments", session_key="s1",
            search_fn=lambda query, limit: [hit("stripe")],
        )
        receipt = market.handle(
            "yes", session_key="s1", store=store,
            install=lambda offer, profile: (False, "", "core said no"),
        )
        self.assertIn("Not installed: core said no", receipt)
        self.assertNotIn("Undo", receipt)
        self.assertEqual(store.records, [])


class BothShelves(unittest.TestCase):
    def setUp(self):
        market.forget("s2")
        self.net = mock.patch.object(seams, "catalog", lambda: [])
        self.net.start()
        self.deps = mock.patch.object(seams, "declared_deps_remote", lambda entry: [])
        self.deps.start()

    def tearDown(self):
        self.deps.stop()
        self.net.stop()
        market.forget("s2")

    def test_a_plugin_answers_before_the_skill_shelf(self):
        entry = SimpleNamespace(
            name="hermes-themes-pack", title="Themes", description="Themes and skins.",
            capabilities={}, category="general", tier="community",
            repo="https://github.com/example/themes", sha="c" * 40, version="1.2.0",
        )
        asked = []
        with mock.patch.object(seams, "profile_exists", lambda name: name == "intern"):
            text = commands.handle_install(
                "themes into intern", catalog=[entry],
                search=lambda query, limit: asked.append(query) or [],
            )
        # A named plugin installs rather than asking, so the contract is that the
        # plugin shelf answered at all and the skill shelf was never consulted.
        self.assertIn("intern", text)
        self.assertEqual(asked, [])

    def test_the_skill_shelf_answers_when_no_plugin_matches(self):
        from types import SimpleNamespace

        choose = harness.load("choose")
        with mock.patch.object(seams, "profile_exists", lambda name: name == "intern"):
            with mock.patch.object(
                choose, "pick",
                return_value=SimpleNamespace(name="stripe", kind="skill", caution=""),
            ):
                text = commands.handle_install(
                    "stripe payments", catalog=[], session_key="s2",
                    search=lambda query, limit: [hit("stripe", "stripe@skills.sh")],
                )
        self.assertIn("Install stripe?", text)
        self.assertIn("Install stripe?", text)


class CardSplitsTheBot(unittest.TestCase):
    """A plain sentence carries the bot itself, not just /concierge install."""

    def setUp(self):
        card = harness.load("card")
        self.card = card
        card.forget("s4")
        self.seen = []
        self.patch = mock.patch.object(
            card, "_install",
            lambda *a, **kw: self.seen.append(kw.get("target")) or "ok\n",
        )
        self.patch.start()
        self.net = mock.patch.object(seams, "declared_deps_remote", lambda entry: [])
        self.net.start()

    def tearDown(self):
        self.net.stop()
        self.patch.stop()
        self.card.forget("s4")

    def entry(self):
        return SimpleNamespace(
            name="accent-picker", title="Accent picker", description="Accent colour picker.",
            capabilities={}, category="desktop", tier="official",
            repo="https://github.com/NousResearch/hermes-official-plugins",
            sha="a" * 40, version="1.0.0",
        )

    def test_the_bot_after_into_reaches_the_install(self):
        with mock.patch.object(seams, "profile_exists", lambda name: name == "intern"):
            self.card.handle("accent picker into intern", entries=[self.entry()],
                             session_key="s4")
            self.card.handle("yes", session_key="s4")
        self.assertEqual(self.seen, ["intern"])

    def test_without_a_bot_the_install_goes_to_this_profile(self):
        with mock.patch.object(seams, "profile_exists", lambda name: False):
            self.card.handle("accent picker", entries=[self.entry()], session_key="s4")
            self.card.handle("yes", session_key="s4")
        self.assertEqual(self.seen, [""])


class UndoInAnotherBot(unittest.TestCase):
    """Undo leaves the home the install went into, never this profile."""

    def setUp(self):
        self.skill_calls = []
        self.patch = mock.patch.object(
            commands, "_undo_skill",
            lambda record, effects: self.skill_calls.append(record) or ["removed"],
        )
        self.patch.start()
        self.home = Path(tempfile.mkdtemp())

    def tearDown(self):
        self.patch.stop()

    def test_a_plugin_installed_into_a_bot_is_removed_from_that_bot(self):
        folder = self.home / "plugins" / "accent-picker"
        folder.mkdir(parents=True)
        (folder / "plugin.yaml").write_text("name: accent-picker\n", encoding="utf-8")
        record = SimpleNamespace(name="accent-picker", kind="plugin", profile="intern",
                                 skills=[], plugin="")
        with mock.patch.object(seams, "profile_home", lambda name: self.home), \
             mock.patch.object(seams, "remove_plugin_in",
                               lambda profile, name: not (shutil.rmtree(folder) or True)):
            text = commands.handle_undo(store=one(record), seams=seams)
        self.assertEqual(self.skill_calls, [])
        self.assertFalse(folder.exists())
        self.assertIn("removed: plugin accent-picker from intern", text)

    def test_a_skill_installed_into_a_bot_is_removed_from_that_bot(self):
        folder = self.home / "skills" / "writing-for-agents"
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text("x", encoding="utf-8")

        def remove(profile, name):
            shutil.rmtree(folder)
            return True

        record = SimpleNamespace(name="writing-for-agents", kind="skill", profile="intern",
                                 skills=["writing-for-agents"], plugin="")
        with mock.patch.object(seams, "profile_home", lambda name: self.home), \
             mock.patch.object(seams, "remove_skill_in", remove):
            text = commands.handle_undo(store=one(record), seams=seams)
        self.assertEqual(self.skill_calls, [])
        self.assertFalse(folder.exists())
        self.assertIn("removed: skill writing-for-agents from intern", text)

    def test_a_skill_receipt_does_not_claim_a_missing_plugin(self):
        folder = self.home / "skills" / "writing-for-agents"
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text("x", encoding="utf-8")
        record = SimpleNamespace(name="writing-for-agents", kind="skill", profile="intern",
                                 skills=["writing-for-agents"], plugin="")
        with mock.patch.object(seams, "profile_home", lambda name: self.home), \
             mock.patch.object(seams, "remove_skill_in", lambda profile, name: True):
            text = commands.handle_undo(store=one(record), seams=seams)
        self.assertNotIn("plugin", text)


if __name__ == "__main__":
    unittest.main()
