# Hackathon submission: Concierge

Deadline: 5PM EST, Nov 11. Three steps, in this order.

## 1. Catalog PR (about 10 minutes)

Fork `NousResearch/hermes-agent`, then on a branch add one file: `plugin-catalog/concierge.yaml`.
The exact content is in `docs/catalog-entry.yaml` in this repo. It pins a real release:

- repo: https://github.com/dresraz/hermes-concierge
- sha: 2afc787df0077707243cc6f06c9d17d3d1c419d9 (tag `v0.1.3`)
- version: 0.1.3
- `hermes plugins validate . --install-deps` at that commit: **passed**, one warning (private core
  imports, disclosed in the README `## Limits` and in the PR body)

PR title: `plugin-catalog: add concierge`

PR body: paste `docs/PR_BODY.md`.

The entry must be submitted by the repo owner, which is you, so the PR has to come from your
account. Nothing about the PR needs the plugin repo to change.

## 2. Demo video on X, 90 seconds or less

Follow `docs/DEMO_SHOTLIST.md`. Post it on X with @NousResearch tagged in the text. Keep the post
public and copy the link.

## 3. The form

http://form.typeform.com/to/FwJLvOln

Fields it asks for: name, email, the PR link, the X post link, and a short description. Use the
first paragraph of `docs/PR_BODY.md` as the description.

You can submit the form as soon as the PR is open. The catalog checks start when a maintainer
triggers them.

## What is already done

- plugin code, tests, docs, release `v0.1.3` pushed
- catalog entry written and parsed by the real loader (`hermes_cli.plugin_catalog.entry_from_mapping`)
- validation passed at the pinned commit
- PR body text written
- demo shotlist written

## What only you can do

- open the PR (your GitHub account)
- record and post the video (your X account)
- submit the form (your email)
