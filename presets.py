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
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

MAX_SKILLS_SHOWN = 6
INSTALL_TIMEOUT = 90  # one skill, not a whole role, has to finish in this


# A preset is a sentence long. A skill this heavy is a decision the person makes
# on purpose ("install comfyui"), never something a role drags in.
HEAVY_KB = 150

# Not about kilobytes alone: comfyui drags in diffusion models and wants a GPU,
# and popular-web-designs is 855 KB of reference images. A role never installs
# either; a person asks for it by name when they want it.
HEAVY_NAMES = frozenset({"comfyui", "popular-web-designs"})


def heavy(name: str) -> bool:
    if name.rsplit("/", 1)[-1] in HEAVY_NAMES:
        return True
    return False


def weight(path: Any) -> int:
    """Kilobytes of a skill folder, so "is this heavy" is a number, not a vibe."""
    from pathlib import Path as _Path

    total = 0
    for item in _Path(str(path)).rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total // 1024


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
    Role('researcher', 'researcher',
         ('research/rss-feeds', 'research/parallel-cli'),
         ('arxiv', 'grounded-citations', 'pdf', 'blocked-page-recovery'),
         'reads sources, follows feeds, keeps citations'),
    Role('writer', 'writer',
         ('creative/simple-english', 'creative/baoyu-article-illustrator', 'web-development/publish-site'),
         ('humanizer', 'youtube-content'),
         'finds the angle, writes it plain, illustrates and ships it'),
    Role('coder', 'coder',
         ('software-development/ast-grep', 'software-development/code-wiki'),
         ('github', 'systematic-debugging', 'requesting-code-review', 'test-driven-development'),
         'debugs, searches structure, reviews, documents the repo'),
    Role('assistant', 'assistant',
         (),
         ('email-inbox-triage', 'google-workspace', 'pdf', 'document-to-action-items', 'weekly-review-planning', 'meeting-action-items', 'obsidian'),
         'own inbox, calendar, files and notes'),
    Role('marketer', 'marketer',
         ('creative/social-media-content-calendar', 'social-media/reddit-reading', 'creative/meme-generation'),
         ('xurl', 'baoyu-infographic'),
         'plans campaigns, reads communities, makes the assets'),
    Role('watcher', 'watcher',
         ('devops/watchers', 'research/rss-feeds', 'research/blogwatcher', 'productivity/live-dashboard'),
         ('product-price-monitor', 'competitor-news-monitor'),
         'polls sources, dedupes, pings you, keeps a board'),
    Role('designer', 'designer',
         ('creative/sketch', 'creative/excalidraw', 'creative/design-md', 'creative/archify'),
         ('claude-design', 'baoyu-infographic'),
         'mocks, diagrams, tokens, infographics'),
    Role('analyst', 'analyst',
         ('finance/excel-author', 'finance/pptx-author', 'data-science/jupyter-notebook', 'finance/stocks', 'productivity/live-dashboard'),
         ('microsoft-office',),
         'workbooks, decks, notebooks, live numbers'),
    Role('tutor', 'tutor',
         ('productivity/memento-flashcards', 'creative/concept-diagrams', 'research/qmd'),
         ('grounded-citations', 'manim-video'),
         'cards, diagrams, explainers, search over your own notes'),
    Role('planner', 'planner',
         ('productivity/decision-questionnaire', 'communication/one-three-one-rule', 'software-development/grill-me'),
         ('document-to-action-items', 'weekly-review-planning'),
         'turns a fog into options, a pick, and a plan of record'),
)

_BY_NAME = {role.name: role for role in ROLES}

# Words a person actually types. Matched on word boundaries, whole-sentence safe.
CUES: dict[str, tuple[str, ...]] = {
    "researcher": ("research", "researcher", "sources", "papers", "arxiv",
                   "literature", "cite", "citations", "deep dive"),
    "writer": ("write", "writer", "writing", "blog", "article", "newsletter",
               "copywriting", "draft", "thread"),
    "coder": ("code", "coder", "coding", "developer", "programmer",
              "debug", "refactor", "repo", "pull request", "tests"),
    # "assistant" is the generic word, not a role: leave it out so
    # "hire a research assistant" lands on researcher.
    "assistant": ("inbox", "email", "calendar", "schedule", "errands",
                  "admin", "files", "logins",
                  # The generic word is a cue only inside a phrase that cannot
                  # be read as "research assistant" or "coding assistant".
                  "general assistant", "personal assistant", "virtual assistant",
                  "assistant bot", "my assistant", "an assistant",
                  "office assistant", "executive assistant"),
    "marketer": ("marketing", "marketer", "seo", "campaign", "audience", "growth",
                 "instagram", "twitter", "reddit"),
    # Bare "watch", "track" and "changes" are everyday words; only a phrase that
    # means monitoring counts, or every fitness app becomes a watcher.
    "watcher": ("watcher", "monitor", "alert", "ping me", "pings me", "notify",
                "keep an eye", "keeps an eye", "when it changes", "keep track"),
    "designer": ("design", "designer", "mockup", "mockups", "ui", "ux",
                 "brand", "illustration", "logo"),
    "analyst": ("analyse", "analyze", "analyst", "analysis", "spreadsheet",
                "excel", "metrics", "chart", "dashboard"),
    "tutor": ("tutor", "teach", "teacher", "explain", "study", "learn",
              "flashcards", "quiz", "practice", "homework"),
    "planner": ("planner", "planning", "plan my", "roadmap", "project", "sprint",
                "priorities", "decision", "schedule my", "keep me on"),
}

# The first cues of a role are the nouns that define it (inbox, spreadsheet,
# repo); the later ones are verbs anyone might use (draft, plan, watch). A verb
# must not outrank a defining noun just because it is a longer word.
_CUES = tuple(
    (role.name, cue, 2 if index < 3 else 1)
    for role in ROLES
    for index, cue in enumerate(CUES[role.name])
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
    # Punctuation is glued to words often enough to hide a role: "researcher," and
    # "writer:" both have to read as the word.
    cleaned = re.sub(r"[^a-z0-9\s'-]+", " ", (sentence or "").lower())
    text = " " + " ".join(cleaned.split()) + " "
    totals: dict[str, int] = {}
    longest: dict[str, int] = {}
    order: dict[str, int] = {}
    for index, (role_name, cue, weight) in enumerate(_CUES):
        if any(" {} ".format(form) in text for form in _forms(cue)):
            totals[role_name] = totals.get(role_name, 0) + weight
            longest[role_name] = max(longest.get(role_name, 0), len(cue))
            order.setdefault(role_name, index)
    if not totals:
        return None
    winner = max(totals, key=lambda name: (totals[name], longest[name], -order[name]))
    return _BY_NAME[winner]


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
    """Copy bundled picks into a lean profile, believing the disk.

    Core's helper resolves the tree from the running package, which points at a
    finder path under an editable install and at nothing at all when HERMES_HOME
    is a scratch home. So the copy is done here from the tree the index actually
    read, and core's helper is kept only as the first attempt.
    """
    import shutil

    from . import seams

    copied = list(seams.copy_bundled(home, names))
    want = [name for name in names if name not in copied]
    if not want:
        return copied

    from . import discover

    for name in want:
        folder = next(
            (item["path"] for item in discover.catalogue() if item["name"] == name),
            None,
        )
        if folder is None:
            continue
        target = home / "skills" / folder.parent.name / name
        try:
            shutil.copytree(folder, target)
        except Exception:
            continue
        copied.append(name)
    return copied


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

    wanted = [item for item in official(role) if not heavy(item)]
    skipped = [item for item in official(role) if heavy(item)]
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

    outcomes += [(item, False) for item in skipped]

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
