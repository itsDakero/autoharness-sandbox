# Pause jelu and wardrobe during the nightly backup

Value: 3   (Jelu reading history and the wardrobe catalogue become reliably restorable)
Effort: 1  (two names in one array, then a test restore)
Risk: 2    (touches the nightly backup)
Source: Dan 2026-10-23

## Problem
`scripts/backup.sh` pauses the containers with SQLite state (`PAUSE=(...)`, fitness and hermes added by
backup-pause-fitness-and-claude). jelu (`/srv/homelab/jelu/database/jelu.db`, WAL mode) and wardrobe
(`/srv/homelab/wardrobe`, SQLite in `tools/wardrobe/app/db.py`) were deployed the same day, after that
build, so they are not paused. restic can copy a db and its WAL at different moments.

## Proposal
- Add `jelu` and `wardrobe` to `PAUSE` in `scripts/backup.sh` (check the container names with `dc.sh ps`).
- Update the comment at the top of backup.sh and the paused list in `docs/m4-backups.md`.
- Manual steps for Dan: after the next nightly run, `journalctl -u homelab-backup -n 20` shows both in
  "paused:", and both containers are Up afterwards.

## Plan
Goal: Add jelu and wardrobe to the containers that backup.sh pauses during `restic backup`, so their SQLite DB and WAL are copied at the same moment.
Kind: change to scripts/backup.sh (nightly backup)
Files:
- scripts/backup.sh: line 31, add `jelu wardrobe` to the end of `PAUSE=(...)`, giving `PAUSE=(radarr radarr-remote sonarr sonarr-remote prowlarr jellyfin seerr uptime-kuma autokuma ntfy fitness hermes jelu wardrobe)`. In the header comment (lines 6-7), change "(incl. fitness and hermes)" to "(incl. fitness, hermes, jelu and wardrobe)". Change nothing else.
- docs/m4-backups.md: in the **Consistency** bullet (line 17-18), change "... ntfy, fitness and hermes" to "... ntfy, fitness, hermes, jelu and wardrobe".
New service: None. The container names are confirmed in the compose files: `container_name: jelu` (tools/jelu/compose.yaml) and `container_name: wardrobe` (tools/wardrobe/compose.yaml). Neither compose file has a sidecar container.
New env vars: None
Checks the builder must run:
- bash -n scripts/backup.sh
- grep -n '^PAUSE=' scripts/backup.sh  (one line, both names, nothing else changed)
- git diff --stat  (only the two files above)
- Do not run backup.sh. It needs root and pauses live containers.
Review focus:
- jelu or wardrobe stopped or missing at 04:00 -> the existing running check skips it, it is left out of "paused:", and the backup still succeeds (no new code needed; just confirm the names go only into PAUSE).
- restic fails while they are paused -> the existing EXIT trap unpauses them too (they are added to `paused`, not handled separately).
- A typo in a name (e.g. `jelu-app`) -> silently never paused. The names must match container_name exactly.
Docs: docs/m4-backups.md Consistency bullet (as above). No CLAUDE.md change.

## Manual steps
Deploy as usual. After the next nightly run, `journalctl -u homelab-backup -n 20` should show jelu and wardrobe in the "paused:" and "unpaused:" lines, and `scripts/dc.sh tools/jelu ps` and `scripts/dc.sh tools/wardrobe ps` should both show Up. (Optional) Do a test restore of /srv/homelab/jelu/database and /srv/homelab/wardrobe following docs/restore.md.

## Review notes
1. /home/dan/homelab/.worktrees/backup-pause-jelu-wardrobe/scripts/backup.sh:6-7: the reflowed header comment line now runs past the usual width ("...(incl. fitness, hermes, jelu and" sits on a long line). This is cosmetic only.
2. Pausing wardrobe for about a minute could interrupt a vision-tagging request to the Mac mini if one is running at 04:00. The request only waits and then carries on, and the same is already true of hermes. No action needed.

## Declined to judge
- Kuma alerts for jelu/wardrobe while they are paused: uptime-kuma is paused in the same window, so this matches the existing behaviour for all paused services.
- Test restore of the jelu/wardrobe data: the plan lists it as an optional manual step for Dan.
