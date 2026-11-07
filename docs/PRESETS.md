# Roles

A role is the short sentence a person already says, plus the skills and the soul
that make the resulting bot able to do the job. Ten of them, nothing else to learn.

```text
/concierge create a researcher for papers
```

```text
Hired researcher-bot

    home     /home/andres/.hermes/profiles/researcher-bot
    soul     SOUL.md, 1084 chars
    skills   9 installed
    profile  listed by hermes profile list
  skills   researcher 8/8 installed: parallel-cli, qmd, llm-wiki, rss-feeds, arxiv, grounded-citations, blocked-page-recovery, pdf

  next     /concierge improve researcher-bot: <habit>
  undo     /concierge undo
```

## The ten

Each line below lists what a role lands. Names before the `+` are optional skills installed through
core. Names after it are bundled skills copied in once the install finishes, because core's installer
archives a same-name skill that is already present. The assistant line opens with the `+`, so all
seven of its picks are bundled.

| role | job in one line |
|---|---|
| researcher | reads sources, follows feeds, keeps citations |
| writer | finds the angle, writes it plain, illustrates and ships it |
| coder | debugs, searches structure, reviews, documents the repo |
| assistant | owns inbox, calendar, files and notes |
| marketer | plans campaigns, reads communities, makes the assets |
| watcher | polls sources, dedupes, pings you, keeps a board |
| designer | mocks, diagrams, tokens, generated images |
| analyst | workbooks, decks, notebooks, live numbers |
| tutor | cards, diagrams, explainers, search over your own notes |
| planner | turns a fog into options, a pick, and a plan of record |

What each one lands:

```
researcher  parallel-cli qmd llm-wiki rss-feeds
            + arxiv grounded-citations blocked-page-recovery pdf
writer      creative-ideation baoyu-article-illustrator parallel-cli publish-site
            + humanizer youtube-content grounded-citations obsidian
coder       python-debugpy rest-graphql-debug ast-grep code-wiki
            + github systematic-debugging test-driven-development requesting-code-review
assistant   + email-inbox-triage google-workspace microsoft-office pdf
            document-to-action-items weekly-review-planning obsidian
marketer    baoyu-article-illustrator social-media-content-calendar reddit-reading
            parallel-cli + xurl humanizer baoyu-infographic
watcher     watchers rss-feeds scrapling live-dashboard
            + product-price-monitor competitor-news-monitor blocked-page-recovery xurl
designer    sketch design-md comfyui excalidraw publish-site
            + baoyu-infographic popular-web-designs claude-design
analyst     excel-author pptx-author stocks jupyter-notebook live-dashboard parallel-cli
            + google-workspace pdf grounded-citations
tutor       memento-flashcards concept-diagrams baoyu-comic qmd
            + grounded-citations manim-video obsidian
planner     decision-questionnaire one-three-one-rule grill-me qmd
            + document-to-action-items obsidian google-workspace
```

Counts: researcher 8, writer 8, coder 8, assistant 7, marketer 7, watcher 8,
designer 8, analyst 9, tutor 7, planner 7 = **77 picks**, down from 129.

## The bar: lean

The rule is the smallest set that finishes the job end to end, not the largest
set that sounds impressive. Five is right when five do the work; fifteen is right
only when the job really has fifteen separate steps. If dropping a skill still
lets the bot finish, it is dropped.

Two adversarial reviewers applied that rule, one mechanical and one end-to-end,
and the sets above are where they agreed. The four things they changed:

- `comfyui` out of marketer: the campaign asset step is finished by
  `baoyu-infographic` and `baoyu-article-illustrator`, and the diffusion-GPU
  setup stalls a no-budget run.
- `xurl` into watcher: RSS and page polling cannot see X posts, so a watcher
  asked to watch an X account failed without it.
- `grill-me` into planner: turning options into a defended pick needs the
  adversarial interview, or the plan reads as a list of maybes.
- `node-inspect-debugger` out of coder: the Python debugger plus
  `systematic-debugging` finishes solo debugging.

## Rules the list obeys

- **Every name is real.** Optional identifiers resolve to
  `optional-skills/<category>/<name>/SKILL.md`; bundled names resolve in the
  core tree. `tests/test_presets.py` fails on any invented name.
- **No memory plugins.** Memory is core, and swapping it is a decision, not a
  hiring default.
- **The disk is the receipt.** A skill counts as installed only if its
  `SKILL.md` is on disk, not under `.archive/`, and not a dot entry. A zero exit
  code with nothing on disk is reported as a failure.
- **Bundled copies land last.** `hermes skills install` archives a same-name
  skill already present, so a copy made before the install pool would be retired
  under `.archive/` while the receipt claimed it.
- **The soul is written before the skills.** If the skills half fails, the bot
  still knows how to behave, and the receipt reads the file to prove what landed.

## Souls

Each role ships a soul: a standing instruction set, not a bio. It names the
workflow, the shape of the reply, what the bot refuses, and how it talks about
the skills it actually has. `scripts/soul_lint.py` gates every one:

- 420 to 1200 characters, and it must name a workflow, an output default and a
  refusal;
- no filler ("as an AI", "delve into", "seamless", "game-changing", and friends);
- it may only claim skills the role really lands;
- no paragraph shared between two roles.

Ten souls, 969 to 1109 characters each, all clean. `tests/test_souls.py` makes
the gate binding and proves the hired profile gets the role soul, not the generic
one.

## Detection

`presets.detect(sentence)` is pure and deterministic: word-boundary cues, the
longest cue wins, plural and `-ing` forms included. `assistant` is deliberately
*not* a cue, because people say "a research assistant" and mean researcher.

No role matched means no preset: the bot is still hired with its generic soul,
and the receipt simply has no skills line. Nothing is guessed.

## Installs go through core

Each optional skill is installed as

```text
hermes -p <profile> skills install official/<category>/<name> --yes
```

several at a time, so the new profile gets core's own scan, provenance and
`skills_guard` verdict rather than a file copy. Measured on this machine: about
0.4s to create a profile, and 1.5s to 2.9s to land a whole role's set from a
warm cache (a cold `comfyui` install was 50s the first time).

If the installer is missing or refuses a skill, the bot still exists; the
receipt says which skills failed and `undo` still removes the whole profile.
