# Publishing Concierge

Nothing here has been done. All of it is public and needs a yes first.

1. Create the repo `hermes-concierge` and push this directory.
2. Tag `v0.1.0`, then `git rev-parse HEAD` and paste the 40-char hash into
   `docs/catalog-entry.yaml` (`sha:`) and the repo URL into `repo:` / `docs_url:`.
3. `hermes plugins validate .` must pass at that exact commit.
4. Copy `docs/catalog-entry.yaml` to `plugin-catalog/concierge.yaml` in a fork
   of `NousResearch/hermes-agent`, then open the PR with `docs/PR.md`.
5. Bump `version:` in `plugin.yaml` and the entry together for every later SHA bump.

One known friction: the entry will show a validate warning about importing
private core modules (`hermes_state`, `pm.plugin_declarations`,
`tools.skills_hub_install`). It is a warning, not a failure, and it is honest:
there is no public `ctx.*` for ranking the live catalog, creating a profile,
installing a plugin or undoing one. `docs/NOTES.md` #7 has the detail.
