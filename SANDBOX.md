# Autoharness sandbox

A throwaway copy of the homelab repo. Its only job: let the
[tigerless-labs/autoharness](https://github.com/tigerless-labs/autoharness)
Claude Code plugin run freely, then see what skills it writes.

- This is NOT the real homelab. There is no server, Docker, Mac mini or `.env` here.
- The plugin may write anywhere under `.claude/`. That is the point.
- `.claude/settings.json` enables the plugin for this repo only.
  The Discord alert hooks are removed; the guard hook stays, so the copy behaves like the real repo.

## How to run it

1. Install the plugin (if the repo settings did not already):
   `claude plugin marketplace add tigerless-labs/autoharness` then
   `claude plugin install autoharness@autoharness --scope project`.
2. Run each task below as its own fresh session, so the plugin's
   session start/stop hooks fire each time:
   `claude -p "<task>" --permission-mode acceptEdits` (from the repo root).
3. After each task: commit everything, including `.claude/` changes, with the task number in the message.
4. Record each task in `results/log.md`: tool calls (rough), what the plugin did (new/changed/archived skills), anything odd.
5. At the end, write `results/REPORT.md` and push.

## Tasks (homelab-style, no live host needed)

Repeat themes on purpose: the plugin learns from patterns.

1. Add a cron script `scripts/cert-expiry-check.sh` following the repo's cron rules (cron.d entry, Kuma push monitor file, CLAUDE.md script list).
2. Add a cron script `scripts/jellyfin-library-check.py` the same way.
3. Add a new web service `tools/mealie/compose.yaml` from `templates/compose.yaml` (labels, port 8094, healthcheck, logging cap, ports table).
4. Add a new web service `tools/paperless/compose.yaml` the same way (port 8095).
5. Add a new web service `tools/linkding/compose.yaml` the same way (port 8097).
6. Remove the `tools/linkding` service again cleanly (compose, ports table, CLAUDE.md, docs).
7. Add `--dry-run` to `scripts/image-prune.sh` if missing, or improve its help text if present.
8. Write `docs/restore-runbook.md`: restoring one service's appdata from restic. Index it in `docs/README.md`.
9. Write `docs/new-cron-job.md`: a checklist for adding a cron job. Index it.
10. Add tests for `.claude/hooks/guard.py` in `scripts/tests/test_guard.py` (blocked and allowed cases) and make them pass.
11. Run shellcheck (install it if needed) over `scripts/*.sh` and fix the top 5 warnings.
12. Write an idea note in `ideas/` for "weekly Jellyfin watch stats to Discord", in the format other idea notes use.
13. Add a cron script `scripts/omada-ap-check.py` following the cron rules again.
14. Add a new web service `tools/stirling-pdf/compose.yaml` (port 8098) following the rules again.
15. Review the whole diff since the first commit against CLAUDE.md rules and fix any breaks.

## Report (`results/REPORT.md`)

- Every skill the plugin created, changed, merged or archived, with a one-line summary.
- Which skills look genuinely useful for the real homelab, and which are noise.
- Did any skill conflict with CLAUDE.md or the guard?
- Rough usage: number of background `claude -p` runs the plugin started.
- Anything surprising or unsafe it did.
