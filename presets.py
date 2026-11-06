"""presets.py: ten roles, each with the handful of skills that make it real.

A preset is a role name plus two or three skills Hermes ships as optional, so
``/concierge hire a researcher`` lands a bot that can actually research. Nothing
here invents a skill: every identifier is ``<category>/<name>`` under
``optional-skills/`` in the Hermes tree, and installs go through core's own
``hermes skills install`` (scan, provenance and consent included) scoped to the
new profile with ``-p``.

Bundled skills are left out on purpose. Every fresh profile is seeded with the
whole ``skills/`` tree, so listing them would be noise on the receipt.
"""

from __future__ import annotations

import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

MAX_SKILLS_SHOWN = 6
INSTALL_TIMEOUT = 180
WORKERS = 3


@dataclass(frozen=True)
class Role:
    name: str
    label: str
    skills: tuple[str, ...]
    blurb: str


# Order matters: first match wins, so the narrower cues come first.
ROLES: tuple[Role, ...] = (
    Role("researcher", "researcher",
         ("research/parallel-cli", "research/scrapling", "research/rss-feeds"),
         "reads sources, follows feeds, keeps citations"),
    Role("writer", "writer",
         ("research/research-paper-writing", "creative/creative-ideation",
          "creative/simple-english", "creative/baoyu-article-illustrator"),
         "finds the angle, writes it plain, illustrates it"),
    Role("coder", "coder",
         ("software-development/python-debugpy", "software-development/rest-graphql-debug",
          "software-development/ast-grep", "software-development/pr-lens"),
         "debugs, searches structure, draws the diff"),
    Role("assistant", "assistant",
         ("email/agentmail", "productivity/box", "security/1password",
          "productivity/shop"),
         "own inbox, files and logins"),
    Role("marketer", "marketer",
         ("creative/social-media-content-calendar", "social-media/reddit-reading",
          "creative/meme-generation"),
         "plans campaigns, reads communities, makes the assets"),
    Role("watcher", "watcher",
         ("devops/watchers", "research/blogwatcher", "productivity/live-dashboard"),
         "polls sources, dedupes, pings you, keeps a board"),
    Role("designer", "designer",
         ("creative/sketch", "creative/impeccable", "creative/design-md",
          "creative/comfyui"),
         "mocks, design tokens, generated images"),
    Role("analyst", "analyst",
         ("finance/excel-author", "data-science/jupyter-notebook", "finance/stocks",
          "productivity/live-dashboard"),
         "workbooks, notebooks, live numbers"),
    Role("tutor", "tutor",
         ("productivity/memento-flashcards", "creative/concept-diagrams",
          "creative/baoyu-comic", "research/qmd"),
         "cards, diagrams, explainers, search over your own notes"),
    Role("planner", "planner",
         ("productivity/decision-questionnaire", "communication/one-three-one-rule",
          "software-development/subagent-driven-development"),
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
    """``official/<category>/<name>`` for each skill, in pick order."""
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
        shown = ", ".join(self.installed or self.wanted)
        if self.failed:
            shown += " (failed: {})".format(", ".join(self.failed))
        if len(shown) > MAX_SKILLS_SHOWN * 18:
            shown = shown[: MAX_SKILLS_SHOWN * 18].rsplit(",", 1)[0] + "..."
        return ["  skills   {} {}/{} installed: {}".format(
            self.role, len(self.installed), len(self.wanted), shown)]


def _which_hermes() -> str:
    return shutil.which("hermes") or "hermes"


def _run(args: Sequence[str], timeout: int) -> tuple[int, str]:
    try:
        done = subprocess.run(
            list(args), capture_output=True, text=True, timeout=timeout
        )
        return done.returncode, (done.stdout or "") + (done.stderr or "")
    except Exception as exc:  # missing binary, timeout, permission
        return 1, "{}: {}".format(type(exc).__name__, exc)


def _present(skills_dir: Path, name: str) -> bool:
    """Skills live at ``skills/<category>/<name>`` (or bare ``skills/<name>``)."""
    for folder in skills_dir.glob("*/" + name):
        if (folder / "SKILL.md").is_file():
            return True
    return (skills_dir / name / "SKILL.md").is_file()


def verify(home: Path, role: Role) -> list[str]:
    """Skills that are really on disk for that profile, read off the profile."""
    skills_dir = Path(home) / "skills"
    return [
        skill.rsplit("/", 1)[-1]
        for skill in role.skills
        if _present(skills_dir, skill.rsplit("/", 1)[-1])
    ]


def install(
    profile: str,
    home: Path,
    role: Role,
    *,
    runner: Callable[[Sequence[str]], tuple[int, str]] | None = None,
    hermes: str | None = None,
) -> Report:
    """Install the role's skills into one profile, then believe the disk."""
    binary = hermes or _which_hermes()

    def one(identifier: str) -> tuple[str, bool]:
        args = [binary, "-p", profile, "skills", "install", identifier, "--yes"]
        code, _ = (runner(args) if runner else _run(args, INSTALL_TIMEOUT))
        return identifier, code == 0

    wanted = official(role)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        outcomes = list(pool.map(one, wanted))

    on_disk = set(verify(home, role))
    installed, failed = [], []
    for identifier, ok in outcomes:
        short = identifier.rsplit("/", 1)[-1]
        if ok and short in on_disk:
            installed.append(short)
        else:
            failed.append(short)
    return Report(role.name, [w.rsplit("/", 1)[-1] for w in wanted], installed, failed)
