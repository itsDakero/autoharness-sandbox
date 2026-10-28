---
name: rules-audit
description: Use when reviewing a diff against the CLAUDE.md rules.
category: review
---

# Audit a change set against the homelab rules

List the range first (`git diff BASE --stat`), then read each changed file with `git diff BASE -- PATH`. Check every changed file against the rules below. Fix plain breaks with an edit, and report the ones you could not fix.

- File modes: `git ls-files -s PATH` shows `100755` for every script under `scripts/`, cron scripts included.
- Images are pinned to an exact version. No `:latest`, no untagged image.
- `docker.sock` is mounted only through the docker socket proxy. `sudo` appears only in `bootstrap.sh`. `/mnt/media` is mounted `:ro`.
- `.env` is never committed. New keys go in `.env.example`, in their service's section.
- Each web service has one `homelab.port` that is free in the CLAUDE.md Ports table, plus the template labels, log cap and healthcheck.
- A new core service is added to the core up/down/stop/restart ask rules in `.claude/settings.json`.
- New docs are indexed in `docs/README.md`. New scripts appear in the CLAUDE.md scripts list, in alphabetical order.
- A removed service leaves no leftovers. Search for its name and port with the Grep tool, or with `grep` using `--exclude='*.env'`.

Report which checks you ran. A check you could not run (refused command, missing tool) is reported as not run, never as passed. For cron scripts, follow the `cron-job-setup` skill.
