# Adversarial audit brief (Concierge role presets)

Read-only review. Do not edit files, install anything, create profiles, or run Hermes commands that
write. You are auditing a shipped product, so be blunt and specific.

## What is being reviewed

`/home/andres/concierge/presets.py` defines ten role presets. A person says one sentence
("hire a researcher") and Concierge creates a Hermes profile and installs that role's skills.
Facts about every pick are in `/home/andres/concierge/docs/audit_input.json`: the skill name, its
optional/bundled tier, its on-disk path, and its real frontmatter description.

The suite already proves every name exists and installs (134 tests). Nobody has judged whether the
SET is any good: whether these ten to fifteen skills actually let the bot do the job the role
promises, without dead weight.

## The bar

A preset is good when a stranger who hired that bot gets a working colleague, not a pile of tools:

1. **Covers the job end to end.** The role's promise (its `blurb`) is the contract. Reading,
   producing, checking, and delivering are all covered. A gap means the bot stalls and asks for a
   skill the hire did not provide.
2. **Lean wins.** The target is the smallest set that still finishes the job. Five skills is a
   strong preset when five do the work. Fifteen is only defensible when the job really contains
   fifteen distinct tasks. Anything duplicated, rarely reached for, or included to look thorough
   gets cut. If removing a pick leaves the bot able to finish the job, remove it.
3. **Every pick earns its place.** If a pick is never the right tool for that job, it is noise, and
   noise makes the receipt dishonest.
4. **No two picks do the same job.** Overlap wastes install time and invites the bot to dither.
5. **No invented capability.** Picks must be real Hermes skills with real descriptions. Do not
   propose a skill that is not on disk.
6. **The role is realistic for a solo operator.** These bots work for one person, in chat, with no
   team, no admin rights, no budget by default. A preset built for a Fortune 500 workflow is slop.

For each role, state the minimum viable count and the one task that would break if you cut
further. That sentence is the justification for the set.


## Roles and their promise

- researcher: reads sources, follows feeds, keeps citations
- writer: finds the angle, writes it plain, illustrates and ships it
- coder: debugs, searches structure, reviews, documents the repo
- assistant: own inbox, calendar, files and notes
- marketer: plans campaigns, reads communities, makes the assets
- watcher: polls sources, dedupes, pings you, keeps a board
- designer: mocks, diagrams, tokens, generated images
- analyst: workbooks, decks, notebooks, live numbers
- tutor: cards, diagrams, explainers, search over your own notes
- planner: turns a fog into options, a pick, and a plan of record

## Candidate pool

Skills live on disk, two tiers, both readable:

- `/home/andres/.hermes/hermes-agent/optional-skills/<category>/<name>/SKILL.md`
- `/home/andres/.hermes/hermes-agent/skills/<category>/<name>/SKILL.md`

Enumerate what exists with `find … -name SKILL.md`, then read descriptions from the files. Only
propose an identifier you have seen on disk, in the form `<category>/<name>` for optional skills or
the bare `<name>` for bundled ones.

## Output contract

End with a compact report, no preamble:

```
ROLE <name>
KEEP: <count>/<total> earn their place
CUT: <identifier> — <why it is dead weight, one line>
SWAP IN: <identifier> — <what gap it closes, one line>
VERDICT: strong | thin | wrong-shaped
```

Then one short block: "SOUL REQUIREMENTS" listing, per role, the three to five behaviours a good
soul for that bot must force (default workflow, output defaults, what it refuses, what it asks
before doing). No cuisine, no persona fluff, no adjectives about excellence.
