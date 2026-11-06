# Where the docs and the brief disagree with the code

Every line below was checked against a running Hermes on this box, not read off a page.
If you are building the same plugin, these are the traps.

## 1. `HERMES_HOME` does not sandbox profiles

The brief says test in a throwaway home. That works for config, plugins and session state,
but **not** for profiles. `hermes_cli.profiles._get_profiles_root()` is anchored to the real
`~/.hermes`, so a plugin that calls `create_profile` writes into the user's real profile
directory even when `HERMES_HOME=$(mktemp -d)/hh` is set.

Worse: a running gateway lists every profile under that root in `gateway_state.json`
(`served_profiles`) and reconciles it. Delete the directory with `rm -rf` and it comes back
within a minute, because the gateway still believes the profile exists.

Verified sequence:

```
HERMES_HOME=$HH ... hire "inbox-bot"     ->  real /home/andres/.hermes/profiles/inbox-bot
rm -rf that directory                     ->  recreated ~60s later by the gateway
hermes profile delete inbox-bot           ->  gone, stays gone, gateway reconciled
```

Consequences we adopted:

- The unit suite injects seams and never calls core. No LLM calls, no profiles.
- The one live end-to-end run used a `bp-test-*` name and was removed with
  `hermes profile delete`, never `rm`.
- `remove` in the plugin goes through core's `delete_profile` for exactly this reason.

## 2. `capabilities` in `plugin.yaml` must be a list, not a mapping

The obvious manifest shape is wrong:

```yaml
capabilities:
  commands: [concierge]
```

`hermes plugins validate` rejects it: `manifest 'capabilities' must be a list`. Commands are
not declared in the manifest at all. They are registered at runtime by `register(ctx)` and
discovered through `hermes_cli.plugins.get_plugin_commands()`. The manifest keeps
`name`, `version`, `description`, `author`, and the hooks it provides.

## 3. A plugin command handler gets exactly one argument

Dispatch calls `handler(raw_text)`. A handler declared as
`def handle_concierge(raw, *, store, seams)` raises `TypeError` the first time a real user
types the command, while every unit test still passes. `handle_concierge` now builds its own
`state.Store()` when none is injected.

## 4. Explicit bot names use the colon form

The mechanical rule takes the last meaningful word (`keeps my inbox at zero` -> `inbox-bot`).
`hire bp-test-zero keeps my inbox at zero` therefore creates `inbox-bot`. To name it, use
`hire bp-test-zero: keeps my inbox at zero`. Leading words before a colon are the name.

## 5. Deleting a served profile stops its gateway

`hermes profile delete <name>` prints `Gateway is running — it will be stopped` and takes the
per-profile gateway down with the directory. That is the behaviour we want from `remove`, so
we call core rather than unlinking files.

## 6. A pre-hire profile list cannot be used as a receipt

The first end-to-end run reported `profile NOT listed` for a bot that plainly existed, because
the receipt was handed the profile list captured *before* `create_profile` ran. The receipt now
re-reads the root after the write when it is not given an injected list. A receipt that can lie
is worse than no receipt.

## 7. `hermes plugins validate` warns about private core imports

Validation passes, and then prints:

```
⚠ private core imports (catalog rule 9: public surfaces only; these can break on
any release): seams.py:38 hermes_cli.plugin_catalog.load_catalog_live; ...
```

There is no `ctx.*` for "rank the live catalog", "run the installer", "create a profile" or
"undo". A plugin that keeps all of those calls in one module (`seams.py`) is the honest shape:
one file to fix when core moves, instead of a copy of the installer that drifts.

## 8. `reset` must not replay the profile-creation record

The first live `reset` deleted the whole bot, because the record from `hire` is "delete this
profile" when replayed. That contradicts the contract ("reset leaves the bot standing").
`reset` now always keeps the bot record and replays only the records written inside it;
`remove` is the only path that deletes a profile. Regression test:
`test_reset_leaves_the_bot_standing`.


## 9. One junk sentence still surfaces a card, and three fixes measured worse

`"convert my sandwich into a spreadsheet tax form for fish"` still ranks `fish-audio`
(`form` 0.54 from its own "advisory form" boilerplate + `fish` 0.84 as a name/tool word).
We tried to remove it three ways and measured each against the 32 realistic asks:

- **Weighted query coverage** (matched word weight / all content word weight): real asks go as
  low as 0.16, the junk ask sits at 0.36. Overlaps, no threshold works.
- **Require a capability-text hit, not a name hit**: the junk ask passes (its `fish` word is in
  the entry's tool text) and 8 of 32 real asks would be dropped.
- **Require an adjacent matched pair**: the junk ask passes, and 7 real asks would still need
  the old path.

Conclusion: this is the boundary of a keyword matcher, not a tuning bug. Behaviour kept,
claim narrowed in `README.md` (a card is not an install; nothing installs without the yes),
and `tests/eval_match.py` keeps the case as a known leak instead of hiding it.

## 10. The hand-written eval can be nudged, so there is a second one

`tests/eval_match.py` uses 32 hand-written asks; whoever edits the expected lists can move the
number. `tests/eval_recall.py` cannot be nudged: fixed seed, samples 120 of the 977 catalog
entries, asks each entry's own lower-cased title, and checks the entry comes back top-3.
Currently `top1=119/120 top3=120/120`. It is an easy task by construction (the title is the
entry's own words) so it is a floor, not a ceiling.

## 11. Undo of a plugin looked for a function that does not exist

`undo.py` guessed core's uninstall name (`uninstall_plugin`, `remove_plugin`, ...) across three
modules. None of them has one: core removes a plugin through `hermes_cli.plugins_cmd_remove.cmd_remove`.
So on a real install `_default_uninstall()` raised `AttributeError`, `_run()` turned it into a
"could not restore" line, and the record stayed. Every undo test injected its own callable, which
is exactly why 101 green tests missed it.

Fixed by pointing the three defaults at the real thing and nothing else:

- plugin -> `seams.remove_plugin()`, which wraps `cmd_remove`; a core refusal is a `SystemExit`
  there, so the seam turns it into a `RuntimeError` (undo must not take the session down).
- skill -> `tools.skills_hub_install.uninstall_skill`, which also refuses skills Concierge did not
  install, so a stray folder cannot be deleted by undo.
- cron -> unchanged; it already resolved to `cron.remove_job`.

`tests/test_undo_defaults.py` injects nothing: it builds a throwaway `HERMES_HOME`, puts a plugin
and a hub-installed skill in it, and checks the paths afterwards. It also runs the production chain
`handle_concierge("undo")` with defaults, and asserts the record is gone only when the file is.
The suite went 101 -> 106.

## 12. Dependencies ride the one yes

The catalog publishes no dependency list: `plugin-catalog/*.json` has no `dependencies`,
`requires` or `python_deps`, so `seams.declared_deps(entry)` is empty for all 977 entries and has
no catalog-side callers. Declarations live in the downloaded tree, which `pm/plugin_declarations.py`
reads as `read_python_declaration(...).install_requirements`.

Install path: a slash command has no tty for core's dependency question, so Concierge passes
`assume_deps_consent=True` (`seams.py:77`, `:90`) and core installs the plugin's own packages
itself. There is no extra question, and no prompt to answer.

The only thing that was missing was honesty in both directions:

- before the yes, `seams.declared_deps_remote(entry)` reads the plugin's own `plugin.yaml`,
  `pyproject.toml` or `requirements.txt` from its pinned public commit. One small HTTPS read, no
  clone, nothing executed. The card prints `deps  httpx, websockets  installed with it, no extra
  question`, and only when the repo actually declares something. If a spec points at git or a URL
  the line says `installs code from git or a url, not PyPI`, because that is the one shape the
  catalog scan cannot see.
- after the yes, the receipt re-reads the installed tree (`seams.declared_deps(target)`) and prints
  `deps  httpx, websockets installed`: what core installed, not what the repo promised.

Measured, one shuffled sample of 40 real catalog entries at their pins (`tests/probe_deps_live.py`):
**9 of 40 (22%) declare packages**, the other 31 declare nothing and show no line. One of the nine,
`weather`, pulls three packages straight from git (`cfrust @ git+https://...`), which is exactly the
case the plain-words line exists for. Cost: ~0.45s per card, worst case three reads, and it is
skipped entirely for unpinned entries.

No new command, verb, config or step: the dependency surface got a line on the card and a line on
the receipt, nothing else. `tests/test_deps.py` covers all of it with an injected fetch, so the
suite stays offline and deterministic (106 -> 115 tests).

## 13. One card, one install, one receipt that is true

Three small defects, one family: the card promised things the code did not do.

1. **The second number.** The card said `Two candidates. Reply 1 or 2.` and described only the
   first. Typing `2` installed a plugin whose tools, hooks and cost the card never showed. A number
   that installs an undescribed thing is a decision made blind, so the number is gone: the runner-up
   is named on the `also` line, `more` describes it, and `/concierge <its name>` installs it. `2`
   now answers "one install at a time". `yes` always means the top match.
2. **`more` did nothing.** It was a recognised reply that fell through to "Nothing is waiting". It
   now prints the runner-up's `why / what / adds / cost` and says out loud that the card still holds
   the top match, so it cannot change what `yes` installs.
3. **Receipts promised undone work.** A failed record write was swallowed and the receipt still said
   `Undo it with /concierge undo`, which would have found nothing. `_remember` returns a bool now;
   on False the receipt prints `no undo  the record could not be saved`. Same check on hire and
   train, not just the card.

No new command, verb or config. `more` was already a dead branch, so this deletes a promise and adds
no surface. Live probe in a throwaway `HERMES_HOME` against the real catalog:
`/home/andres/.hermes/cache/scratch/live_card.txt` (card, `more`, `2`, `no`). Suite 115 -> 120, zero
LLM calls.

## 14. Roles install real skills, and the disk is the only receipt

What the brief implied: a preset is a list of skill names. What the CLI actually
does, measured on this machine:

1. **`hermes skills install` has no `--profile` flag.** Scope comes from the
   global `-p`: `hermes -p <profile> skills install official/<category>/<name> --yes`.
   The identifier is the three-part `official/...` form, not the bare name and
   not `optional-skills/...`.
2. **The exit code is not the truth.** `--yes` returns 0 for the install, and the
   first version of `verify()` still reported 0/3 because it looked for
   `skills/<name>/SKILL.md`. Skills land at `skills/<category>/<name>/SKILL.md`,
   so the check now globs both shapes. The spike caught it: 3 `SKILL.md` on disk
   while the report said all three failed.
3. **A fresh profile starts with no skills directory.** The 44 bundled skills are
   seeded on the profile's first real run, not at `create_profile`. So a preset
   only lists optional skills, and a receipt that says `skills 0 installed`
   before the preset line is correct, not a bug.
4. **Cost of an install is per skill, not per profile.** 0.6s to create a profile,
   1.2s for three skills installed three-at-a-time, 16s for the designer role's
   four (`comfyui` dominates). Fine inside one command; the reason installs run
   in a thread pool rather than a loop.
5. **A skill that fails to install must not lose the bot.** The profile is already
   created and recorded by then. The receipt names the failures, `undo` still
   removes the whole profile, and no exception escapes.

Spike, three roles, throwaway `bp-test-*` profiles, all deleted afterwards:

```
researcher  install 1.21s  3/3  parallel-cli, scrapling, rss-feeds
writer      install 2.40s  4/4  research-paper-writing, creative-ideation, simple-english, baoyu-article-illustrator
watcher     install 1.20s  3/3  watchers, blogwatcher, live-dashboard
designer    install 16.32s 4/4  sketch, impeccable, design-md, comfyui
tutor       install 2.26s  4/4  memento-flashcards, concept-diagrams, baoyu-comic, qmd
```

Every identifier was checked against the Hermes tree twice: a one-off scan while
choosing them, and `tests/test_presets.py::Contract` on every run, which fails if
a name is not a real `optional-skills/<category>/<name>/SKILL.md`. Suite 120 -> 134,
zero LLM calls, no new command.

## 15. Profiles are HOME-anchored; the CLI has to be told the same root

`hermes_cli.profiles.create_profile()` writes to `~/.hermes/profiles/<name>` no matter what
`HERMES_HOME` says: the profiles root is deliberately HOME-anchored so profiles survive a moved
data dir. But `hermes -p <name> skills install` honours `HERMES_HOME`, so the two disagreed the
moment Concierge ran under a custom home: the profile was created for real, and every optional
install went looking in the throwaway tree and found no profile (`installed 0 of 11`).

Fix: `install()` passes `HERMES_HOME=<root of the profile>` to the CLI, derived from the profile
path it just got, instead of inheriting whatever the session had. One role re-run under a
throwaway `HERMES_HOME` now lands 11 of 11.

Consequence for testing, recorded because the brief asks for a throwaway home: `HERMES_HOME`
isolates Hermes' data, not its profiles. Test profiles are real profiles under
`~/.hermes/profiles/`, named `bp-test-*` and deleted in the same run. Nothing else is touched.

## 16. Two receipt lies fixed: `.archive/` counts, and the installer eats copies

1. `verify()` counted a skill as present if `skills/*/<name>` existed, and `.archive/<name>` matches
   that glob: a retired copy read as installed. `_present` now skips any folder whose parent starts
   with `.`.
2. Copying a bundled skill before `hermes skills install` runs is pointless: the installer archives
   any same-name skill it finds, so the receipt named a skill that had just been retired. Bundled
   copies now happen after the install pool, and `copy_bundled` never selects a path under
   `.archive/` and prefers the shallowest match when a name exists in two categories.

## 17. A third receipt lie: the skills line counted folders and lock files

`bots.receipt` reported `len(skills_dir.iterdir())`. That counts category folders
(`research/`, `creative/`) and dot bookkeeping (`.hub`, `.usage.json`,
`.usage.json.lock`), so a profile with seven real skills printed "8 installed" by
coincidence and would drift with every core change to that folder. `_skills_on_disk`
now walks `SKILL.md` markers and skips any relative part beginning with `.`, so a
retired copy under `.archive/` and a category folder cannot be counted. Proven in
`tests/test_receipt.py`; the live check is `skills == picks + 1` (the seeded
`hermes-agent` skill).

## 18. The soul path is core's own

`write_soul` writes `<profile home>/SOUL.md`. That is exactly what core reads:
`agent/prompt_builder.load_soul_md` resolves `HERMES_HOME / "SOUL.md"` as identity
slot #1 (`agent/prompt_builder.py:1512`). Profiles are HOME-anchored, which is why
`install()` passes the real root; writing anywhere else would leave the bot with
the generic soul the hire flow wrote a second earlier.

## 19. Souls are gated, not written once

`scripts/soul_lint.py` checks length (420-1200), filler phrases, that the text
names a workflow and an output default and a refusal, that it only claims skills
the role actually lands, and that no paragraph repeats across roles. All ten pass
at 969-1109 characters. `tests/test_souls.py` makes the gate binding and proves
the hired profile ends up with the role soul rather than the generic one.

## 20. Deleting a profile with `rm -rf` while the gateway runs does not delete it

This host runs a multiplex gateway, and it reconciles `~/.hermes/profiles/` on a timer and on
config changes. A directory removed behind its back comes back as an empty scaffold within a
minute, with a fresh `state.db`, and `served_profiles` in `gateway_state.json` still lists it.
`hermes profile delete <name> --yes` is the only removal that sticks: it asks the gateway to
unserve the profile (`gateway.control_socket.request_unserve_profile`), so the next reconcile
does not recreate it. Prove it: delete, wait 45s, list.

## 21. A profile is born with no `plugins:` block, so the bot gets the app's defaults

`create_profile` writes memory, skills and cron, and leaves config alone. Core then resolves every
bundled plugin's switch from its own default, which is the author's pick and not yours. A hired bot
therefore came up with switches nobody chose, and the receipt could not tell you which.

`plugins_inherit.py` copies the owner's `enabled` and `disabled` lists into the new profile's
`config.yaml` and drops the names that resolve inside the owner's home (`plugins/`,
`plugins/<kind>/`), because a profile is a different home and those folders are not inside it. The
receipt says `your setup, N switches, M not available here`; with no switches of your own it says
`stock defaults` and writes nothing. A copy error degrades to the same line and never fails a hire.

Prove it: hire into a throwaway home with `enabled: [web/fastcrw]` and a local plugin folder, and
read the new `config.yaml` plus the receipt line. `tests/test_plugins_inherit.py` holds the contract,
including that a name listed in both lists appears once in the "left behind" list.

## 22. Installing into a bot is a child process, and nothing else would work

`hermes` resolves a profile from its own home, and `HERMES_HOME` does not relocate the profiles
root: pointing it at a temp directory leaves `create_profile` writing into the real
`~/.hermes/profiles/` (proved with `mktemp -d`, which created a real `bp-test-intern`). So a
bot-targeted install shells out to `hermes -p <profile> ...` as a child process and reads the disk
afterwards, instead of swapping an environment variable inside the running agent.

The destination rides on the sentence: `split_target` takes the last ` into `, requires one word and
an existing profile, and keeps the user's casing for the catalog query. A typo yields no target, so
the card says `this profile` rather than installing somewhere else quietly. Undo reads `profile` off
the receipt and routes there before it looks at the kind, because a skill installed into `intern`
has to leave `intern`'s home and `undo.py` only ever looks at this profile.

Prove it: `accent picker into <bot>` then `yes` lands 9 files under that bot's `plugins/` and undo
empties it; `a skill for writing commit messages into <bot>` lands 3 files under its `skills/`;
`tests/test_market.py` holds the card split, both undo routes and the no-`plugin` line on a skill
receipt.
