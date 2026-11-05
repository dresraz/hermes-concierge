# Concierge

Install a bot or a skill set like an app: **one sentence, one card, one yes, a receipt, and an undo.**

Concierge is a Hermes Agent plugin. It answers one question — *"can I add that?"* — without making you learn the catalog, read a manifest, or remember which of the ~977 entries does the thing.

```
/concierge remember what I told you across sessions
```

```
Concierge

  you said    remember what I told you across sessions
  best match  cognee  (community, memory)
  why         remember, across, sessions
  what        Knowledge-graph memory for Hermes, shared with Cognee's Claude Code, Codex and OpenClaw plugins: automatic recall, remember, forget, recaps and code search
  adds        6 tools, 4 hooks
  cost        6 tools, sent on every request like every other tool
  install     https://github.com/topoteretes/cognee-integrations v1.4.1 @ b13274096018

  also        entropicmem  (community)

Install it?  /concierge yes   or   /concierge no
```

The runner-up is named, never numbered. `/concierge more` describes it and `/concierge entropicmem` installs it by name. No single key installs something the card did not describe.

`/concierge yes` installs it through Hermes's own catalog installer, with Hermes's own scan report and consent gate, then reads the result back off the disk:

```
Installed cognee

  on disk     $HERMES_HOME/plugins/cognee (76 files)
  enabled     yes
  scan        safe, 80 notes

Undo it with /concierge undo
```

When nothing fits, it installs nothing:

```
  best match  none

Nothing in the catalog does that yet. Nothing was installed.
```

The matcher is keyword-based, so a nonsense sentence can still surface one weak card
(it never installs anything without your yes). On our junk set, 7 of 8 absurd asks
return nothing at all.

## One command

Everything is a word after `/concierge`. There is no `/hire` and no `/train` to remember.

```
  CONCIERGE
  Bots and skills, one sentence at a time.

  /concierge <sentence>          install the best match from the catalog
  /concierge hire <sentence>     make a new bot
  /concierge train <bot>: <what> teach a bot one standing habit
  /concierge bots                list the bots Concierge made
  /concierge remove <n>          delete bot number n
  /concierge reset <n>           take back what Concierge changed in bot n
  /concierge undo                take back the last thing Concierge did
  /concierge help                this list
```

`/concierge` with nothing after it prints that same list.

## Hire: a sentence becomes a bot

```
/concierge hire bp-test-zero: keeps my inbox at zero and drafts replies
```

```
Hired bp-test-zero

    home     /home/andres/.hermes/profiles/bp-test-zero
    soul     SOUL.md, 265 chars
    skills   0 installed
    profile  listed by hermes profile list

  next     /concierge train bp-test-zero: <habit>
  undo     /concierge undo
```

The word before the colon is the name. Without a colon the name is the last meaningful word, so `/concierge hire keeps my inbox at zero` hires `inbox-bot`.

The bot is created through core's own `create_profile`, so it shows up in `hermes profile list` like any other profile, with its own memory, skills and cron.

Training is a sentence too:

```
/concierge train bp-test-zero: always answer in one line
```

```
Trained bp-test-zero

    skill    /home/andres/.hermes/profiles/bp-test-zero/skills/always-answer-in-one-line/SKILL.md
    front    name and description parse
    listed   always-answer-in-one-line is in bp-test-zero's skills
    next     start a session as bp-test-zero and it is in the prompt index

  undo     /concierge undo
```

## Lifecycle: the bots it made, in one sentence

```
/concierge bots
```

```
  BOTS  2

   1  inbox-bot       Triage my inbox
   2  newsletter-bot  Writes my weekly newsletter

  remove <n>  delete that bot
  reset <n>   take back what Concierge changed in it
```

`remove` deletes a bot Concierge created. `reset` takes back only Concierge's own changes and leaves the bot standing:

```
Reset: inbox-bot (2 changes)

  removed: skill $HERMES_HOME/profiles/inbox-bot/skills/always-answer-in-one-line
  kept: the bot itself (delete it with /concierge remove)
```

Both take a number or a name.

**`default` is never deleted.** `remove default` is refused and points at `reset default`, which replays only the records Concierge wrote for that profile. Same for any profile Concierge did not create: it is refused, because deleting something it cannot name is not a concierge's job.

## Why a plugin and not a prompt

A prompt cannot read the live catalog, cannot rank every real entry in it against your sentence, cannot call core's installer, cannot write an install record, and cannot undo it. Concierge does all five, and it never invents a plugin or a bot that does not exist.

## How it works

- `commands.py` is the whole command surface: one verb table, one card protocol, one record store.
- `match.py` ranks the live catalog against your sentence. Pure, deterministic, no model call, no network. Tokenize, fold plurals, bridge an outcome to a mechanism with a small hand-written vocabulary so *"remember this forever"* reaches memory providers instead of scoring zero. Each candidate carries the words that earned it, which is what `why` prints.
- `card.py` renders the catalog card, takes the yes or no, and prints the receipt once an install lands.
- `lifecycle.py` lists, removes and resets — the only place that decides what may be deleted.
- `bots.py` turns a sentence into a profile name, a title, a duty list and a `SOUL.md`.
- `training.py` turns a sentence into one `SKILL.md` in that bot's skills directory.
- `seams.py` is the only module that calls Hermes core: catalog, installer, scan gate, profiles, hook registration.
- `effects.py` holds the filesystem writes, injected so tests never touch a real directory.
- `undo.py` reverses the last thing Concierge did, then checks the disk before dropping the record.
- `state.py` keeps one record per install, tagged with what kind it is.

## Matching, measured

`tests/eval_match.py` is a fixed set of 32 realistic asks plus 8 nonsense ones, scored against the live catalog:

| | result |
|---|---|
| correct entry in the top 3 | **32/32** |
| correct entry ranked first | 25/32 |
| nonsense installs nothing | 7/8 |

No LLM call is involved, so those numbers are the same on every run. The single nonsense miss is a sentence with real words in it; the card still asks first, which is the point of the card.

## Cost

Concierge adds no tools to the request. The only per-request cost is the plugin's own registration. The card tells you when a plugin you are about to add does add tools, hooks, or middleware, counting what the catalog declares. It prints no token figure, because the catalog carries no schemas and a number there would be a guess.

## Safety

- Dependencies ride the one yes. If the plugin's own repo declares Python packages, the card says
  which ones before you confirm (`deps  httpx, websockets  installed with it, no extra question`),
  and says so plainly when a package comes from git instead of PyPI. The receipt re-reads the
  installed tree and lists what actually landed. No second prompt: the catalog is pre-screened, so
  the pinned plugin's declared packages are the safe default.
- Installs only through `hermes_cli`'s catalog install, so the same platform check, scan, dependency consent and pinning that `hermes plugins install` gives you apply here.
- A `caution` rating costs a second explicit yes, as text, so it reaches you in the CLI, the TUI and the gateway alike. A `dangerous` rating is never installed.
- The card never asks for, holds, or prints a secret. If an entry needs one, it shows the requirement label and nothing else.
- `default` cannot be removed; it can only be reset to what Concierge changed.
- Anything Concierge did not create cannot be removed through Concierge.
- `undo` is a record diff, not a guess: it reverses exactly what the record says was written, then checks the disk. A partial undo keeps the record so you can run it again.
- No background processes, no self-updater, no telemetry, no network calls of its own.

## Development

```
cd /home/andres/concierge
PYTHONPATH=/home/andres python -m unittest discover -s tests
PYTHONPATH=/home/andres python tests/eval_match.py
hermes plugins validate /home/andres/concierge
```

Tests are `unittest`, stdlib only, deterministic, and make no LLM calls. They never touch a real profile, a real SOUL file, or a real plugins directory: every seam is injected.

## License

MIT
