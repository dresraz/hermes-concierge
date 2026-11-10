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
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

MAX_SKILLS_SHOWN = 6
INSTALL_TIMEOUT = 90  # one skill, not a whole role, has to finish in this


# A role is never dragged in silently when it costs more than attention: the
# model reads the skill's own metadata (name, description, requirements) and
# says whether it is heavy. With no model nothing is treated as heavy.
HEAVY_PROMPT = """A skill may be heavy: it downloads large models or datasets, wants a GPU,
or ships a very large asset tree. Read its own name and description and say
whether installing it should be an explicit choice, never a silent extra.

Name: {name}
Description: {description}

Answer JSON only: {{"heavy": true or false}}"""


def heavy(name_or_entry, llm=None) -> bool:
    """True when this skill should never ride along silently with a role.

    Decided from the entry's own metadata plus the model's answer, never
    from a name list. With no model nothing counts as heavy.
    """
    if isinstance(name_or_entry, str):
        short = name_or_entry.rsplit("/", 1)[-1]
        description = ""
    else:
        short = str(
            name_or_entry.get("name") if isinstance(name_or_entry, dict)
            else getattr(name_or_entry, "name", "")
        ).rsplit("/", 1)[-1]
        description = str(
            name_or_entry.get("description") if isinstance(name_or_entry, dict)
            else getattr(name_or_entry, "description", "") or ""
        )
    if not short:
        return False
    if llm is None:
        return False
    if not description:
        description = _describe(short)
    import json

    try:
        answer = llm.complete_structured(
            instructions=HEAVY_PROMPT.format(name=short, description=description[:600]),
            input=[{"type": "text", "text": short}],
            json_mode=True,
            max_tokens=30,
            temperature=0,
            timeout=15,
        )
    except Exception:
        return False
    raw = (getattr(answer, "text", "") or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return False
    try:
        return bool(json.loads(raw[start : end + 1]).get("heavy"))
    except Exception:
        return False


def _describe(name: str) -> str:
    """The skill's own one-liner from the tree on disk, or empty."""
    try:
        from . import discover

        for item in discover.catalogue():
            if item["name"] == name:
                return str(item.get("why") or item.get("description") or "")
    except Exception:
        pass
    return ""


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

def names() -> list[str]:
    return [role.name for role in ROLES]


def get(role: str) -> Role | None:
    return _BY_NAME.get((role or "").strip().lower())


ROLE_PROMPT = """You choose the role for a new assistant from its one-line descriptions.

Sentence: {sentence}

Roles:
{roles}

Answer JSON only: {{"role": "<one role name from the list, or none>"}}
Pick the role whose job matches the sentence. Pick "none" when the sentence
names no role here. Answer with a name from the list, never a new one."""

ROLE_FALLBACK_NOTE = (
    "No model was reachable, so no role was picked."
)


def detect(sentence: str, llm=None) -> Role | None:
    """Best role for a sentence, or None.

    The model reads the sentence against the preset names and their
    one-line descriptions and picks one, or 'none'. The chosen role still
    drives the same install list. With no model nothing is picked.
    """
    if llm is None:
        return None
    import json

    roles = "\n".join("- {}: {}".format(role.name, role.blurb) for role in ROLES)
    try:
        answer = llm.complete_structured(
            instructions=ROLE_PROMPT.format(
                sentence=" ".join(str(sentence or "").split())[:300],
                roles=roles,
            ),
            input=[{"type": "text", "text": str(sentence or "")}],
            json_mode=True,
            max_tokens=40,
            temperature=0,
            timeout=20,
        )
    except Exception:
        return None
    raw = (getattr(answer, "text", "") or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        heard = str(json.loads(raw[start : end + 1]).get("role") or "").strip().lower()
    except Exception:
        return None
    if not heard or heard == "none":
        return None
    return _BY_NAME.get(heard)


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
        return ["{} skills {}/{} installed: {}.".format(
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
            # A failed copy leaves a half-written dir that makes every retry
            # fail with FileExistsError. Remove it and report one honest line.
            try:
                shutil.rmtree(target, ignore_errors=True)
            except Exception:
                pass
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
    llm=None,
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

    wanted = [item for item in official(role) if not heavy(item, llm)]
    skipped = [item for item in official(role) if heavy(item, llm)]
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
