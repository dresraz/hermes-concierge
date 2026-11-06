# Add Concierge to the catalog

One sentence in, one bot or skill installed, with a receipt and an undo.

Concierge is a plugin that makes adding anything to Hermes a single exchange:
say what you want, get one card, answer yes. It matches the ask against the
live 977-entry catalog, installs through Hermes's own installer and scan gate,
reads the result back off the disk and prints what actually landed. `/concierge
undo` removes exactly what it added. When nothing fits it says so and installs
nothing.

It also owns the bots it creates: hire, train, list, fire and reset, all behind
the same `/concierge` command. `fire` is the opposite of `hire`; a bot that has
been used makes you type its name back, and `undo` never deletes a used bot.

- Pin: `<sha>`
- `hermes plugins validate` at the pin: pass (one advisory on private core
  imports, explained below)
- Tests: 120 unit tests, zero LLM calls, zero network, run in a throwaway
  `HERMES_HOME`
- Matching, two independent measures against the live catalog: 25/32 top-1 and
  32/32 top-3 on hand-written asks; 119/120 top-1 on un-tunable recall
- Default profile: `fire default` is refused; `reset default` only replays
  records Concierge wrote
- No self-updater, no telemetry, no credentials

The private-import advisory: ranking the live catalog, creating a profile,
installing and removing are not on the public `ctx.*` surface, so Concierge
calls the same functions the CLI calls rather than rebinding anything. It does
not patch, wrap or replace core code (rule 9). If you would rather have a
public seam for "install this catalog entry and tell me what landed", that is
the hook this plugin wants and it would happily switch to it.
