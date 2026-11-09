# Concierge build spec: batch 1

> Historical design notes from before the 0.9 rewrite. The shipped behaviour is
> described in [README.md](README.md); where this file disagrees with the code, the
> code is right.

> Archived build brief. This file is what was handed to the first round of coding
> agents, kept for provenance. It is not a description of the finished plugin: the
> surface is now four commands (`/concierge`, `/concierge create`, `/concierge improve`, `/concierge undo`),
> `cost.py` was never built, and everything below describes the first draft only.
> The current truth is `README.md`.

Read this whole file before writing code. It is the contract. If something here is
wrong or impossible, stop and say so in your final answer; do not invent a workaround.

## Repo

`/home/andres/.hermes/plugins/concierge` is a flat Hermes directory plugin:

```
/home/andres/.hermes/plugins/concierge/
  plugin.yaml
  __init__.py        # register(ctx), already present, do not touch
  match.py           # agent A writes this
  cost.py            # agent B was to write this; never built, the card counts tool names only
  tests/harness.py   # already present, do not touch
  tests/test_match.py
  tests/test_cost.py # never built
```

Flat means modules sit NEXT TO `plugin.yaml`, not in a subdirectory. `hermes plugins
validate` fails on a subdirectory layout. Modules import each other with relative
imports (`from . import cost`) because the loader mounts the plugin root as a package.

Constraints, all hard:

- Python standard library only. No third-party imports, no pytest.
- No network, no subprocess, no LLM call, no filesystem write in `match.py` or `cost.py`.
- `/home/andres/.hermes/hermes-agent` is READ-ONLY reference. Read it, never edit it,
  never import from it at runtime (tests may not either).
- Do not touch any file outside `/home/andres/.hermes/plugins/concierge`.
- No em dashes or en dashes in prose or comments. Plain words.

## How to run the tests

```
cd /home/andres/.hermes/plugins/concierge && python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Tests use `unittest`, and load modules through `tests/harness.py`:

```python
from harness import load          # when run with -s tests, the tests dir is on sys.path
match = load("match")
```

If discovery will not resolve `harness`, use `import harness` after
`sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))`.

## The catalogue entry shape (real, read from core)

`hermes_cli.plugin_catalog.load_catalog_live()` returns a list of
`PluginCatalogEntry` dataclasses with these fields:

```
name, title, description, repo, sha, maintainer, tier, category,
requires_hermes, subdir, docs_url, version, image, screenshots, readme,
platforms, onboarding, capabilities, known_issues
```

`description` is often a long paragraph. `category` is a short word (`tools`,
`memory`, ...). `tier` is `community` or `official`. Live count today: 1,063 entries.
Never hardcode that number anywhere; read it at runtime.

## Agent A: `match.py`

A deterministic ranker. Given what the user typed and the live catalogue, it returns
the entries worth showing or a clean no-match. No model, no embeddings, no randomness.

```python
FLOOR: float                     # module constant, tuned so the demo cases below pass

@dataclass(frozen=True)
class Candidate:
    name: str
    description: str
    category: str = ""
    tier: str = ""
    repo: str = ""
    sha: str = ""

@dataclass(frozen=True)
class Match:
    candidate: Candidate
    score: float
    why: tuple[str, ...]         # short matched terms, for the card

@dataclass(frozen=True)
class Result:
    query: str
    verdict: str                 # "match" or "no_match"
    matches: tuple[Match, ...]   # descending score, at most `limit`, ties broken by name
    sentence: str                # one plain sentence the card shows verbatim

def from_catalog(entry) -> Candidate: ...
def normalise(text: str) -> tuple[str, ...]: ...
def rank(query: str, candidates: Sequence[Candidate], limit: int = 3,
         floor: float = FLOOR) -> Result: ...
```

Behaviour that must hold, each one as a test:

1. `rank("marketing bot for my agency", catalogue)` returns `verdict="match"` and at
   least one match. This is the demo's first card and may never be empty.
2. `rank("teleport me to tokyo", catalogue)` and `rank("book my dentist appointment",
   catalogue)` both return `verdict="no_match"` with an empty `matches` tuple and a
   `sentence` that says plainly that nothing in the catalogue does that.
3. Determinism: calling `rank` twice with identical input gives identical output,
   including ordering. No `set` iteration order leaks into results; sort with a name
   tiebreak.
4. `Match.why` holds at most 4 terms, each present in the candidate's text.
5. `limit` is respected; scores are floats in `0.0..1.0`.
6. `from_catalog` tolerates a missing `category` or `tier` and a `description` of 4000
   characters without raising.

Scoring is your call. A workable shape: normalise to lowercase word tokens, drop a
small stopword list, expand a short synonym table (bot/agent/assistant,
marketing/growth/promo, hire/install/add), score on token overlap in name and
description with the name weighted higher and long descriptions damped so a
4000-character blob does not win on volume alone. Explain the chosen FLOOR in one
comment line with the two demo queries it separates.

## Agent B: `cost.py`

The card shows a token figure. It is a ceiling derived from declared tool schema bytes.
It is never a measurement of usage, and the rendered string must say so.

```python
CHARS_PER_TOKEN = 4              # matches core: agent/model_metadata.py:2340

@dataclass(frozen=True)
class Ceiling:
    tool_count: int
    tokens: int
    basis: str

def measure(schemas: Sequence[Mapping[str, Any]]) -> Ceiling: ...
def line(ceiling: Ceiling) -> str: ...
```

Behaviour that must hold, each one as a test:

1. `measure([])` gives `tool_count=0`, `tokens=0`, and a `line()` that still reads as
   honest (no division by zero, no "None").
2. `measure` counts serialised schema bytes with `sort_keys=True` and
   `separators=(",", ":")`, divides by `CHARS_PER_TOKEN`, rounds UP (ceiling, never
   understate).
3. `line(measure(schemas))` contains the tool count, the token figure with thousands
   separators, and the words `ceiling` and `not` in that order, for example:
   `12 tools - about 1,480 tokens of schema - ceiling, not usage`.
4. Same schemas in, same Ceiling out, twice.
5. A schema dict containing a non-JSON-serialisable value does not raise; the value is
   counted as a stable repr instead.
6. `basis` is a fixed string naming the source (`declared tool schema`), so the card
   can label what it is.

## Live catalog facts (verified 2026-11-05, do not re-derive)

`hermes_cli.plugin_catalog.load_catalog_live()` returns **977** entries. Each entry
is a dataclass with exactly these fields:

```
name repo sha description maintainer tier category requires_hermes subdir docs_url
version image screenshots readme platforms title onboarding capabilities known_issues
```

`capabilities` is a dict whose keys include `provides_tools`, `provides_hooks`,
`provides_middleware`, `requires_env`. `tier` is a string such as `community`.
`sha` is the exact 40-character pin. A real entry, for shape reference:

```
name=hermes-themes-pack  tier=community  category=general  version=1.2.0
sha=c3147a9f08b3d704b706aeed983b0081ce72dbd7
title=Hermes Themes Pack  platforms=[]  onboarding=False  known_issues=[]
```

## How to run Python here

The interpreter that has Hermes dependencies is the staged runtime venv:

```
/home/andres/.hermes/installs/efa56cb662777d08/environments/ae12b292110447cf8b2bda983d205ede/venv/bin/python
```

Run tests from `/home/andres/.hermes/plugins/concierge` with that interpreter, prefixing
`PYTHONPATH=/home/andres/.hermes/hermes-agent` only when a test needs core. Plain
`python3` lacks `ruamel` and will fail on any core import.

## Agent C: `effects.py`

Never touched during tests: the real SOUL, the real cron store, the real skills
directory. Every core call is injected, with a lazy default.

```python
@dataclass(frozen=True)
class Snapshot:
    path: str
    backup: str          # empty when the file did not exist
    existed: bool

def soul_text(title: str, duties: Sequence[str], boundaries: Sequence[str]) -> str: ...
def write_soul(path: str, text: str) -> Snapshot: ...
def restore_soul(snapshot: Snapshot) -> None: ...
def install_skills(names: Sequence[str], installer: Callable[[str], Any]) -> list: ...
def arm_cron(prompt: str, creator: Callable[..., str], schedule: str = "* * * * *") -> str: ...
```

Behaviour that must hold, each one as a test:

1. `soul_text` is deterministic, plain prose, no dashes as punctuation, under 1200
   characters, and its first line names the role.
2. `write_soul` copies an existing file to `<path>.concierge-backup` before
   overwriting and returns `existed=True`; on a missing file it writes fresh,
   returns `existed=False`, `backup=""`, and creates parent directories.
3. `restore_soul` puts the backup back byte for byte, and on `existed=False`
   removes the file it wrote.
4. `install_skills` calls the injected installer once per name, in order, and
   returns one record per name carrying the name and the installer's return.
5. `arm_cron` calls the injected creator with the prompt and schedule as keywords
   and returns the id it produced.
6. Nothing in the module imports `hermes_cli`, `cron`, `tools`, or reads the
   environment at import time.

Write `/home/andres/.hermes/plugins/concierge/effects.py` and
`/home/andres/.hermes/plugins/concierge/tests/test_effects.py`. Tests use `tempfile` and a fake
installer/creator. In your report, name the core function you would bind as the
default installer and its real signature, read from the repo, plus the file and
line you read it from.

## Agent D: command surface

You own exactly two files: `/home/andres/.hermes/plugins/concierge/plugin.yaml` and
`/home/andres/.hermes/plugins/concierge/__init__.py`. Nothing else. Do not edit `seams.py`,
`match.py`, `cost.py`, `effects.py`, or `SPEC.md`.

Read, in this order, before writing anything:

1. `/home/andres/.hermes/plugins/concierge/SPEC.md` (this file)
2. `/home/andres/.hermes/hermes-agent/plugins/disk-cleanup/__init__.py`
3. Two more in-tree plugin entrypoints that register a slash command, found with
   `grep -rln "commands" /home/andres/.hermes/hermes-agent/plugins/*/plugin.yaml`
4. The `ctx` object's command registration method, at its definition

Then:

- `plugin.yaml` declares `capabilities:` that match, key for key, what the
  registered behaviour actually does. No capability you cannot point to a line of
  code for. Keep `name`, `version`, `author`, and a one-sentence description.
- `__init__.py` registers one slash command handler for `/concierge` that parses
  a single free-text argument and hands it to `card.handle(text)`, imported
  lazily inside the handler so a missing sibling never breaks plugin load.
- Run `hermes plugins validate /home/andres/.hermes/plugins/concierge` and paste the **entire**
  output, all lines, no `head`, no `tail`. If it emits warnings, list each one and
  say whether it is fixable without touching core.

`card.py` does not exist yet and is not yours. A validation refusal that blames
`card` is expected; report it and leave the file alone.

## Report back

In your final answer, state: the file you wrote, the exact test command, its real
output line (`Ran N tests ... OK`), the tuned FLOOR or constant you chose and the two
demo queries that separate it, and anything in this spec that turned out wrong.
Never report success without pasted command output.
