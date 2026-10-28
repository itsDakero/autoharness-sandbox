# Install cron entries automatically when a deploy changes install-cron.sh

Value: 4   (Dan: four merged features (disk alert, arr re-search, cleanup report, image digest) actually start running)
Effort: 1  (one change to deploy-idea.sh plus a small drift check)
Risk: 1    (Dan's user crontab only; no root, no containers)
Score: 20
Source: scout 2026-10-16

## Problem
`scripts/install-cron.sh` lists 9 entries, but Dan's crontab has only the original 5 (qbit-watchdog,
idea-actions, seerr-route, ha-backup-check, scrutiny-check). Missing: disk-space-check (daily 09:10, merged
Oct 15), arr-missing-search (Sun 02:30, merged Oct 14), storage-cleanup report (Sun 10:00) and image-check
(Mon 09:10, merged Oct 16). Each idea left "run install-cron.sh after deploy" as a manual step, and it never
happened. The only disk-space-check journal entry is a build-time test on Oct 15 22:28. Nothing reports the
drift. Side effect today: traefik v3.7.15 has been on Docker Hub since Oct 16 05:10 (we run v3.7.14), and the
image digest that would say so isn't scheduled.

## Proposal
- `scripts/deploy-idea.sh`: when the merged diff touches `scripts/install-cron.sh`, run it as dan (it only
  edits the user crontab, no sudo) and print the resulting entries.
- Drift check: compare `crontab -l` with the script's ENTRIES. Report a mismatch either as a line in the
  dashboard status or in a daily ntfy/Discord message from an existing cron script (e.g. disk-space-check).
- Dan runs `scripts/install-cron.sh` once by hand now.
No new service, no port, no media access.

## Existing tools checked
- scripts/install-cron.sh: changed Oct 14, 15 and 16 (git log); already idempotent, so safe to rerun on deploy.
- scripts/deploy-idea.sh: prunes images after a deploy and never touches cron.
- ideas/done/{arr-missing-search,storage-cleanup,disk-space-alert,image-freshness-digest}.md: all list the
  same manual cron step.

## Rough plan
1. Add the "diff touches install-cron.sh -> run it, print entries" step to deploy-idea.sh.
2. Add a `--check` mode to install-cron.sh (exit non-zero and list missing/extra entries) and call it from
   one existing daily cron script or the dashboard status.
3. Update docs/m5-pipeline.md (deploy steps) and drop the manual cron line from the idea template, if any.

_Approved on the dashboard, 2026-10-16._

## Plan
Goal: Every deploy brings Dan's crontab back in line with `scripts/install-cron.sh`, and a daily check posts to Discord whenever the two differ.
Kind: change to scripts/install-cron.sh and scripts/deploy-idea.sh (script/cron)
Files:
- scripts/install-cron.sh: add a `--check` mode.
  - Compare the tagged lines in the current crontab (`crontab -l | grep '# homelab$'`) with ENTRIES as exact lines.
    No crontab at all counts as every entry missing.
  - Print `missing: <line>` and `extra: <line>` for each difference. Exit 0 with `cron: in sync` when they match,
    or exit 1 when they don't.
  - `--check --notify` also sends one Discord post when they differ: `scripts/discord.sh "Cron drift: N missing, M
    extra; run scripts/install-cron.sh"`, with the missing script names shortened to basenames. It also logs via
    `logger -t install-cron`.
  - Test override (shell env only): `CRON_LIST=<file>` makes `--check` read the current entries from that file
    instead of `crontab -l`.
  - Add a 10th ENTRIES line: `15 9 * * * $REPO/scripts/install-cron.sh --check --notify # homelab`.
  - The plain install (no args) works as before. Any other argument prints usage and exits 2.
  - Update the header comment.
- scripts/deploy-idea.sh: after the `bootstrap.sh/systemd` warning line and before the service checks, add:
  ```
  echo "== cron"
  if ! "$REPO/scripts/install-cron.sh" --check; then
    "$REPO/scripts/install-cron.sh" || echo "deploy-idea: install-cron failed (deploy is fine)" >&2
  fi
  ```
  - This runs on every deploy, not only when install-cron.sh changed, so it also repairs drift that came from
    somewhere else.
  - It never fails the deploy under `set -e`.
  - It needs no sudo: it only touches dan's user crontab.
- docs/m5-pipeline.md, Stage C deploy bullet: add "deploy-idea.sh reinstalls the cron entries when they differ
  from install-cron.sh". In the Stage D Commands block, add `scripts/install-cron.sh --check   # crontab vs
  the repo (daily 09:15, Discord on drift)`.
- CLAUDE.md, scripts list: change `qbit-watchdog.sh` (cron, via `install-cron.sh`) to also say
  "`install-cron.sh` (`--check`: daily Discord on drift; deploy-idea.sh reinstalls on drift)".
- Not touched: anything under `.claude/`. There is no manual-cron line in the kit or templates (I grepped), so
  this needs no protected-path writes.
New service: none
New env vars: None (it reuses DISCORD_WEBHOOK_URL through discord.sh)
Checks the builder must run:
- `bash -n scripts/install-cron.sh scripts/deploy-idea.sh`
- `shellcheck` on both, if installed.
- Build a temp file with the 10 expected lines, using the worktree path as REPO, then:
  - `CRON_LIST=<that file> scripts/install-cron.sh --check` -> exit 0, `cron: in sync`.
  - Same with one line removed and one foreign `# homelab` line added -> exit 1, one `missing:` and one `extra:`.
  - `CRON_LIST=/nonexistent ...` -> exit 1, all 10 missing, no crash.
- `scripts/install-cron.sh --bogus` -> exit 2.
- NEVER run `scripts/install-cron.sh` without `--check`, and never run `--check` without CRON_LIST, from the
  worktree. Without `--check`, REPO would be `.worktrees/...` and Dan's crontab would be rewritten with
  worktree paths. Don't run `--notify` either (it posts to Discord).
Review focus:
- Plain install run from a worktree -> it writes worktree paths. Accepted, since only deploy (main repo) and Dan
  run it. The builder's tests must not run it; the reviewer checks the build log or commands.
- No crontab, or `crontab -l` fails -> `--check` reports everything missing and exits 1. No `set -e`/pipefail
  abort before the report (the grep with no matches must not kill the script).
- Discord down or webhook unset -> `--check --notify` still prints, logs and exits 1. discord.sh failure is
  ignored, with no retry loop.
- Deploy via the dashboard (`--yes`, run from cron by idea-actions.py) -> the cron step runs non-interactively,
  and a failure only prints a warning. The merge, push and Discord "Deployed" still happen.
- Drift that lasts days -> one Discord post per day (cron 09:15), never more often. A matching crontab posts
  nothing.
Docs: docs/m5-pipeline.md (deploy bullet plus a Commands line); CLAUDE.md scripts-list entry for install-cron.sh.

## Manual steps
- After deploying, check `crontab -l | grep homelab`. It should show 10 lines.
  - Today's crontab has 5 of the 9 current entries, and deploying this build installs all 10 through the new
    deploy step, so the separate hand run the note asks for isn't needed.
  - If the deploy printed "install-cron failed", run `scripts/install-cron.sh` once by hand.
- Optional: `CRON_LIST=/dev/null scripts/install-cron.sh --check --notify` to see a test drift post in Discord.

## Review notes
1. shellcheck isn't installed, so only `bash -n` was run. It passed on both scripts.
2. The builder hasn't committed on `idea/install-cron-on-deploy` yet (`git log main..idea/...` is empty), so I reviewed the working-tree diff from `scripts/idea.sh diff`. There's no build log to check commands against. Instead I read Dan's crontab (read-only): it has 5 `# homelab` lines and no `.worktrees` paths, so no plain install was run from the worktree.
3. The drift message adds a `(missing: <basenames>)` suffix to the planned wording, which is what the plan asked for. If an unknown argument reached `--check` in deploy-idea.sh, the exit-2 usage path would trigger a reinstall. That can't happen with the fixed call there.
4. The plain install also removes extra `# homelab` lines, so the deploy step repairs both missing and extra entries. That fits the goal.

## Declined to judge
- `idea-actions.py` running deploy-idea.sh from cron with cron's PATH: `crontab` and `logger` are in /usr/bin, so I see no issue, but I didn't run it end to end.
