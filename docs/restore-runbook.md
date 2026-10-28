# Restore one service's appdata from restic

For Dan. One service's folder(s) under `/srv/homelab` broke or lost data; the rest of
the server is fine. Bring back that service's appdata from a restic snapshot, without
touching any other service.

Other cases (backup disk lost, server dead, Home Assistant, Omada) are in
`docs/restore.md`. Backup setup is in `docs/m4-backups.md`.

Steps marked **UNTESTED** have not been run yet. Remove the mark once a step works.

## 0. Before you start
- Snapshots: local repo `/mnt/backup/restic` (nightly 04:00, tag `nightly`; kept 7 daily,
  4 weekly, 6 monthly). B2 holds the same snapshots (`docs/restore.md`, case b).
- The repo is root-only, so every `restic` command runs with `sudo`. Password:
  `/etc/restic/password`. Never print it.
- Paths inside a snapshot are absolute: restoring `/srv/homelab/seerr` with
  `--target /tmp/restore-seerr` gives `/tmp/restore-seerr/srv/homelab/seerr`.
- Always restore to `/tmp` first, look, then copy back. Never `--target /` on a working server.
- Typing the long restic options each time is error-prone. Set them once in your shell
  (no secret in it, only the file path):
```bash
R="sudo restic -r /mnt/backup/restic --password-file /etc/restic/password --cache-dir /var/cache/restic"
```

## 1. Find the service's folders
A service can own more than one folder. Read them from its compose file
(`${APPDATA_PATH}` = `/srv/homelab`):
```bash
grep -n 'APPDATA_PATH' tools/paperless/compose.yaml
```

Services with more than one folder, or a folder with another name:

| Service | Compose dir | Folders under `/srv/homelab` |
|---|---|---|
| qbittorrent | `media/qbittorrent` | `qbittorrent`, `gluetun` |
| uptime-kuma | `core/uptime-kuma` | `uptime-kuma`, `autokuma` |
| dashboard | `core/dashboard` | `dashboard` (incl. `actions`, `agent-feed`), `ops-actions` |
| hermes | `tools/hermes` | `hermes` (it also writes `dashboard/agent-feed`: leave that to the dashboard) |
| paperless | `tools/paperless` | `paperless/{data,media,consume,export,redis}`: restore `paperless` whole |
| jellyfin | `media/jellyfin` | `jellyfin/config` (`jellyfin/cache` is not backed up) |
| scrutiny | `tools/scrutiny` | `scrutiny/config` (`scrutiny/influxdb` is not backed up) |
| omada | `core/omada` | use `docs/restore.md`, case e (the live DB is not backed up) |
| ha-backups | `core/ha-backups` | use `docs/restore.md`, case d |

Everything else: one folder named after the service.

**Not in any snapshot** (`scripts/backup-excludes.txt`): logs, `logs.db*`, `MediaCover`,
`Sentry`, `*.pid`, Jellyfin cache/transcodes, `gluetun/servers.json`, AdGuard's query log,
Scrutiny's InfluxDB, Omada's `data/db`, `/srv/homelab/forensics`. These come back empty;
the apps rebuild them.

## 2. Pick a snapshot
List the snapshots (newest last):
```bash
$R snapshots
```

`latest` is the newest. If the damage happened before last night's 04:00 run, `latest`
holds the damage too: pick the last snapshot from **before** it and use its ID instead
of `latest` below.

To see what changed in a folder between two snapshots:
```bash
$R diff <older-id> <newer-id> | grep '/srv/homelab/seerr/'
```

## 3. Restore to /tmp and look
Example: `seerr` (compose dir `media/seerr`, folder `seerr`). For more folders, add one
`--include` per folder.
```bash
$R ls <id> /srv/homelab/seerr
```
```bash
$R restore <id> --target /tmp/restore-seerr --include /srv/homelab/seerr
```
```bash
sudo ls -la /tmp/restore-seerr/srv/homelab/seerr
```

Check sizes look right (a 0-byte database means the wrong snapshot):
```bash
sudo du -sh /tmp/restore-seerr/srv/homelab/seerr /srv/homelab/seerr
```

## 4. Swap it in
1. Stop the service (every container in its compose file).
```bash
scripts/dc.sh media/seerr stop
```

2. **UNTESTED.** Move the broken folder aside. Keep it until the restore works.
```bash
sudo mv /srv/homelab/seerr /srv/homelab/seerr.broken
```

3. **UNTESTED.** Copy the restored folder back, keeping owners and modes. Create the
   folder and copy its contents (`/.`), so it never lands nested as `seerr/seerr`.
```bash
sudo mkdir -p /srv/homelab/seerr
```
```bash
sudo cp -a /tmp/restore-seerr/srv/homelab/seerr/. /srv/homelab/seerr/
```

4. Check owners match the list in `keep/owners.txt` (`docs/restore.md`, section 0).
   `cp -a` keeps them, so this should already be right. **Do not chown `/srv/homelab`.**
```bash
sudo stat -c '%u:%g %a %n' /srv/homelab/seerr
```
```bash
grep '/srv/homelab/seerr$' /srv/homelab/keep/owners.txt
```

5. Start it again.
```bash
scripts/dc.sh media/seerr up -d
```

## 5. Check
1. Wait a minute, then check the container is healthy and Kuma is up.
```bash
scripts/dc.sh media/seerr ps
```
```bash
scripts/kuma-status.py seerr
```

2. Open the service from the dashboard and check the data you lost is back.

3. Logs, if it does not come up:
```bash
scripts/dc.sh media/seerr logs --tail 50
```
   Or run `/debug-service seerr`.

4. Only when it works: delete the moved-aside folder and the restore folder.
```bash
sudo rm -r /srv/homelab/seerr.broken /tmp/restore-seerr
```

**Roll back** (the restore is worse than before): stop the service, move the restored
folder away, move `seerr.broken` back to `seerr`, start it.

## Per-service notes
- **SQLite and consistency.** `scripts/backup.sh` pauses the arr apps, Jellyfin, Seerr,
  Kuma/AutoKuma, ntfy, fitness, hermes, books and wardrobe during the backup, so their
  snapshots are one consistent point. Other services (e.g. mealie, paperless, fpl, lms,
  changedetection, leafgreen, dashboard) are backed up while running. Their database is
  usually fine; if the app reports a corrupt DB after the restore, try the snapshot
  before.
- **uptime-kuma**: restore `uptime-kuma` and `autokuma` together, from the same snapshot.
  After the start, restart AutoKuma so it logs in again:
  `scripts/dc.sh core/uptime-kuma restart autokuma`.
- **qbittorrent**: the stop/start covers Gluetun too (same compose file). `servers.json` is
  re-downloaded by Gluetun.
- **paperless**: restore all of `paperless` from one snapshot (`data` holds the database,
  `media` the documents; they must match). Its Redis is a queue only.
- **Arr apps**: after a restore, the app may show files as missing until its next disk
  scan. `/mnt/media` is never in a snapshot and never touched by a restore.
- **One file only**: `--include` the file's full path, then `sudo cp -a` just that file.
  Files tracked in git come back with `git restore <file>`.

## Backup disk lost
`$R` does not work for B2: the B2 key must be loaded inside a root shell, so it is never
printed. Run each restic command in that shell (`docs/restore.md`, case b). Steps 2 and 3:
```bash
sudo bash -c 'set -a; . /etc/restic/b2.env; restic -r b2:dan-homelab-restic-x7k2:homelab \
  --password-file /etc/restic/password --cache-dir /var/cache/restic snapshots'
```
```bash
sudo bash -c 'set -a; . /etc/restic/b2.env; restic -r b2:dan-homelab-restic-x7k2:homelab \
  --password-file /etc/restic/password --cache-dir /var/cache/restic \
  restore <id> --target /tmp/restore-seerr --include /srv/homelab/seerr'
```
Then steps 4 and 5 as above.
