# M4 backups – runbook

## Stage A: local restic backups
- **Disk**: `/dev/sdc` (ext4, 916 GB) at `/mnt/backup` (fstab, `nofail`). Set up by hand.
- **Repo**: `/mnt/backup/restic`, root-only. Its password is in `/etc/restic/password` (root-only). Keep a copy
  of the password **off this box** in a password manager. Without it the repo can't be read.
- **What**: the homelab repo, including `.git` and `.env`, and `/srv/homelab`, which holds every app's config
  and `keep/` (Omada and router backups). It does not back up `/mnt/media`: that is never a source, and
  `scripts/backup-excludes.txt` lists it too as a safety net. Caches, logs, `MediaCover`, Sentry,
  `gluetun/servers.json` and the AdGuard query log are excluded too. Jellyfin `config/metadata` (~900 MB) is kept.
  Also an allow-list of `/home/dan/.claude`: `settings.json`, `skills/`, `projects/*/memory`, and the plugin
  config (`plugins/known_marketplaces.json`, `synced`, `data`), because sda is an old disk. Missing paths are
  skipped. `.credentials.json` (OAuth token), the `*.jsonl` transcripts, history, caches and sessions are
  never sources and are also in `backup-excludes.txt`, so they stay off B2.
- **When**: `homelab-backup.timer` runs daily at 04:00 (plus up to 15 min of random delay). With `Persistent=true`,
  a missed run happens at the next boot. It runs `scripts/backup.sh` as root through `homelab-backup.service`.
- **Consistency**: the script runs `docker pause` on radarr, radarr-remote, sonarr, sonarr-remote, prowlarr,
  jellyfin, seerr, uptime-kuma, autokuma, ntfy, fitness, hermes, books and wardrobe for the `restic backup` step only (about a minute), then
  unpauses them, including when the backup fails. This gives a single crash-consistent copy of each SQLite DB
  and its WAL. adguard, gluetun, qbittorrent and traefik are never paused. Containers that are stopped stay stopped.
- **Retention**: `forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune` after each backup, and
  `restic check` on Sundays.
- **Cache**: the script sets `RESTIC_CACHE_DIR=/var/cache/restic`. Under systemd, root has no `$HOME`, so restic
  would otherwise run without a cache and print a warning.
- **Alert**: when the service fails (a script error, a missing mount or a timeout), systemd runs
  `homelab-backup-failure.service`. That posts a high-priority ntfy message to `NTFY_ALERT_TOPIC`, with the
  last 15 journal lines as the body.
- **Units**: `systemd/*.service|timer` in the repo. `sudo ./bootstrap.sh` installs and enables them, so run it
  again after editing them.
- Root runs a script that `dan` can edit. That isn't a new risk, because `dan` is in the `docker` group, which is
  already root-equivalent.

### Commands
```bash
systemctl list-timers homelab-backup.timer             # next run
sudo systemctl start homelab-backup.service            # back up now
journalctl -u homelab-backup -n 50                     # last run (dan is in adm)
scripts/backup.sh test-alert                           # ntfy test, no root
sudo systemctl start homelab-backup-failure.service    # real failure alert path
R="sudo restic -r /mnt/backup/restic --password-file /etc/restic/password --cache-dir /var/cache/restic"
$R snapshots
$R ls latest | less
$R restore latest --target /tmp/restore-test --include /srv/homelab/keep    # restore a subset
```

### Restoring an app
Stop the app first (`scripts/dc.sh <dir> stop`). Then restore its directory to a temporary target, check it,
and copy it back over `/srv/homelab/<service>/` keeping the owners (`cp -a` as root). Start the app again.
For a whole-box restore, restore the repo first, put back `.env`, then `/srv/homelab`, then run `core-up.sh`
and the media stacks. If the backup disk is lost, restore from B2 instead (stage B). That needs the restic
password and the B2 key, so keep both off this box.

## Stage B: off-site copy to Backblaze B2
- **Repo**: `b2:dan-homelab-restic-x7k2:homelab`, created by hand. It uses the same password file as the local
  repo. The B2 key (`B2_ACCOUNT_ID`, `B2_ACCOUNT_KEY`) is in `/etc/restic/b2.env` (root-only). The script loads it
  and never prints it.
- **What**: `restic copy` of every local `nightly` snapshot that B2 doesn't have yet. On a normal night that is
  just tonight's; after a missed or failed night it catches up. There is no second backup, so apps are paused
  only once, and B2 only ever holds snapshots that passed the local run. `/mnt/media` is never involved.
- **When**: `homelab-backup.service` has `OnSuccess=homelab-backup-offsite.service`. The copy starts only after a
  successful local backup, and never if the local backup failed. It has no timer of its own. It runs
  `scripts/backup.sh offsite` and shares the local run's lock, so the two never overlap.
- **Retention**: the same `forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6` runs every night. `prune` runs
  only on Sundays, to keep B2 API calls low.
- **Check**: Sundays only, `restic check --with-cache --read-data-subset=N/12`, where N comes from the ISO week.
  Each week reads a different twelfth of the data, so all of it is read about once a quarter. There is no full
  check. `--with-cache` reuses `/var/cache/restic` instead of downloading all tree data again.
- **Alert**: a failure (copy, forget, prune, check, missing key, network) runs
  `homelab-backup-offsite-failure.service`. That posts "Homelab off-site backup FAILED" to `NTFY_ALERT_TOPIC`,
  with the last 15 lines of `homelab-backup-offsite`.
- **B2 bucket**: set its lifecycle to "Keep only the last version". Otherwise files that restic prunes are
  kept as hidden versions and still billed. The key should be limited to this bucket.

### Commands
```bash
sudo systemctl start homelab-backup-offsite.service          # copy now (no local backup)
journalctl -u homelab-backup-offsite -n 50                   # last run
sudo systemctl start homelab-backup-offsite-failure.service  # real off-site alert path
# B2 repo access (key loaded inside the root shell, never printed):
sudo bash -c 'set -a; . /etc/restic/b2.env; restic -r b2:dan-homelab-restic-x7k2:homelab \
  --password-file /etc/restic/password --cache-dir /var/cache/restic snapshots'
```
Replace `snapshots` with e.g. `restore latest --target /tmp/restore-test --include /srv/homelab/keep`.

## Stage C: Home Assistant backups
- **What**: HA OS on the Pi (`192.168.0.78`) writes its backups to an SMB share on this server.
  The share folder is `/srv/homelab/ha-backups`, which is already a restic source, so stages A and B
  copy the files to `/mnt/backup` and B2 every night. `backup.sh` is unchanged.
- **Share**: `//192.168.0.210/ha-backups`, user `hass`, password `HA_BACKUP_SMB_PASSWORD` in `.env`.
  The share is served by the `ha-backups` container (`core/ha-backups`, image `dockurr/samba`).
  The repo's `core/ha-backups/smb.conf` is mounted read-only over the image's own config. It allows
  SMB3 only, with signing mandatory, no guest access and the one user. Files land as `dan`
  (uid 1000), mode 0640.
- **Access**: the share is published on `192.168.0.210:445` only, so it is not on Tailscale or IPv6.
  Never forward it on the router. Docker ports skip UFW, so there are two layers instead:
  1. `hosts allow = 192.168.0.78 127.0.0.1` in `smb.conf`. smbd closes other connections before they
     log in. `127.0.0.1` is the container itself, for `smbclient` tests.
  2. A DOCKER-USER rule. It drops tcp 445 to the LAN IP on the LAN interface from any source except
     the Pi. `scripts/docker-user-rules.sh` (root; `add`/`remove`/`show`) owns it and only ever touches
     its own rule, which is tagged `homelab-ha-backups-smb`. `homelab-docker-user.service` runs it after
     every docker start, because iptables rules don't survive a reboot. `bootstrap.sh` installs that unit.
- **Monitoring**: Uptime Kuma runs a TCP check on `192.168.0.210:445` every 5 minutes. It comes from the
  `monitor` bridge, not the LAN interface, so the DOCKER-USER rule doesn't drop it. smbd accepts the
  connection and then refuses it, so `ha-backups` logs one "Denied connection" line per check. The
  dashboard tile has no link, because SMB isn't a web page.
- **Freshness**: `scripts/ha-backup-check.sh` runs from dan's crontab at 09:00 (`install-cron.sh`). It
  posts a high-priority ntfy alert when the newest file in the share is more than 9 days old, or when
  there is none. It repeats daily until a fresh backup lands. It is kept out of `backup.sh` on purpose:
  a stale HA backup must not mark the server backup as failed or block the B2 copy.
  - Last run: `journalctl -t ha-backup-check -n 20`
  - Test: `scripts/ha-backup-check.sh test`
- **Size**: HA backups are compressed and usually encrypted, so restic deduplicates them badly. Each
  new backup adds about its full size to both repos. HA's own "keep 4" setting bounds the total.

### Steps in the HA UI
1. **Settings > System > Storage > Add network storage**:
   - Name `homelab`, usage **Backup**, server `192.168.0.210`
   - Protocol **Samba/Windows (CIFS)**, remote share `ha-backups`
   - Username `hass`, the password, version **Auto**
2. **Settings > System > Backups > Configure** (automatic backups):
   - Schedule: **weekly**, at **02:00** HA time. That keeps it clear of the server's 04:00–04:30
     backup window in both GMT and BST.
   - Keep: **4** backups. Location: tick **homelab**. The Pi's own storage can stay ticked too.
   - Weekly backups leave 2 days of grace before the 9-day alert fires.
3. **Save the backup encryption key** (HA's "emergency kit") in the password manager, next to the restic
   password. Without it, none of these copies can be restored.
4. Click **Back up now** once, then check that a `.tar` appears in `/srv/homelab/ha-backups`.

### If HA can't mount the share
Check `scripts/dc.sh core/ha-backups logs --tail 50` and HA's Supervisor log.
- "Denied connection": the Pi's IP has changed. Its address must stay `192.168.0.78` (DHCP reservation).
- Signing errors: as a fallback, change `server signing = mandatory` to `server signing = auto` in
  `core/ha-backups/smb.conf`, then `scripts/dc.sh core/ha-backups restart`. This is not applied by
  default. Go back to `mandatory` if it turns out signing wasn't the cause.

### Restoring Home Assistant
Using `$R` from stage A:
1. Find a snapshot that holds the backup you want: `$R ls latest /srv/homelab/ha-backups`. Use a
   snapshot ID from `$R snapshots` for an older one.
2. Restore it to a temporary folder:
   `$R restore latest --target /tmp/restore-ha --include /srv/homelab/ha-backups`.
   If the backup disk is lost, use the B2 command from stage B.
3. Then either:
   - **HA still running**: copy the `.tar` back into `/srv/homelab/ha-backups` (as root, `cp -a`). It
     appears under Settings > System > Backups for the `homelab` location. Restore it from there.
   - **New Pi or SD card**: copy the `.tar` to a laptop (`scp`). Choose "Restore from backup" during
     HA onboarding and upload it. Then add the network storage again (steps above).
4. Enter the backup encryption key when HA asks.

### Commands
```bash
scripts/dc.sh core/ha-backups logs --tail 50              # smbd log, denied connections
docker exec ha-backups testparm -s                        # effective Samba config
docker exec -it ha-backups smbclient //127.0.0.1/ha-backups -U hass -m SMB3 -c ls
sudo scripts/docker-user-rules.sh show                    # DOCKER-USER chain
sudo scripts/docker-user-rules.sh remove                  # drop the rule (until next docker start)
systemctl status homelab-docker-user.service
```

## Stage D: disk health (Scrutiny)
Scrutiny reads SMART data from the three disks and keeps the history. A daily script turns its
verdict into an ntfy alert, so a dying disk shows up before the backups need it.

| Disk | Drive | smartctl type | Notes |
|---|---|---|---|
| sda | Hitachi HTS723225L9A360 250G (OS) | `sat` | known 187/188 exception, see below |
| sdb | Seagate ST4000DM004 4TB (media) | `sat` | |
| sdc | Samsung 860 EVO 1TB (USB) | `sat` | USB bridge hides the overall verdict |

- `tools/scrutiny/compose.yaml`: omnibus image (web UI + collector + InfluxDB), port 8084 published on
  all interfaces (`8084:8080`), so the dashboard tile works from the LAN and the tailnet. (It was LAN IP
  only at first, which broke the tile on tailnet devices: `homelab` resolves to the Tailscale IP there.)
- The disks are passed in read-only (`/dev/sdX:/dev/sdX:r`) with `SYS_RAWIO`; smartctl works with that
  on all three. `/run/udev` is mounted read-only for disk names.
- `/srv/homelab/scrutiny/config/collector.yaml` lists the three disks as type `sat`. It has no notify
  section: Scrutiny's own notifications are not used, so the ntfy topic is in no file.
- The collector runs inside the container daily at midnight (Scrutiny default).
- sdc: smartctl prints "SMART Status not supported: Incomplete response", and the collector's
  `--xall` run exits with code 4 (checksum error), because the USB bridge doesn't pass everything
  through. smartctl still judges the disk from its attributes. Normal for USB bridges.
- Backups: `scrutiny/config` (settings, `scrutiny.db`) is backed up. `scrutiny/influxdb` (SMART and
  temperature history) is excluded in `backup-excludes.txt`; after a restore the history starts again.
- Uptime Kuma checks `http://${LAN_IP}:8084/api/health`.

### Alerts: `scripts/scrutiny-check.sh`
Cron, daily 09:05 (installed by `scripts/install-cron.sh`). Reads `/api/summary` and alerts on the
`NTFY_ALERT_TOPIC` (priority high) when:
- a disk has `device_status` other than 0 (1 = SMART's own verdict failed, 2 = Scrutiny's thresholds
  failed, 3 = both), except the sda case below
- fewer than 3 disks are reported (archived disks don't count)
- a disk's newest collection (`collector_date`) is older than 3 days, or missing
- the API doesn't answer, or the summary has an unexpected format

It repeats daily until fixed. Logs: `journalctl -t scrutiny-check`.

### The sda exception
sda (the Hitachi OS disk) is status 2 because of two attributes. SMART's own verdict is PASSED:
- **187 Reported_Uncorrect**: raw `261331580224021`. A packed vendor value, not a real count
  (normalised 100, threshold 0).
- **188 Command_Timeout**: raw 329. Real but old: the drive's error log holds 369 errors, the latest at
  2,602 power-on hours (the drive is past 12,700).
- 5, 196, 197 and 198 (reallocated, reallocation events, pending, uncorrectable sectors) are all 0.

Scrutiny v0.9.5 can't ignore attributes per disk. The disk detail settings dialog is a placeholder
("not yet implemented"), and the dashboard settings (`status_threshold`, `status_filter_attributes`)
are global and only affect Scrutiny's own notifications, not `device_status`. So the exception lives in
the script (`sda_known_ok`). sda's status 2 is accepted only while all of these hold:
- the disk's WWN is `SDA_WWN=0x5000cca583cdf8cb`. The WWN stays with the drive; the name `sda` can move
  after a reboot or USB replug.
- `device_status` is exactly 2, so SMART's own verdict still passes
- raw values of 5, 196, 197 and 198 are all 0
- 188 raw is below `SDA_MAX_188=1000`, so the exception ends if timeouts keep climbing
- no attribute other than 187 and 188 is failing

Anything else, including a failed details call or a missing attribute, alerts. The ok line in syslog
says `(sda: known 187/188 accepted)` when it applies. If sda is replaced, remove `SDA_WWN`,
`SDA_MAX_188` and `sda_known_ok`.

### Commands
```bash
scripts/scrutiny-check.sh                                  # run the check now (result in syslog)
scripts/scrutiny-check.sh test                             # test notification
journalctl -t scrutiny-check -n 20
docker exec scrutiny scrutiny-collector-metrics run        # collect now instead of at midnight
docker exec scrutiny smartctl -i -H /dev/sda               # sdc needs -d sat
docker exec scrutiny smartctl -A /dev/sda                  # attribute table
curl -s http://192.168.0.210:8084/api/summary | jq '.data.summary[].device | {device_name, device_status}'
```

### Alerts: `scripts/disk-space-check.sh`
Cron, daily 09:10 (installed by `scripts/install-cron.sh`). Reads `df` only: no root, no container. Alerts on
the `NTFY_ALERT_TOPIC`:
- `/mnt/media` at 70% or more (default priority): "time to build storage cleanup part B" (see
  `docs/m2-media.md`, Watched-media cleanup report)
- `/` and `/mnt/backup` at 85% or more (high priority); `/srv/homelab` too, only if it becomes its own mount
- any of them at 95% or more (high priority); this replaces the warn alert

Repeats: a warn alert at most once a week per disk, a 95% alert daily. A disk that drops below its
threshold is forgotten, so the next crossing alerts at once. State: `/srv/homelab/disk-space-check/state`
(`<mount> <warn|crit> <epoch>`); a missing or corrupt file counts as "never sent", and it is only updated
after ntfy accepted the post. An unmounted `/mnt/backup` is logged and skipped (backup.sh fails loudly on
that); an unreadable `df` result is logged, skipped, and the script exits 1.
```bash
scripts/disk-space-check.sh                 # run the check now (result in syslog)
scripts/disk-space-check.sh test            # test notification
journalctl -t disk-space-check -n 20
```

### Diun (skipped)
Diun (image update notifications) was in the first plan for this stage and dropped before anything
was built: not installed, to keep this stage to disk health. Adding it later needs:
- `IMAGES: 1` in `core/docker-socket-proxy` (still read-only, `POST: 0` stays), and Diun on the
  `socket-proxy` network. Never its own `docker.sock` mount.
- its own low-priority ntfy topic (e.g. `NTFY_UPDATES_TOPIC`), so update notices don't mix with alerts
- `diun.enable=true` labels on the services to watch, and a pinned Diun image

Instead: `scripts/image-check.py` (no container, no socket). Cron, Mondays 09:10 (`scripts/install-cron.sh`):
reads the pinned images from the tracked compose files and posts one Discord digest (service, current,
newest, patch/minor/major, and the `/update-stack <name>` to run); a quiet week is one "all current" line.
Flavour rule: a candidate tag must have the current tag's shape (every digit run replaced by `N`, so `v`,
`-rootless`, `-lsN` are kept; `latest`, `12.2`, rc/beta are dropped); highest wins. `HOLDS` in the script
lists lines pinned on purpose (Omada 6.2.x, AutoKuma 2.x): shown as "held", not pending. If the GitHub
release notes between current and newest mention security / CVE / GHSA, the line says SECURITY and ntfy
(high) fires once per image:tag (the `alerted` list); the digest keeps flagging it every week. Images
that can't be checked (registry down, GitHub rate limit for notes) are listed, never counted as current.
Cache with GitHub ETags and `alerted`: `~/.cache/homelab/image-check.json` (missing or corrupt = starts
empty). `scripts/image-check.py --print` shows the digest only (no Discord, no ntfy, `alerted` kept);
logs: `journalctl -t image-check`.
