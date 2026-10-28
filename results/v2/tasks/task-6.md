I've added `scripts/restore-drill.sh`, a monthly restore drill. It runs from a systemd timer, not cron: the restic repo and `/etc/restic/password` are root-only, and `backup.sh` already runs as root under systemd. So there's no `cron.d` file and no Kuma push monitor. Kuma can't watch a monthly job anyway, because its push interval tops out at 24 days. It has only been tested in the sandbox with a fake `restic`, never against a real repo.

**What the drill does**
- **Which folder:** it rotates by month through 12 appdata folders: radarr, sonarr, prowlarr, seerr/config, jellyfin/config, uptime-kuma, dashboard, fitness, books, wardrobe, mealie, paperless. `restore-drill.sh <folder>` drills any other folder by hand.
- **Restore:** it takes the newest `nightly` snapshot of `/srv/homelab` and restores that one folder with `restic restore --verify` into a fresh root-only temp dir under `/var/tmp`.
- **Checks:** the restored files must match the snapshot's listing in file count and total bytes, and at least one file must be non-empty. It also checks there is enough free space before restoring, and always deletes the temp dir.
- **Snapshot age:** the restore is checked first, then the drill fails if the snapshot is 48 hours or older. The failure message says which part failed.
- **Reports:** one Discord line either way, with the folder, snapshot ID, age, file count, size and duration. On failure it exits 1 and systemd runs a failure unit that sends ntfy with the last 15 journal lines. That also covers timeouts and crashes. `test-alert` sends a test ntfy, like `backup.sh`.

**Wiring**
- Three new units in `systemd/`: `homelab-restore-drill.service`, `homelab-restore-drill.timer` (1st of the month, 10:00, catches up after downtime) and `homelab-restore-drill-failure.service`.
- `bootstrap.sh` installs them alongside the backup units and enables the timer, so the server needs `sudo ./bootstrap.sh` after merging.
- The drill uses the same lock file as the backup jobs and waits up to 2 hours for it, so it never runs during a backup or prune.

**Docs:** a new Stage E section at the end of `docs/m4-backups.md`, with commands. I also added a line in `CLAUDE.md`'s scripts list (alphabetical) and its `systemd/` entry, `docs/README.md`, `docs/restore.md` and `docs/restore-runbook.md` (which notes that steps 1–3 are now drilled monthly). `docs/new-cron-job.md` now says root-only or monthly jobs go to systemd instead of cron.

**Checks**
- `bash -n` and `shellcheck` on the new script pass. On `bootstrap.sh`, shellcheck shows only an info-level note at line 19 that was there before.
- `scripts/check.sh` passes all five checks.
- `systemd-analyze verify` on the units complains only that `/home/dan/homelab` doesn't exist here.
- With a fake `restic` and paths changed to the scratchpad, I ran four cases: a successful drill (exit 0), a 59-hour-old snapshot (fails), a missing restored file (fails) and bad arguments (exit 2). The temp dir was removed every time.

**Left undone**
- Nothing ran against real restic, systemd or Discord.
- The drill only proves the files come back. It doesn't start the app on the restored data.
- One small risk, noted in the docs: if the server boots near 04:00 and the drill runs then to catch up a missed month, it holds the lock and that night's backup fails with "another backup is running". At the normal 10:00 slot this can't happen.