# Roles

A role is the short sentence a person already says, plus the skills that make
the resulting bot able to do the job. Ten of them, nothing else to learn.

```text
/concierge hire a researcher for papers
```

```text
Hired researcher-bot

    home     /home/andres/.hermes/profiles/researcher-bot
    soul     SOUL.md, 241 chars
    skills   0 installed
    profile  listed by hermes profile list
  skills   researcher 3/3 installed: parallel-cli, scrapling, rss-feeds

  next     /concierge train researcher-bot: <habit>
  undo     /concierge undo
```

## The ten

| role | say this | skills it lands |
|---|---|---|
| researcher | a researcher for papers | `research/parallel-cli`, `research/scrapling`, `research/rss-feeds` |
| writer | write my blog | `research/research-paper-writing`, `creative/creative-ideation`, `creative/simple-english`, `creative/baoyu-article-illustrator` |
| coder | debug this repo | `software-development/python-debugpy`, `software-development/rest-graphql-debug`, `software-development/ast-grep`, `software-development/pr-lens` |
| assistant | my inbox is a mess | `email/agentmail`, `productivity/box`, `security/1password`, `productivity/shop` |
| marketer | growth for my instagram | `creative/social-media-content-calendar`, `social-media/reddit-reading`, `creative/meme-generation` |
| watcher | keep an eye on prices | `devops/watchers`, `research/blogwatcher`, `productivity/live-dashboard` |
| designer | design a landing page | `creative/sketch`, `creative/impeccable`, `creative/design-md`, `creative/comfyui` |
| analyst | analyse my sales spreadsheet | `finance/excel-author`, `data-science/jupyter-notebook`, `finance/stocks`, `productivity/live-dashboard` |
| tutor | teach me spanish | `productivity/memento-flashcards`, `creative/concept-diagrams`, `creative/baoyu-comic`, `research/qmd` |
| planner | keep me on track with the roadmap | `productivity/decision-questionnaire`, `communication/one-three-one-rule`, `software-development/subagent-driven-development` |

## Rules the list obeys

- **Only optional skills.** The bundled tree (44 skills) arrives with core and
  is seeded into a profile the first time it runs, so a preset lists only the
  optional skills that are *not* already there. Suggesting the bundled tree
  would be noise on the receipt.
- **No memory plugins.** Memory is core, and swapping it is a decision, not a
  hiring default.
- **No invented names.** Every identifier is a real `optional-skills/<category>/<name>`
  with a `SKILL.md`. `tests/test_presets.py` checks that against the Hermes tree
  and the whole list is installed for real in `docs/NOTES.md` §14.
- **Three to five per role, best first.** More than that and the bot is a junk
  drawer, not a specialist.
- **The disk is the receipt.** A skill counts as installed only if
  `skills/<category>/<name>/SKILL.md` exists afterwards. A zero exit code with
  nothing on disk is reported as a failure.

## Detection

`presets.detect(sentence)` is pure and deterministic: word-boundary cues, the
longest cue wins, plural and `-ing` forms included. `assistant` is deliberately
*not* a cue, because people say "a research assistant" and mean researcher.

No role matched means no preset: the bot is still hired with its soul, and the
receipt simply has no skills line. Nothing is guessed.

## Installs go through core

Each skill is installed as

```text
hermes -p <profile> skills install official/<category>/<name> --yes
```

three at a time, so the new profile gets core's own scan, provenance and
`skills_guard` verdict rather than a file copy. Measured on this machine:
0.6s to create the profile, 1.2s to land three skills, 16s for the designer
role's four (the `comfyui` skill is the slow one).

If the installer is missing or refuses a skill, the bot still exists; the
receipt says which skills failed and `undo` still removes the whole profile.
