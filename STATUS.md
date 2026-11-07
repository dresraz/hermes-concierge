# STATUS

GATE: build complete, ready to submit
Date: 2026-11-06

## Release

- `plugin.yaml` version `0.1.6`, tag `v0.1.6`, commit `c2b83e3faccb75992791cbb538bd2b4238b9fb98`.
- `docs/catalog-entry.yaml` pins that sha and `version: "0.1.6"`; the entry passes Hermes core's own
  `scripts/validate_plugin_catalog.py` (exit 0).
- 170 tests, 0 model calls, 0 network calls, 2 skipped (live-only). `python -m unittest discover -s tests`: OK.
- Live catalog at match time: 1,063 entries.
- The sentence search installs from both shelves: the plugin catalog and the skill registries, into
  this profile or into `into <bot>`. Proven live for plugin -> bot, skill -> bot, skill -> this
  profile, each with a card, a receipt and a working undo (`docs/NOTES.md` #22).

## Done

- Plugin loads and validates (`hermes plugins validate`: pass; one advisory about private core
  imports, explained in `docs/NOTES.md` #7).
- One command only: `/concierge`. `/concierge create` and `/concierge improve` are sentences inside it, not registry
  commands (verified by probing `get_plugin_commands()`: the registry key is `concierge` alone).
- Prose pass: no em dashes in the plugin's own writing (one quoted core message stays verbatim),
  no banned phrases, long paragraphs split. `scripts/soul_lint.py` still bans em dashes in souls.
- `/concierge help` lists every verb, and the three words a card accepts (yes / no / more).
  Card plus one yes installs. Create, improve, bots, remove, reset, undo all run end to end in a
  throwaway home.
- The card describes exactly one install. The runner-up is named (`also  jet-browser`) but has no
  number: `/concierge more` describes it, `/concierge <its name>` installs it. A bare `2` states
  that there is one install at a time and installs nothing (`docs/NOTES.md` #13).
- `default` cannot be deleted. `remove default` is refused; `reset default` replays only the
  records Concierge wrote. `reset` on a bot Concierge created keeps the bot standing; only
  `remove` deletes a profile.
- Dependencies ride the one yes: the card reads the plugin's own manifest at its pin and names the
  packages before confirm (9 of 40 sampled catalog entries declare any; one pulls from git and says
  so). The receipt re-reads the installed tree and lists what landed. No second question.
- Receipts are read off disk after the write, never predicted. Undo verified by re-reading.
- No receipt offers an undo it did not record: card, create and improve all report a failed record
  write and drop the undo line instead of promising a reversal with nothing behind it (#13).
- Matcher, two independent measures against the live 1,063-entry catalog, zero network, zero model:
  hand-written asks (`tests/eval_match.py`) top1 24/32, top3 31/32, 8 of 8 nonsense return nothing;
  un-tunable recall (`tests/eval_recall.py`, 120 sampled entries asked their own titles) top1 119/120,
  top3 120/120.
- Known limit, measured not hidden: one junk sentence still surfaces a card. Three candidate fixes
  were tried and all measured worse on real asks (`docs/NOTES.md` #9). A card is not an install.
- Untuned check 2026-11-06 (set never used for tuning): 16 everyday asks, 9 refused, 7 carded
  (weather and lights defensible, 5 near misses); of 8 asks that do have a fitting plugin, the best
  one came first 3 times. README quotes these numbers next to the tuned set.
- Undo of a plugin runs core's real removal (`cmd_remove`), not a guessed name;
  `tests/test_undo_defaults.py` proves it in a throwaway home with nothing injected, through the
  real command too (`docs/NOTES.md` #11).
- Ten roles create with the smallest skill set that finishes the job, 7-9 picks each (77 total,
  down from 129): optional skills installed through core's own `hermes -p <profile> skills install`
  plus bundled-tree skills copied in after the install pool. Every identifier exists in the Hermes
  tree and the bundled names are written on the receipt; a test fails on any invented name or a role
  outside 5-15. Verified role by role, all ten green: only real `SKILL.md` leaves counted,
  `failed == []`, nothing stranded in `.archive/` (`docs/NOTES.md` #14-17, `docs/PRESETS.md`).
- Lean set agreed by two adversarial reviewers (one mechanical, one end-to-end): four changes
  applied: `comfyui` out of marketer, `xurl` into watcher, `grill-me` into planner,
  `node-inspect-debugger` out of coder (`docs/PRESETS.md` § The bar).
- A soul per role: standing instructions, 969-1109 chars, written to `<profile>/SOUL.md` before the
  skills so a failed install never costs the bot. That path is core's own identity slot
  (`agent/prompt_builder.py:1512`). `scripts/soul_lint.py` gates length, filler, workflow, output
  default, refusal, truthful skill claims and cross-role copying; all ten clean, and
  `tests/test_souls.py` makes the gate binding (`docs/NOTES.md` #18-19).
- The receipt counts real skills: `_skills_on_disk` walks `SKILL.md` and skips dot entries and
  `.archive/`, so folders and lock files stopped inflating the number (`docs/NOTES.md` #17,
  `tests/test_receipt.py`).
- All-ten readable check, `bp-test-*` profiles, deleted after each: every role lands its full pick
  list, zero failures, zero `.archive/` leaks. Note: profiles are HOME-anchored, so `HERMES_HOME`
  does not isolate them (`docs/NOTES.md` #15).

## Adversarial pass, what it caught

- Undo reported success for a plugin that was not there. It now checks presence first and prints
  `already gone: plugin <name>`, shipped in 0.1.4.
- The pty harness behind the demo never sent Enter, so the card beat looked proven when it was not.
  Harness fixed, full loop re-run in one session: ask, card, yes, install, receipt, undo.
- Doc drift: this file still said v0.1.0 and 145 tests, `docs/DEMO.md` was a second older script
  disagreeing with the shotlist, and the README showed a note count with no explanation. All fixed.

## Recording script

- `docs/DEMO_SHOTLIST.md` is the one to record: 88 seconds, seven beats, real screen output.
- `docs/DEMO.md` is superseded and kept only for its offline fallback note.

## Left, user only

- Open the catalog PR from `dresraz` (entry and body are ready).
- Post the demo on X, under 90 seconds, tagging `@NousResearch`.
- Submit both links at the Typeform.

## Budget

- $0 of ~$10. No paid model calls were made; every test is deterministic.
