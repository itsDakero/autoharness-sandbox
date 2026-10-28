# Close two backup gaps: unpaused SQLite apps and ~/.claude

Value: 4   (Dan: fitness check-ins and FiiT logs, Hermes state and his Claude Code memory/skills become reliably restorable)
Effort: 1  (two arrays in backup.sh plus excludes, then a test restore)
Risk: 2    (touches the nightly backup and what reaches B2; must keep the OAuth credentials and transcripts out)
Score: 20
Source: scout 2026-10-23

## Problem
(a) `scripts/backup.sh` pauses only `radarr radarr-remote sonarr sonarr-remote prowlarr jellyfin seerr
uptime-kuma autokuma ntfy`. Not paused:
- `fitness.db` (15.9 MB, WAL mode in `tools/fitness/app/db.py`): check-ins and FiiT logs Garmin can't
  re-sync; the app syncs every 30 min (`SYNC_EVERY_S`) while the 04:10 backup runs.
- Hermes: live WAL databases `kanban.db`, `response_store.db`, `runs_idempotency.db` (each with -wal/-shm).
restic can copy the db and its WAL at different moments. The backup takes about 7 s (Oct 23: 7,424 files,
1.380 GiB processed), so pausing two more containers costs almost nothing.

(b) `SOURCES=("$REPO" /srv/homelab)` leaves out `~/.claude`: Dan's auto-memory (`projects/*/memory`,
32K), user `settings.json`, user skills (`skills/`, 4.4M) and plugin config. They sit only on sda, the
2009 HDD Scrutiny already flags.

## Proposal
In `scripts/backup.sh` and `scripts/backup-excludes.txt` only:
- Add `fitness` and `hermes` to `PAUSE`.
- Add an allow-list of `~/.claude` paths to `SOURCES`: `settings.json`, `projects/*/memory`, `skills/`,
  plugin config.
- Excludes must keep out of restic and B2: `.credentials.json` (OAuth token), `projects/**/*.jsonl`
  transcripts (236M, may hold pasted secrets), `history.jsonl`, `file-history`, `cache`, `session-env`,
  `shell-snapshots`.
The script runs as root via systemd, so use the absolute path `/home/dan/.claude/...`, not `~`. No
change to systemd units or `bootstrap.sh` should be needed. Update `docs/m4-backups.md` and
`docs/restore.md` with the new paths.

## Existing tools checked
- restic (already in use): retention 7 daily / 4 weekly / 6 monthly; backup journal Oct 22 and 23 healthy
  (local about 7 s, B2 copy about 8 s, 3 packs). B2 growth from this stays under 5 MB.
- No new tool needed.

## Rough plan
1. Add `fitness` and `hermes` to `PAUSE`; confirm both restart after the run (check with `dc.sh ps`).
2. Add the `~/.claude` allow-list and excludes; dry-run with `restic backup --dry-run -vv` (or `restic ls
   latest` after a run, with Dan) and confirm `.credentials.json` and `*.jsonl` are absent.
3. Test-restore `fitness.db` to a scratch dir and open it with `sqlite3 ... 'PRAGMA integrity_check'`.
4. Docs: `docs/m4-backups.md`, `docs/restore.md`.

_Approved on the dashboard, 2026-10-23._

## Plan
Goal: Pause fitness and hermes during the nightly restic backup, and add an allow-list of Dan's `~/.claude` config and memory to the backup. OAuth credentials and transcripts stay out.
Kind: change to scripts/backup.sh (nightly restic backup)
Files:
- scripts/backup.sh: two changes.
  - Append `fitness hermes` to `PAUSE`.
  - After `SOURCES=(...)`, add a `CLAUDE_HOME=/home/dan/.claude` block. It appends each of the paths below to `SOURCES`, but only if the path exists (`[[ -e $p ]]`). restic fails on a missing source, so a missing path has to be skipped rather than break the backup.
    - `$CLAUDE_HOME/settings.json`
    - `$CLAUDE_HOME/skills`
    - `$CLAUDE_HOME/projects/*/memory` (bash glob, expanded with `shopt -s nullglob` and then restored)
    - `$CLAUDE_HOME/plugins/known_marketplaces.json`
    - `$CLAUDE_HOME/plugins/synced`
    - `$CLAUDE_HOME/plugins/data`
  - Do not add `plugins/marketplaces` (16M of git clones that can be downloaded again) or `plugin-directory-cache-v2.json` (a cache).
  - Use absolute paths only, no `~` and no `$HOME` (root runs this under systemd).
  - Update the header comment to say that the backup includes the `~/.claude` allow-list and pauses fitness and hermes.
- scripts/backup-excludes.txt: add a commented safety-net block. Even though the sources are an allow-list, these must never reach restic or B2:
  /home/dan/.claude/.credentials.json
  /home/dan/.claude/**/*.jsonl
  /home/dan/.claude/history.jsonl
  /home/dan/.claude/file-history
  /home/dan/.claude/cache
  /home/dan/.claude/paste-cache
  /home/dan/.claude/session-env
  /home/dan/.claude/shell-snapshots
  /home/dan/.claude/sessions
  /home/dan/.claude/plugins/marketplaces
  /home/dan/.claude/plugins/plugin-directory-cache-v2.json
- docs/m4-backups.md:
  - "What" bullet (line ~7): add the `~/.claude` allow-list and the safety-net excludes, and why (sda is old, and credentials and transcripts are kept off B2).
  - "Consistency" bullet (line ~13): add fitness and hermes to the paused list.
- docs/restore.md:
  - Section 0 "Backed up": add the `/home/dan/.claude` allow-list.
  - Add a short subsection under (a) on restoring Claude memory/skills. Restore with `--include /home/dan/.claude` to `/tmp/restore-claude`, then copy back as dan with `cp -a`. Note that `.credentials.json` is not in backups, so after a server rebuild Dan logs in to Claude Code again.
  - Case (c): add a line saying the same.
New service (if any): none
New env vars: None
Checks the builder must run:
- `bash -n scripts/backup.sh`
- A sourcing-free sanity check that the allow-list expands. Copy the `SOURCES` and `CLAUDE_HOME` block into a scratch script, run it as dan, and print `${SOURCES[@]}`. The output must list the 2 memory dirs, settings.json, skills and the plugin paths, and must not include `.credentials.json`, any `*.jsonl`, or `plugins/marketplaces`.
- `git diff --stat`, which should touch only the 4 files above.
- Do not run `backup.sh` or restic. Both need root.
Review focus:
- A path in the allow-list is missing (e.g. `plugins/data` deleted, or no `projects/*/memory`): the path is skipped, the backup still succeeds, and there is no restic "does not exist" error or exit 3.
- The nullglob matches nothing: no literal `*` path is passed to restic, and nullglob is reset afterwards so the rest of the script behaves as before.
- fitness or hermes is stopped at 04:10: the existing loop skips it, it stays stopped, and there is no warning spam.
- The backup fails while fitness or hermes is paused: the existing `trap unpause EXIT` unpauses both. Nothing special is needed for them (only autokuma gets the restart).
- Credentials or transcripts leak into a snapshot: impossible both by allow-list and by the excludes. The reviewer checks that neither list includes `.credentials.json` or `projects/*/*.jsonl`.
Docs: docs/m4-backups.md ("What" and "Consistency" bullets), docs/restore.md (section 0, a new Claude memory subsection, a case (c) note). CLAUDE.md doesn't change (the backup.sh description there stays accurate).

## Manual steps
After the deploy, verify with Dan:
1. `sudo systemctl start homelab-backup.service`, then `journalctl -u homelab-backup -n 20`. Expect "paused: … fitness hermes" and "backup done". Then `scripts/dc.sh tools/fitness ps` and `scripts/dc.sh tools/hermes ps` should both show Up.
2. Run this. It must print nothing:
   `sudo restic -r /mnt/backup/restic --password-file /etc/restic/password --cache-dir /var/cache/restic ls latest /home/dan/.claude | grep -E 'credentials|\.jsonl|marketplaces/'`
3. Run this. It must list memory, skills and settings.json:
   `sudo restic ... ls latest /home/dan/.claude | head`
4. Test-restore fitness.db and check it:
   `sudo restic ... restore latest --include /srv/homelab/fitness --target /tmp/restore-fitness`
   then `python3 -c "import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check').fetchone())" /tmp/restore-fitness/srv/homelab/fitness/fitness.db`
   Expect `('ok',)`. Then remove the scratch dir.
5. The off-site copy picks this up automatically. No changes to systemd or bootstrap.sh.

## Review notes
1. /home/dan/homelab/.worktrees/backup-pause-fitness-and-claude/scripts/backup.sh:7: the header comment now breaks oddly after "so the". It's cosmetic; re-wrapping it would fix it.
2. docs/m4-backups.md still says the pause lasts "about a minute". Recent runs take about 7 s, so the line is out of date but harmless.
3. Pausing hermes for the few seconds of the backup is far shorter than Discord's gateway heartbeat (about 41 s), so it should not drop the bot. Still, check `scripts/dc.sh tools/hermes logs` after the first run (manual step 1).
4. `plugins/synced` holds a gitkraken `mcp.json`. I searched it, `plugins/data`, `settings.json` and `known_marketplaces.json` for token/secret/key/password/bearer and found nothing. If a plugin later stores a token there, it would reach B2, so keep an eye on it.

## Declined to judge
None
