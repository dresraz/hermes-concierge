# STATUS

GATE: build complete
Date: 2026-11-05

## Done
- Plugin loads and validates (`hermes plugins validate /home/andres/concierge`: pass; one
  advisory about private core imports, explained in `docs/NOTES.md` #7).
- One command only: `/concierge`. `/hire` and `/train` are sentences inside it, not registry
  commands (verified by probing `get_plugin_commands()`: the registry key is `concierge` alone).
- `/concierge help` lists every verb, and the three words a card accepts (yes / no / more).
  Card + one yes install. Hire, train, bots, remove, reset, undo all run end to end in a
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
- No receipt offers an undo it did not record: card, hire and train all report a failed record
  write and drop the undo line instead of promising a reversal with nothing behind it (#13).
- Matcher, two independent measures against the live 977-entry catalog, zero network, zero LLM:
  hand-written asks (`tests/eval_match.py`) top1 25/32, top3 32/32, 7 of 8 nonsense return nothing;
  un-tunable recall (`tests/eval_recall.py`, 120 sampled entries asked their own titles) top1 119/120,
  top3 120/120.
- Known limit, measured not hidden: one junk sentence still surfaces a card. Three candidate fixes
  were tried and all measured worse on real asks (`docs/NOTES.md` #9). A card is not an install.
- Undo of a plugin runs core's real removal (`cmd_remove`), not a guessed name; `tests/test_undo_defaults.py`
  proves it in a throwaway home with nothing injected, through the real command too (`docs/NOTES.md` #11).
- Ten roles hire with 10-15 genuinely relevant skills each (11-15 picks, all ten roles): a mix of
  optional skills installed through core's own `hermes -p <profile> skills install` and bundled-tree
  skills copied in after the install pool. Every identifier exists in the Hermes tree and the bundled
  names are written on the receipt; a test fails on any invented name or a role outside 10-15.
  Verified role by role, all ten green: `installed == picks`, `failed == []`, nothing stranded in
  `.archive/` (`docs/NOTES.md` #14-16, `docs/PRESETS.md`).
- 134 unit tests, 0 LLM calls, 2 skipped (live-only). `python -m unittest discover -s tests`: OK.
- Live probe of the new card, throwaway `HERMES_HOME`, real 977-entry catalog: two-candidate ask,
  `more`, `2`, `no` (`/home/andres/.hermes/cache/scratch/live_card.txt`).
- All-ten readable check, `bp-test-*` profiles, deleted after each: every role lands its full pick
  list, zero failures, zero `.archive/` leaks. `planner` re-run under a throwaway `HERMES_HOME`
  after the CLI-home fix: 11/11. Note: profiles are HOME-anchored, so `HERMES_HOME` does not isolate
  them (`docs/NOTES.md` #15).
- Docs: `README.md` (pitch, card, receipts, lifecycle, roles), `SPEC.md`, `docs/PRESETS.md` (the ten
  roles and their skills), `docs/NOTES.md` (14 places the code disagrees with the brief or the docs).

## Failed / open
- The junk-sentence card cannot be removed without losing real asks; claim narrowed in `README.md`.
- Cosmetics left alone: `adds 1 tools` does not singularise, and a long `what` is cut mid-word.
- Nothing blocking. `hermes plugins validate` advisory on private core imports stays: there is no
  public `ctx.*` for ranking the live catalog, installing, creating a profile, or undoing.

## Packaged, nothing public
- Public repo `https://github.com/dresraz/hermes-concierge`, 6 commits all authored `dresraz`,
  tag `v0.1.0`, MIT licence, branch `main`.
- A fresh clone of that commit passes `hermes plugins validate` and 134 tests.
- Ready to send: `docs/catalog-entry.yaml` (repo + sha blank until the repo exists),
  `docs/PR.md`, `docs/SUBMIT.md`.

## Next (user calls, not done on purpose)
- Create the public repo, push, fill the two blank fields, open the catalog PR: all need a yes.

## Budget
- $0 of ~$10. No paid model calls were made; every test is deterministic.
