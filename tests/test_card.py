"""The card is the product, so every line of it is a promise under test."""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

card = harness.load("card")
state = harness.load("state")


def entry(name, title="", description="", caps=None, tier="community", category="general"):
    return SimpleNamespace(
        name=name,
        title=title,
        description=description,
        capabilities=caps or {},
        category=category,
        tier=tier,
        repo=f"https://github.com/example/{name}",
        sha="c" * 40,
        version="1.2.0",
    )


CATALOG = [
    entry(
        "hermes-memory-locus",
        title="Locus memory",
        description="Memory provider that recalls notes across sessions.",
        caps={"provides_middleware": ["memory"]},
    ),
    entry(
        "hermes-themes-pack",
        title="Hermes Themes Pack",
        description="Themes and skins for the CLI, the TUI and Desktop.",
    ),
    entry(
        "browser-use",
        title="Browser Use",
        description="Drive a browser to fetch pages.",
        caps={"provides_tools": ["browser_navigate", "browser_extract"]},
    ),
]


class Store:
    def __init__(self):
        self.records = []

    def add(self, record):
        self.records.append(record)

    def latest(self):
        return self.records[-1] if self.records else None


def outcome(**overrides):
    base = dict(
        ok=True,
        installed_name="hermes-themes-pack",
        target="",
        verdict="safe",
        findings=[],
        blocked_reason="",
        enabled=True,
        notes=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class Ask(unittest.TestCase):
    def setUp(self):
        card._reset()

    def test_empty_sentence_asks_for_one(self):
        self.assertIn("/concierge", card.handle("   ", entries=CATALOG))

    def test_no_match_installs_nothing(self):
        text = card.handle("quarterly payroll export", entries=CATALOG)
        self.assertIn("Nothing here fits", text)
        self.assertIn("Nothing was installed", text)

    def test_card_carries_the_decision(self):
        text = card.handle("change the colors of my terminal", entries=CATALOG)
        self.assertIn("hermes-themes-pack", text)
        self.assertIn("yes", text)
        self.assertIn("no", text)
        self.assertIn("Install hermes-themes-pack?", text)

    def test_card_explains_why(self):
        text = card.handle("drive a real browser", entries=CATALOG)
        self.assertIn("Drive a browser", text)
        self.assertIn("browser", text)

    def test_cost_line_is_honest_when_no_tools_are_added(self):
        line = card.cost_line(CATALOG[1])
        self.assertIn("no tools", line)
        # No price and no token figure: nothing about this entry can be measured.
        self.assertNotIn("$", line)
        self.assertNotIn("token", line.lower())

    def test_cost_line_labels_where_the_cost_lands_when_tools_are_added(self):
        line = card.cost_line(CATALOG[2])
        self.assertIn("2 tools", line)
        # It may say the tools ride on every request; it may not claim a charge
        # that was never measured.
        self.assertIn("every request", line)
        self.assertNotIn("charge", line.lower())
        # No number is invented: the catalog carries no schemas, so any token
        # figure here would be a guess.
        self.assertNotIn("token", line.lower())

    def test_runner_up_is_named_but_never_numbered(self):
        text = card.handle("themes memory browser", entries=CATALOG)
        # The rival is named so it can be asked for by name...
        self.assertIn("Another option: hermes-memory-locus", text)
        # ...but there is no second number: a number installs what the card did not
        # describe, which is a decision made blind.
        self.assertNotIn("1 or 2", text)
        self.assertIn("yes", text)
        self.assertIn("no", text)

    def test_more_describes_the_runner_up_and_leaves_the_yes_alone(self):
        card.handle("themes memory browser", entries=CATALOG)
        text = card.handle("more", entries=CATALOG)
        self.assertIn("hermes-memory-locus", text)
        self.assertIn("Memory provider", text)
        self.assertIn("yes", text)
        self.assertIn("no", text)

        picked = []

        def fake_install(entry_, approve=None):
            picked.append(entry_.name)
            return outcome(installed_name=entry_.name)

        card.handle("yes", store=Store(), install=fake_install)
        self.assertEqual(picked, ["browser-use"])

    def test_more_with_nothing_waiting_installs_nothing(self):
        text = card.handle("more", entries=CATALOG)
        self.assertIn("Nothing is waiting", text)

    def test_no_clears_the_pending_question(self):
        card.handle("change the colors of my terminal", entries=CATALOG)
        self.assertIn("Nothing installed", card.handle("no", entries=CATALOG))
        self.assertIn("Nothing is waiting", card.handle("yes", entries=CATALOG))


class Confirm(unittest.TestCase):
    def setUp(self):
        card._reset()

    def test_yes_installs_and_reports_what_happened(self):
        card.handle("change the colors of my terminal", entries=CATALOG)
        store = Store()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "plugin.yaml").write_text("name: x\n", encoding="utf-8")
            calls = []

            def fake_install(entry_, approve=None):
                calls.append(entry_.name)
                return outcome(target=tmp)

            text = card.handle("yes", store=store, install=fake_install)
        self.assertEqual(calls, ["hermes-themes-pack"])
        self.assertIn("Installed hermes-themes-pack", text)
        self.assertIn("the files are there", text)
        self.assertIn("enabled     yes", text)
        self.assertIn("/concierge undo", text)
        self.assertEqual(store.records[0].name, "hermes-themes-pack")
        self.assertTrue(store.records[0].target.endswith(tmp))

    def test_caution_costs_a_second_yes(self):
        card.handle("change the colors of my terminal", entries=CATALOG)
        store = Store()
        first = SimpleNamespace(ok=False, verdict="caution", findings=[], blocked_reason="caution")
        second = outcome(verdict="caution", findings=["reads files"], target="")

        def fake_install(entry_, approve=None):
            accepted = approve("report") if approve else False
            return second if accepted else first

        text = card.handle("yes", store=store, install=fake_install)
        self.assertIn("caution", text)
        self.assertIn("Accept it with /concierge yes", text)
        self.assertEqual(store.records, [])

        text = card.handle("yes", store=store, install=fake_install)
        self.assertIn("hermes-themes-pack", text)
        self.assertIn("1 note", text)

    def test_caution_report_comes_back_as_text_not_as_stdout(self):
        # TUI and gateway never show stdout, so a printed report is a report the
        # user cannot approve.
        card.handle("change the colors of my terminal", entries=CATALOG)
        blocked = SimpleNamespace(ok=False, verdict="caution", findings=[], blocked_reason="caution")

        def fake_install(entry_, approve=None):
            if approve:
                approve("scan: reads files outside its own directory")
            return blocked

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            text = card.handle("yes", store=Store(), install=fake_install)
        self.assertEqual(buffer.getvalue(), "")
        self.assertIn("reads files outside its own directory", text)
        self.assertIn("Accept it with /concierge yes", text)

    def test_dangerous_rating_is_reported_not_installed(self):
        card.handle("change the colors of my terminal", entries=CATALOG)
        blocked = outcome(
            ok=False, verdict="dangerous", blocked_reason="scan rated the plugin dangerous"
        )
        text = card.handle("yes", store=Store(), install=lambda e, approve=None: blocked)
        self.assertIn("Not installed", text)
        self.assertIn("dangerous", text)

    def test_two_installs_nothing_unseen(self):
        card.handle("themes memory browser", entries=CATALOG)
        picked = []

        def fake_install(entry_, approve=None):
            picked.append(entry_.name)
            return outcome(installed_name=entry_.name)

        text = card.handle("2", store=Store(), install=fake_install)
        self.assertEqual(picked, [])
        self.assertIn("One install at a time", text)
        # The card is untouched and still means the top match.
        self.assertIn("Nothing installed", card.handle("no", entries=CATALOG))

    def test_two_with_nothing_pending_installs_nothing(self):
        called = []

        def fake_install(entry_, approve=None):
            called.append(entry_.name)
            return outcome()

        text = card.handle("2", store=Store(), install=fake_install)
        self.assertEqual(called, [])
        self.assertIn("One install at a time", text)

    def test_receipt_does_not_promise_undo_when_the_record_could_not_be_saved(self):
        card.handle("change the colors of my terminal", entries=CATALOG)

        class Broken:
            records = []

            def add(self, record):
                raise OSError("disk full")

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "plugin.yaml").write_text("name: x\n", encoding="utf-8")
            text = card.handle(
                "yes",
                store=Broken(),
                install=lambda e, approve=None: outcome(target=tmp),
            )
        self.assertIn("Installed hermes-themes-pack", text)
        self.assertNotIn("Undo it with", text)
        self.assertIn("could not be saved", text)


class CardsArePerConversation(unittest.TestCase):
    """One gateway process serves many chats, so a card belongs to the chat shown it."""

    def setUp(self):
        card._PENDING.clear()

    def test_a_yes_in_another_chat_installs_nothing(self):
        card.handle("change the colors of my terminal", entries=CATALOG, session_key="chat-a")
        text = card.handle("yes", entries=CATALOG, session_key="chat-b")
        self.assertIn("Nothing is waiting", text)

    def test_each_chat_answers_its_own_card(self):
        card.handle("change the colors of my terminal", entries=CATALOG, session_key="chat-a")
        card.handle("drive a real browser", entries=CATALOG, session_key="chat-b")
        picked = []

        def fake_install(entry_, approve=None):
            picked.append(entry_.name)
            return outcome(installed_name=entry_.name)

        card.handle("yes", entries=CATALOG, store=Store(), install=fake_install, session_key="chat-b")
        self.assertEqual(picked, ["browser-use"])
        # chat-a still holds the card it was shown, and nothing else.
        self.assertIn("Nothing is waiting", card.handle("yes", entries=CATALOG, session_key="chat-c"))
        card.handle("yes", entries=CATALOG, store=Store(), install=fake_install, session_key="chat-a")
        self.assertEqual(picked, ["browser-use", "hermes-themes-pack"])


if __name__ == "__main__":
    unittest.main()
