# Concierge

[![license](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)
[![tests](https://img.shields.io/badge/tests-43%20passing-3fb950)](tests)
[![hermes](https://img.shields.io/badge/hermes-%3E%3D0.22.7-4B5563)](plugin.yaml)

**The front door to the Hermes marketplace.**

One sentence installs the right skill or plugin, or makes you a bot with the right ones already in it.
No catalog to learn, no manifest to read, no restart. One sentence, one receipt read off the disk, and
one undo.

```
/concierge something that reads my pdfs
/concierge make me a researcher
/concierge undo
```

## What it does

- **Installs** from Hermes's own published marketplace lists (skills, plugins and connectors),
  refreshed daily. It never ships its own copy of the catalog, so what it offers is what the
  marketplace has today.
- **Creates bots** from ten presets, each a small, light skill set: researcher, writer, coder,
  assistant, marketer, watcher, designer, analyst, tutor, planner. A bot is a core profile
  (`hermes profile create --clone`), so aliases, config and skills stay core's work.
- **Improves a bot** by adding a skill, or by writing one habit into its `SOUL.md`.
- **Deletes a bot** it created, after a confirmation, and never one it did not create.
- **Undoes** the last change from a receipt on disk.

## What it refuses

- It does not run from a shared chat. A gateway platform needs the owner's opt-in:
  `plugins.entries.concierge.allow_gateway: true`.
- It does not copy your login into a bot. Copying `auth.json` forks single-use OAuth grants: the
  first profile to refresh revokes every other copy. A bot resolves credentials through the
  credential pool, and a bot that needs its own gets one with
  `hermes -p <bot> auth add <provider>`.
- It does not touch another bot from inside a bot. Inside a bot, the command only changes that bot.

## How it decides

The model your Hermes already runs reads your sentence and answers one small plan: which action,
which bot, which marketplace thing, which preset role. The code carries that answer out against real
names it just read from the marketplace. Six start-of-sentence patterns exist so `search`, `undo`,
`bots`, `install <name>` and a pending yes or no still work when no model is available; every other
sentence goes to the model.

## Install

```
hermes plugins install dresraz/hermes-concierge --enable
```

Then, in any chat the owner controls:

```
/concierge help
```

## Development

Plain Python, nothing outside Hermes itself.

```
python3 -m unittest discover -s tests -t tests
```

`hermes plugins validate .` runs the same admission checks the marketplace does.
