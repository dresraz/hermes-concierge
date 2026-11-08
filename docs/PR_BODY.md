## What this does

Concierge makes adding something to Hermes a one-sentence job.

You say what you want. Concierge matches it against both marketplace shelves: the plugin catalog
(1,064 entries today) and the skill registries. A plugin gets one card with the name, tier, what it
adds, what it costs on every request and the pinned commit, and installs only after you say yes.
Add `into <bot>` and the same sentence installs into that bot's profile instead of your own, skills
included. Then it reads the result back off the disk and prints a receipt. `/concierge undo` removes
exactly what it added, from the home it went into. When nothing fits, it installs nothing and says
so.

It also improves a bot. `/concierge improve researcher-bot: it needs to read scanned PDFs` installs
that skill from the marketplace into that bot. `/concierge improve my researcher: always show the
source first` writes the rule into the bot's `SOUL.md`, where every turn reads it. Improves work on
any profile on the machine, not only the ones Concierge made. Rules are deduped, capped and written
atomically, one backup per rule, so undo restores the exact bytes a rule replaced instead of
guessing.

A bare `/concierge` opens a shelf: the bots, the skills already on disk and the plugin catalog,
numbered, generated per request, expiring after ten minutes. A number acts on that row.

One deliberate omission: it does not recommend memory plugins. They hook the agent's own memory and
can need a hosted service or a paid plan, so they are left to a manual install.

It also creates bots: `/concierge create a researcher for papers` makes a `researcher-bot` profile
with a role, its catalog skills (eight for the researcher, the count varies by role), a `SOUL.md`
and a copy of your own plugin switches, so the bot starts from your setup instead of the bundled
defaults. The receipt counts what came along and what stayed behind, then tells you how to improve it
further.

## Surfaces used

- one slash command, `/concierge`, registered with `ctx.register_command`. No `SKILL.md`, so
  nothing is added to a profile's skill list or to the skill index
- one `pre_gateway_dispatch` hook: turns a short reply word in the messaging gateway into the same
  confirmation the CLI takes, and consumes it so the model never sees it
- no tools registered, so nothing is added to the model's tool list or to the request
- installs and removals call the same core paths the CLI uses (`install_catalog_entry`,
  `cmd_remove`, `do_install`, `create_job`), so Hermes's own scan, consent screen and commit pinning
  still apply. There is no separate installer and no self-updater.

## Disclosures (rule 13)

- **Network.** It fetches the plugin catalog index from GitHub, the skill registries behind a skill
  search, and one plugin manifest at its pinned commit for the dependency line on the card. Nothing
  else goes out.
- **Reads outside its own data.** It reads the active `HERMES_HOME`: the catalog, the profiles
  directory, and the plugin and skill directories. That is what lets the receipt be read back off
  the disk instead of being a claim.
- **Writes.** A new profile per bot created, skills into it, a `SOUL.md`, its `plugins:` switches copied
  from your own `config.yaml`, and Hermes's own install records.
  Listing, resetting and deleting profiles are limited to profiles Concierge created; the default
  profile can be reset to stock but never deleted.
- **Shell commands.** An install aimed at another bot runs `hermes -p <bot> …` as a short-lived child
  process: a profile's plugin and skill directories belong to that profile's home. Your yes is still
  the gate, and nothing runs in the background.
- **Credentials.** None. No API keys, no `.env`, no `auth.json`, no OAuth.
- **Telemetry.** None.
- **Long-running work.** None. No background processes, no watchers.
- **Load time.** Nothing runs at import. The hook registers and returns.

## Known warnings, disclosed rather than hidden

`hermes plugins validate` passes with one warning: 23 imports of core modules that have no
public seam (for example "install this catalog entry" and "create a profile"). They are the same
calls the CLI makes, nothing is rebound at runtime, and `no core override` passes. If Hermes adds
public seams for those operations, Concierge switches to them the same day. The warning is
also in the README under `## Limits`.

## Evidence

- `hermes plugins validate . --install-deps` at the pinned commit: passed, one warning
- 170 tests, no network, no model calls
- matcher measured against the live catalog: top pick 24/32, in the top three 31/32, eight of
  eight nonsense asks install nothing
