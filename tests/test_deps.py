"""Dependencies: named before the yes, re-read after it, never a second question.

The catalog publishes no dependency list, so the card reads the plugin's own
manifest at the pinned sha. These tests inject that read, so the suite makes no
network call and stays deterministic.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

card = harness.load("card")
seams = harness.load("seams")
state = harness.load("state")


def entry(name="deps-probe", repo="https://github.com/example/deps-probe", sha="c" * 40):
    return SimpleNamespace(
        name=name,
        title=name,
        description="Does one thing.",
        capabilities={},
        category="general",
        tier="community",
        repo=repo,
        sha=sha,
        version="1.0.0",
    )


def candidate(name="deps-probe"):
    match = harness.load("match")

    e = entry(name)
    return match.Candidate(name=name, title=name, score=9.0, matched=["thing"], entry=e), e


class RemoteDeclaration(unittest.TestCase):
    def test_reads_a_plugin_manifest_at_the_pin(self):
        seen = []

        def fetch(url):
            seen.append(url)
            return "name: deps-probe\npython_dependencies:\n  - httpx\n  - rich>=13\n"

        deps = seams.declared_deps_remote(entry(), fetch=fetch)
        self.assertEqual(deps, ["httpx", "rich>=13"])
        self.assertIn("/" + "c" * 40 + "/plugin.yaml", seen[0])

    def test_reads_a_pyproject_when_there_is_no_plugin_manifest(self):
        def fetch(url):
            if url.endswith("plugin.yaml"):
                return ""
            return '[project]\nname = "x"\ndependencies = ["httpx==0.27"]\n'

        self.assertEqual(seams.declared_deps_remote(entry(), fetch=fetch), ["httpx==0.27"])

    def test_an_unpinned_or_unreachable_repo_declares_nothing(self):
        self.assertEqual(seams.declared_deps_remote(entry(sha=""), fetch=lambda u: "x"), [])

        def broken(url):
            raise OSError("no network")

        self.assertEqual(seams.declared_deps_remote(entry(), fetch=broken), [])

    def test_a_repo_with_no_declaration_returns_nothing(self):
        def fetch(url):
            return "name: deps-probe\n" if url.endswith("plugin.yaml") else ""

        self.assertEqual(seams.declared_deps_remote(entry(), fetch=fetch), [])


class CardLine(unittest.TestCase):
    def test_packages_are_named_before_the_yes(self):
        _, e = candidate()
        text = card.render("do the thing", [candidate()[0]], deps=["httpx", "rich>=13"])
        self.assertIn("Also installs httpx, rich", text)
        self.assertIn("Also installs", text)

    def test_no_packages_means_no_line(self):
        text = card.render("do the thing", [candidate()[0]], deps=[])
        self.assertNotIn("  deps        ", text)

    def test_a_git_package_says_so_in_plain_words(self):
        text = card.render(
            "do the thing", [candidate()[0]], deps=["cfrust @ git+https://github.com/x/cfrust"]
        )
        self.assertIn("(from git)", text)
        self.assertEqual(seams.risky_deps(["cfrust @ git+https://github.com/x/cfrust"]), [
            "cfrust @ git+https://github.com/x/cfrust"
        ])
        self.assertEqual(seams.risky_deps(["httpx==0.27", "rich"]), [])


class ReceiptLine(unittest.TestCase):
    def test_the_receipt_lists_what_core_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plugin.yaml").write_text(
                "name: deps-probe\npython_dependencies:\n  - httpx\n  - rich\n",
                encoding="utf-8",
            )
            outcome = SimpleNamespace(verdict="safe", findings=[], notes=[], enabled=True)
            record = state.Installed(
                name="deps-probe", sha="c" * 40, title="deps-probe", target=str(root), enabled=True
            )
            text = card.receipt(outcome, record)
            self.assertIn("Also installed httpx, rich.", text)

    def test_a_plugin_with_no_declaration_prints_no_deps_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plugin.yaml").write_text("name: plain\n", encoding="utf-8")
            outcome = SimpleNamespace(verdict="safe", findings=[], notes=[], enabled=True)
            record = state.Installed(
                name="plain", sha="c" * 40, title="plain", target=str(root), enabled=True
            )
            self.assertNotIn("  deps        ", card.receipt(outcome, record))


if __name__ == "__main__":
    unittest.main()
