# Disk Space Alert

Value: 3
Effort: 1
Score: 15
Source: claude 2026-10-15

## Problem
Nothing warns when a disk fills up. Kuma and Scrutiny check health, not free space. Storage cleanup part B
(actually deleting watched media) is on hold until it's needed: `/mnt/media` is at 28% today, and the
report only deletes above 85%. Dan wants a heads-up at 70% so part B gets built in time.

## Proposal
`scripts/disk-space-check.sh`, cron daily via `scripts/install-cron.sh`, same shape as
`scripts/ha-backup-check.sh` (syslog tag, `test` argument, ntfy topic read from the env file, never printed).
- `/mnt/media` at 70% or more: ntfy, default priority. Message: "media disk at N%: time to build storage
  cleanup part B (docs/m2-media.md)".
- `/`, `/srv/homelab` (if it's a separate mount) and `/mnt/backup` at 85% or more: ntfy, high priority.
- Every disk at 95% or more: high priority.
- Repeats at most once a week per disk and level (small state file under `/srv/homelab/`), so it doesn't
  nag daily over a slow fill. Repeats daily at 95%.
- Read-only: `df` only. No container, no root.

## Checks
`bash -n`, `scripts/disk-space-check.sh test` sends one test, and a run with a lowered threshold in a temp
copy sends an alert. Add a line to `docs/m4-backups.md` (Stage D) and to CLAUDE.md's scripts list.

_Added by Claude in the terminal for Dan, 2026-10-15._

## Plan
Goal: a daily ntfy alert when a disk is filling up. Media at 70% means it's time to build storage cleanup part B.
Kind: script/cron
Files:
- scripts/disk-space-check.sh (new, executable): follow the shape of scripts/ha-backup-check.sh. That means `set -uo pipefail`,
  `log()` to syslog with tag `disk-space-check` (and echo when run on a tty), `notify <title> <msg> <priority>`
  reading NTFY_ALERT_TOPIC from "$REPO/.env" with the same sed and never printing it, and posting to
  http://localhost:8081/$topic with the header `Priority: default|high` and `Tags: floppy_disk,warning`.
  `test` sends one test notification and exits.
  - Disks are fixed mountpoints. `/mnt/media` warns at 70 (priority default) with this message:
    "media disk at N%: time to build storage cleanup part B (docs/m2-media.md, Watched-media cleanup report)".
    `/` and `/mnt/backup` warn at 85 (priority high). `/srv/homelab` is added at 85 only when
    `findmnt -n -o TARGET --target /srv/homelab` is not `/`. Today it is on `/`, so it isn't checked
    separately. Any of these at 95 or more is the `crit` level (priority high). At crit, send only the crit
    alert, not the warn one as well.
  - Use % from `df -P --output=pcent <mnt>` with the `%` stripped. Run `mountpoint -q` first for everything except `/`.
  - Thresholds and the state path can be overridden for testing through env vars: DISK_CHECK_MEDIA_PCT (70),
    DISK_CHECK_SYSTEM_PCT (85), DISK_CHECK_CRIT_PCT (95), DISK_CHECK_STATE
    (/srv/homelab/disk-space-check/state). These are shell env vars, not .env entries.
  - The state file has one line per alert, `<mount> <level> <epoch>`, level = warn|crit. Before an alert, check
    the last send: warn repeats only when it is at least 7 days minus 1 hour old. crit sends every day. Write the
    state only after a successful ntfy post. When a disk is below its threshold, drop its line, so the next
    crossing alerts at once. Use `mkdir -p` for the state dir and write via a temp file + `mv`.
  - Each run logs one line per disk ("ok /mnt/media 28%" or "alert …" / "suppressed …").
- scripts/install-cron.sh: add `10 9 * * * $REPO/scripts/disk-space-check.sh # homelab` after the scrutiny line.
- docs/m4-backups.md: add a `### Alerts: scripts/disk-space-check.sh` subsection to Stage D after the scrutiny one.
  It covers the thresholds, the repeat rule, where the state file lives, the test/run/journalctl commands, and that
  the check is df-only with no root and no container.
- CLAUDE.md: add a scripts-list entry after scrutiny-check.sh:
  `disk-space-check.sh` (cron: ntfy when a disk fills; media 70%, system/backup 85%, any 95%).
New service: None
New env vars: None (reuses NTFY_ALERT_TOPIC)
Checks the builder must run:
- `bash -n scripts/disk-space-check.sh scripts/install-cron.sh`
- `scripts/disk-space-check.sh`: real run. It should log ok for /, /mnt/media (28%) and /mnt/backup, and send nothing.
- `DISK_CHECK_STATE=<scratch>/state DISK_CHECK_MEDIA_PCT=1 scripts/disk-space-check.sh`: this sends one
  media alert and writes the state. Run it again with the same env: it should be suppressed, and nothing sent.
  Then run with DISK_CHECK_CRIT_PCT=1: it sends crit alerts and should send them again on a second run.
- Do not run `scripts/disk-space-check.sh test` or install-cron.sh from the worktree. Both are for Dan at deploy.
Review focus:
- /mnt/backup (USB) not mounted -> log "not mounted", skip it, and never report the root fs's % as backup.
  backup.sh already fails loudly on that.
- ntfy down or topic unset -> log it, don't write the state (so tomorrow retries), and exit 1.
- df output empty or not a number -> log it, skip that disk, exit 1 at the end, and don't alert on garbage.
- Missing or corrupt state file -> treat it as "never sent", with no crash. A disk going below its threshold clears its
  entry, so there is no stale suppression.
- Slow media fill above 70% -> one ntfy a week, not daily. Daily only at 95%.
Docs: CLAUDE.md scripts list; docs/m4-backups.md Stage D subsection. No port table change.

## Manual steps
- `scripts/install-cron.sh` (adds the 09:10 entry).
- `scripts/disk-space-check.sh test` to confirm the phone gets it.

## Review notes
1. /home/dan/homelab/.worktrees/disk-space-alert/scripts/disk-space-check.sh: it calls `df --output=pcent` without the `-P` the plan asked for. This is correct. GNU df won't accept `-P` together with `--output`, and `--output` never wraps lines anyway.
2. When `/mnt/media` reaches 95%, the crit message doesn't mention building storage cleanup part B. The warn message (70%) does. You could add the same hint to the media crit text.
3. If `/mnt/backup` isn't mounted, the script logs and skips it but still exits 0. That matches the plan, which relies on backup.sh failing loudly, but nothing in this check reports the missing disk.
4. After a failed ntfy post, two lines are logged ("ntfy post failed" and "... NOT sent"). This is harmless. The topic never shows up in the logs.
5. The changes are staged in the worktree but not committed yet. `git log main..idea/disk-space-alert` is empty. `idea.sh diff` shows all the changes.

## Declined to judge
- State path is a directory or not writable: an unlikely edge case that the plan doesn't cover. /srv/homelab is owned by dan, so it will work.
- No alert when an unmounted disk stays unmounted: outside this check's scope, per the plan.
