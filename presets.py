"""presets.py: ten roles, each with the curated set of skills that make it real.

A preset is a role name plus the skills a bot of that role actually needs: a
handful of the bundled tree, which Hermes ships in the package, and a handful
of optional skills, which install through core's own ``hermes skills install``
(scan, provenance and consent included) scoped to the new profile with ``-p``.

The receipt is the bot's whole brain. Concierge profiles are created lean (the
``.no-bundled-skills`` marker), so the 44-skill tree is NOT seeded; only the
picks below land on disk, plus ``hermes-agent`` itself, which every profile
needs. Nothing here invents a skill: every name is read off the Hermes tree.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

MAX_SKILLS_SHOWN = 6
INSTALL_TIMEOUT = 90  # one skill, not a whole role, has to finish in this
WORKERS = 1  # one at a time: the installer writes into a shared tree


@dataclass(frozen=True)
class Role:
    name: str
    label: str
    skills: tuple[str, ...]        # optional skills: ``<category>/<name>``
    bundled: tuple[str, ...]       # bundled skills, by name, copied from the tree
    blurb: str

    @property
    def picks(self) -> tuple[str, ...]:
        """What lands on disk for this role, in receipt order."""
        return self.bundled + tuple(s.rsplit("/", 1)[-1] for s in self.skills)


# Order matters: first match wins, so the narrower cues come first.
ROLES: tuple[Role, ...] = (
    Role("researcher", "researcher",
         ("research/parallel-cli", "research/llm-wiki", "research/rss-feeds"),
         ("arxiv", "grounded-citations", "blocked-page-recovery", "pdf"),
         "reads sources, follows feeds, keeps citations"),
    Role("writer", "writer",
         ("creative/baoyu-article-illustrator", "research/parallel-cli",
          "web-development/publish-site"),
         ("humanizer", "youtube-content", "grounded-citations", "obsidian"),
         "finds the angle, writes it plain, illustrates and ships it"),
    Role("coder", "coder",
         ("software-development/python-debugpy", "software-development/rest-graphql-debug",
          "software-development/ast-grep", "software-development/code-wiki"),
         ("github", "systematic-debugging", "test-driven-development",
          "requesting-code-review"),
         "debugs, searches structure, reviews, documents the repo"),
    Role("assistant", "assistant",
         (),
         ("email-inbox-triage", "google-workspace", "pdf",
          "document-to-action-items", "weekly-review-planning", "obsidian"),
         "own inbox, calendar, files and notes"),
    Role("marketer", "marketer",
         ("creative/baoyu-article-illustrator", "creative/social-media-content-calendar",
          "social-media/reddit-reading", "research/parallel-cli"),
         ("xurl", "humanizer", "baoyu-infographic"),
         "plans campaigns, reads communities, makes the assets"),
    Role("watcher", "watcher",
         ("devops/watchers", "research/rss-feeds",
          "productivity/live-dashboard"),
         ("product-price-monitor", "competitor-news-monitor", "blocked-page-recovery",
          "xurl"),
         "polls sources, dedupes, pings you, keeps a board"),
    Role("designer", "designer",
         ("creative/sketch", "creative/design-md", "creative/excalidraw",
          "web-development/publish-site"),
         ("baoyu-infographic", "claude-design"),
         "mocks, diagrams, tokens, generated images"),
    Role("analyst", "analyst",
         ("finance/excel-author", "finance/pptx-author", "finance/stocks",
          "productivity/live-dashboard", "research/parallel-cli"),
         ("google-workspace", "pdf", "grounded-citations"),
         "workbooks, decks, notebooks, live numbers"),
    Role("tutor", "tutor",
         ("productivity/memento-flashcards", "creative/excalidraw",
          "research/llm-wiki"),
         ("grounded-citations", "obsidian"),
         "cards, diagrams, explainers, search over your own notes"),
    Role("planner", "planner",
         ("productivity/decision-questionnaire", "communication/one-three-one-rule",
          "software-development/grill-me"),
         ("document-to-action-items", "obsidian", "google-workspace"),
         "turns a fog into options, a pick, and a plan of record"),
)

_BY_NAME = {role.name: role for role in ROLES}

# Words a person actually types. Matched on word boundaries, whole-sentence safe.
CUES: dict[str, tuple[str, ...]] = {
    "researcher": ("research", "researcher", "sources", "papers", "arxiv",
                   "literature", "cite", "citations", "deep dive"),
    "writer": ("write", "writer", "writing", "blog", "article", "copy",
               "newsletter", "script", "draft", "thread"),
    "coder": ("code", "coder", "coding", "dev", "developer", "programmer",
              "debug", "refactor", "repo", "pull request", "tests"),
    # "assistant" is the generic word, not a role: leave it out so
    # "hire a research assistant" lands on researcher.
    "assistant": ("inbox", "email", "calendar", "schedule", "errands",
                  "admin", "files", "logins"),
    "marketer": ("marketing", "marketer", "seo", "social", "campaign", "ads",
                 "audience", "growth", "instagram", "twitter", "reddit"),
    "watcher": ("watch", "watcher", "monitor", "alert", "ping me", "track",
                "notify", "keep an eye", "when it changes", "changes"),
    "designer": ("design", "designer", "mockup", "mockups", "ui", "ux",
                 "brand", "theme", "images", "illustration", "logo"),
    "analyst": ("analyse", "analyze", "analyst", "analysis", "data",
                "spreadsheet", "excel", "metrics", "numbers", "chart", "dashboard"),
    "tutor": ("tutor", "teach", "teacher", "explain", "study", "learn",
              "flashcards", "quiz", "practice", "homework"),
    "planner": ("plan", "planner", "planning", "roadmap", "project", "sprint",
                "priorities", "decision", "schedule my", "keep me on"),
}

_CUES = tuple(
    (role.name, cue)
    for role in ROLES
    for cue in CUES[role.name]
)


def names() -> list[str]:
    return [role.name for role in ROLES]


def get(role: str) -> Role | None:
    return _BY_NAME.get((role or "").strip().lower())


def _forms(cue: str) -> tuple[str, ...]:
    """The cue plus how people actually inflect it: s, es, ing, ed."""
    if " " in cue:
        return (cue,)
    return (cue, cue + "s", cue + "es", cue + "ing", cue + "ed")


def detect(sentence: str) -> Role | None:
    """Best role for a sentence, or None. Longest cue wins, then roster order."""
    text = " " + " ".join((sentence or "").lower().split()) + " "
    best: tuple[int, int] | None = None
    winner: Role | None = None
    for index, (role_name, cue) in enumerate(_CUES):
        if any(" {} ".format(form) in text for form in _forms(cue)):
            score = len(cue)
            if best is None or score > best[0]:
                best = (score, index)
                winner = _BY_NAME[role_name]
    return winner


def official(role: Role) -> list[str]:
    """``official/<category>/<name>`` for each optional skill, in pick order."""
    return ["official/" + skill for skill in role.skills]


@dataclass
class Report:
    role: str
    wanted: list[str]
    installed: list[str]
    failed: list[str]

    @property
    def ok(self) -> bool:
        return bool(self.wanted) and not self.failed

    def lines(self, home: Path | None = None) -> list[str]:
        names = self.installed or self.wanted
        shown = ", ".join(names[:MAX_SKILLS_SHOWN])
        rest = len(names) - MAX_SKILLS_SHOWN
        if rest > 0:
            shown += " +{} more".format(rest)
        if self.failed:
            shown += " (failed: {})".format(", ".join(self.failed))
        return ["  skills   {} {}/{} installed: {}".format(
            self.role, len(self.installed), len(self.wanted), shown)]


def _which_hermes() -> str:
    return shutil.which("hermes") or "hermes"


def _run(
    args: Sequence[str], timeout: int, env: dict | None = None
) -> tuple[int, str]:
    try:
        done = subprocess.run(
            list(args), capture_output=True, text=True, timeout=timeout, env=env
        )
        return done.returncode, (done.stdout or "") + (done.stderr or "")
    except Exception as exc:  # missing binary, timeout, permission
        return 1, "{}: {}".format(type(exc).__name__, exc)


def _present(skills_dir: Path, name: str) -> bool:
    """Skills live at ``skills/<category>/<name>`` (or bare ``skills/<name>``)."""
    for folder in skills_dir.glob("*/" + name):
        if folder.parent.name.startswith("."):  # .archive/ holds retired copies
            continue
        if (folder / "SKILL.md").is_file():
            return True
    return (skills_dir / name / "SKILL.md").is_file()


def verify(home: Path, role: Role) -> list[str]:
    """Skills that are really on disk for that profile, read off the profile."""
    skills_dir = Path(home) / "skills"
    return [skill for skill in role.picks if _present(skills_dir, skill)]


def _copy_bundled(home: Path, names: Sequence[str]) -> list[str]:
    """Copy bundled picks into a lean profile through core's own sync helpers."""
    try:
        from . import seams  # plugin-relative inside Hermes
    except ImportError:  # loaded as a top-level module (spikes, tests)
        import seams

    return seams.copy_bundled(home, names)


def write_soul(home: Path, role: Role) -> int:
    """Write the role's soul over the generic one; 0 when the role has none."""
    try:
        from . import souls
    except ImportError:  # loaded as a flat module by the tests and spikes
        import souls
    text = souls.get(role.name)
    if not text:
        return 0
    try:
        path = Path(home) / "SOUL.md"
        path.write_text(text, encoding="utf-8")
    except OSError:  # no home yet, no perms: the receipt shows the old soul
        return 0
    return len(text)


def install(
    profile: str,
    home: Path,
    role: Role,
    *,
    runner: Callable[[Sequence[str]], tuple[int, str]] | None = None,
    hermes: str | None = None,
    copier: Callable[[Path, Sequence[str]], list[str]] | None = None,
) -> Report:
    """Land the role's skills in one profile, then believe the disk."""
    binary = hermes or _which_hermes()
    copy = copier or _copy_bundled

    # The soul goes in first: if the skills half fails, the bot still knows how
    # to behave, and the receipt below reads the file to prove what landed.
    write_soul(home, role)

    # Profiles are HOME-anchored by core, so the CLI must be told the same root
    # the profile actually lives under, or it looks in HERMES_HOME and finds none.
    env = {**os.environ, "HERMES_HOME": str(Path(home).parent.parent)}

    def one(identifier: str) -> tuple[str, bool]:
        args = [binary, "-p", profile, "skills", "install", identifier, "--yes"]
        code, _ = (runner(args) if runner else _run(args, INSTALL_TIMEOUT, env))
        return identifier, code == 0

    wanted = official(role)
    outcomes = []
    misses = 0
    for identifier in wanted:
        identifier, ok = one(identifier)
        outcomes.append((identifier, ok))
        misses = 0 if ok else misses + 1
        if misses >= 2:
            # Two timeouts in a row is a broken seller, not a slow one: stop
            # instead of holding the conversation for nine of them.
            outcomes += [(left, False) for left in wanted[len(outcomes):]]
            break

    # Bundled copies go in last: the installer archives any same-name skill it
    # finds, so a copy made first would end up retired under `.archive/`.
    try:
        copy(Path(home), role.bundled)
    except Exception:  # no tree, no perms: verify() below reports it, never guess
        pass

    on_disk = set(verify(home, role))
    installed, failed = [], []
    for identifier, ok in outcomes:
        short = identifier.rsplit("/", 1)[-1]
        if ok and short in on_disk:
            installed.append(short)
        else:
            failed.append(short)
    for name in role.bundled:
        if name not in on_disk:
            failed.append(name)
    picks = list(role.picks)
    installed = [name for name in picks if name in on_disk and name not in failed]
    return Report(role.name, picks, installed, failed)
