# Restore runbook

For Dan. Three cases: (a) one file or app from the local repo, (b) backup disk lost,
(c) server dead. Then Home Assistant, Omada and the "keep OFF the server" list.

Steps marked **UNTESTED** have not been run yet. Case (c) gets a full drill later;
remove the marks as steps pass. Everything else uses commands from
`docs/m4-backups.md` that have run.

This file holds no secrets. Passwords and keys come from the password manager
(see the end).

## 0. Before you start
- **Backed up**: the repo `/home/dan/homelab` (incl. `.git` and the env file) and
  `/srv/homelab` (every app's config, `ha-backups/`, `keep/`), and an allow-list of
  `/home/dan/.claude` (settings, skills, memory, plugin config; no credentials or transcripts).
  Caches and logs are excluded (`scripts/backup-excludes.txt`). `/mnt/media` is **never** backed up.
- **Local repo**: `/mnt/backup/restic` (root-only), nightly at 04:00.
- **B2 repo**: `b2:dan-homelab-restic-x7k2:homelab`, copied after each good local run.
- Same restic password for both: `/etc/restic/password`. B2 key: `/etc/restic/b2.env`.
- Snapshots are tagged `nightly`. Kept: 7 daily, 4 weekly, 6 monthly.
- `latest` = newest snapshot. For an older one use its ID from the `snapshots` list.
- Always restore into a folder under `/tmp` first, look at it, then copy it back.
- Paths inside a snapshot are absolute: restoring `/srv/homelab/seerr` with
  `--target /tmp/restore-seerr` gives `/tmp/restore-seerr/srv/homelab/seerr`.
- **Record owners**: case (c), step 10 compares owners with `keep/owners.txt`. Write it
  now, and re-run after adding a service:
```bash
sudo stat -c '%u:%g %a %n' /srv/homelab/* | sudo tee /srv/homelab/keep/owners.txt
```

## a. Lost a file or one app config (local repo)
Example: `seerr`. Replace `seerr` with the service, and `media/seerr` with its
compose dir.
Jellyfin's config is about 900 MB: the same steps work, they just take longer.

1. List the snapshots and pick one.
```bash
sudo restic -r /mnt/backup/restic --password-file /etc/restic/password \
  --cache-dir /var/cache/restic snapshots
```

2. Look inside it.
```bash
sudo restic -r /mnt/backup/restic --password-file /etc/restic/password \
  --cache-dir /var/cache/restic ls latest /srv/homelab/seerr
```

3. Restore the folder to `/tmp`.
```bash
sudo restic -r /mnt/backup/restic --password-file /etc/restic/password \
  --cache-dir /var/cache/restic restore latest --target /tmp/restore-seerr \
  --include /srv/homelab/seerr
```

4. Check what came back.
```bash
sudo ls -la /tmp/restore-seerr/srv/homelab/seerr
```

5. Stop the app.
```bash
scripts/dc.sh media/seerr stop
```

6. **UNTESTED.** Move the broken folder aside (keeps it until you are sure).
```bash
sudo mv /srv/homelab/seerr /srv/homelab/seerr.broken
```

7. **UNTESTED.** Copy the restored folder back, keeping owners and modes. Create the
   folder first and copy its contents (`/.`), so it never lands nested as `seerr/seerr`.
```bash
sudo mkdir -p /srv/homelab/seerr
```
```bash
sudo cp -a /tmp/restore-seerr/srv/homelab/seerr/. /srv/homelab/seerr/
```

8. Start the app.
```bash
scripts/dc.sh media/seerr up -d
```

9. Wait a minute for the app to start and Kuma to check it again. Then check it:
   dashboard tile and Uptime Kuma.
```bash
scripts/kuma-status.py seerr
```

10. Only when it works: delete the broken folder and the restore folder.
```bash
sudo rm -r /srv/homelab/seerr.broken /tmp/restore-seerr
```

**One file only**: use `--include` with the file's full path, then copy just that file
(`sudo cp -a`). For files tracked in git, `git restore <file>` is enough. The env file is
not in git: it only comes back from restic.

### Claude memory and skills
Restore `/home/dan/.claude` to `/tmp`, look, then copy back as `dan` (no root needed for the copy).
```bash
sudo restic -r /mnt/backup/restic --password-file /etc/restic/password \
  --cache-dir /var/cache/restic restore latest --target /tmp/restore-claude \
  --include /home/dan/.claude
```
```bash
cp -a /tmp/restore-claude/home/dan/.claude/. /home/dan/.claude/
```
`.credentials.json` is not in backups: after a server rebuild, log in to Claude Code again.

## b. Backup disk lost, server fine (B2)
The B2 key is loaded inside a root shell, so it is never printed.

1. List the B2 snapshots.
```bash
sudo bash -c 'set -a; . /etc/restic/b2.env; restic -r b2:dan-homelab-restic-x7k2:homelab \
  --password-file /etc/restic/password --cache-dir /var/cache/restic snapshots'
```

2. **UNTESTED.** Restore what you need to `/tmp` (here: seerr).
```bash
sudo bash -c 'set -a; . /etc/restic/b2.env; restic -r b2:dan-homelab-restic-x7k2:homelab \
  --password-file /etc/restic/password --cache-dir /var/cache/restic \
  restore latest --target /tmp/restore-seerr --include /srv/homelab/seerr'
```

3. Then steps 4–10 of case (a).

### New backup disk
Nightly backups fail (ntfy alert) until this is done. The old snapshots stay safe in B2.

1. Plug in the new disk and find its device name. Be sure it is the new, empty disk.
```bash
lsblk -o NAME,SIZE,MODEL,SERIAL,MOUNTPOINT
```

   Stop if the disk shows a mount point, or partitions you recognise.

2. **UNTESTED.** Format it ext4. This wipes the disk: check the name twice.
```bash
sudo mkfs.ext4 -L backup /dev/sdX
```

3. Get its UUID.
```bash
sudo blkid /dev/sdX
```

4. **UNTESTED.** Edit `/etc/fstab`: replace the old `/mnt/backup` line with this one.
```bash
sudo nano /etc/fstab
```
```
UUID=<new-uuid> /mnt/backup ext4 defaults,nofail,x-systemd.device-timeout=10 0 2
```

5. **UNTESTED.** Mount it.
```bash
sudo mount /mnt/backup
```

6. Check it is mounted.
```bash
findmnt /mnt/backup
```

7. **UNTESTED.** Create the local repo with B2's chunker settings.
   Why: so the next copy to B2 does not re-upload everything.
   The root shell loads the B2 key from `b2.env` to read B2's settings;
   `--from-password-file` is B2's repo password (the same file).
```bash
sudo bash -c 'set -a; . /etc/restic/b2.env; restic init -r /mnt/backup/restic \
  --password-file /etc/restic/password --from-repo b2:dan-homelab-restic-x7k2:homelab \
  --from-password-file /etc/restic/password --copy-chunker-params'
```

8. Run a backup now (the B2 copy follows on its own).
```bash
sudo systemctl start homelab-backup.service
```

9. Check the run.
```bash
journalctl -u homelab-backup -n 50
```

10. Check the B2 copy.
```bash
journalctl -u homelab-backup-offsite -n 50
```

11. Scrutiny watches the backup disk as `sdc` (`tools/scrutiny/compose.yaml`,
    `/srv/homelab/scrutiny/config/collector.yaml`). If the new disk has another name,
    fix both. Then run the check.
```bash
scripts/scrutiny-check.sh
```

## c. Server dead, new machine
Whole plan: install Ubuntu, install restic by hand, restore the repo and `/srv/homelab`
from B2, then run `bootstrap.sh` from the restored repo. No GitHub key needed.
The env file comes back from the snapshot, so app secrets need no other copy.

**All of case (c) is UNTESTED** until the drill.

Step 9 does not restore the `/home/dan/.claude` allow-list. Restore it as in case (a), "Claude memory
and skills", using the B2 form. `.credentials.json` is not in backups: log in to Claude Code again.

1. Install Ubuntu Server 24.04. Hostname `homelab`, user `dan`. Enable OpenSSH.
   `dan` must be uid 1000 (the first user is), so restored files keep the right owner.
```bash
id dan
```

2. Install restic.
```bash
sudo apt-get install -y restic
```

3. Create the restic config folder.
```bash
sudo install -d -m 0700 /etc/restic
```

4. Type the restic password (from the password manager) as the only line.
```bash
sudo nano /etc/restic/password
```

5. Write the B2 key file: two lines, `B2_ACCOUNT_ID=<keyID>` and
   `B2_ACCOUNT_KEY=<application key>`, values from the password manager.
```bash
sudo nano /etc/restic/b2.env
```

6. Make both files root-only.
```bash
sudo chmod 600 /etc/restic/password /etc/restic/b2.env
```

7. Check B2 is reachable and pick a snapshot.
```bash
sudo bash -c 'set -a; . /etc/restic/b2.env; restic -r b2:dan-homelab-restic-x7k2:homelab \
  --password-file /etc/restic/password --cache-dir /var/cache/restic snapshots'
```

8. Check before step 9: list the two folders in the snapshot. This checks the B2 key,
   the password and the paths, and writes nothing. (`restore --dry-run` needs restic
   0.17+; this server has 0.16.4.) The output should list both folders and what is
   directly inside them.
```bash
sudo bash -c 'set -a; . /etc/restic/b2.env; restic -r b2:dan-homelab-restic-x7k2:homelab \
  --password-file /etc/restic/password --cache-dir /var/cache/restic \
  ls latest /home/dan/homelab /srv/homelab'
```

> **Warning:** only on the new, empty machine. This writes over `/home/dan/homelab` and
> `/srv/homelab`. Never run it on a working server.

9. Restore the repo and `/srv/homelab` to their real places.
```bash
sudo bash -c 'set -a; . /etc/restic/b2.env; restic -r b2:dan-homelab-restic-x7k2:homelab \
  --password-file /etc/restic/password --cache-dir /var/cache/restic \
  restore latest --target / --include /home/dan/homelab --include /srv/homelab'
```

10. Check owners. The repo should be `dan dan`:
```bash
ls -ld /home/dan/homelab
```
    If the repo shows `root root`, fix it. Only `/home/dan/homelab` may be chowned.
```bash
sudo chown -R dan:dan /home/dan/homelab
```
    Then check `/srv/homelab` against the owners list that came back with the restore:
```bash
sudo stat -c '%u:%g %a %n' /srv/homelab/*
```
```bash
cat /srv/homelab/keep/owners.txt
```
    Owner is 1000 for everything. Four folders (`adguard`, `autokuma`, `ntfy`,
    `uptime-kuma`) have group 988, the docker group on the old server. On a new machine
    a different docker GID is harmless: those folders are 775 and owned by `dan`.
    If the owner differs, the usual cause is a new `dan` without UID 1000 (step 1).
    Fix the user. **Do not chown `/srv/homelab`.**

11. Mount the media disk. Add its line to `/etc/fstab` (UUID from `sudo blkid`):
```bash
sudo nano /etc/fstab
```
```
UUID=<media-uuid> /mnt/media ext4 defaults,noatime,nofail 0 2
```

12. Mount it.
```bash
sudo mount /mnt/media
```

13. If the backup disk survived, add its fstab line too (see case b, step 4) and mount it.
    If not, set up a new one with case (b), "New backup disk", after step 26.

14. Run the bootstrap from the restored repo (Docker, Tailscale, UFW, NVIDIA 580,
    backup units, DOCKER-USER rule).
```bash
cd /home/dan/homelab
```
```bash
sudo ./bootstrap.sh
```

15. Log out and back in, so `dan` is in the `docker` group.

16. Join the tailnet. First remove the old `homelab` machine in the Tailscale admin
    console, so the name stays `homelab`.
```bash
sudo tailscale up
```

17. Reboot (NVIDIA driver), then check the GPU.
```bash
sudo reboot
```
```bash
nvidia-smi
```

18. Tailscale IP: the new machine may get a new one.
```bash
tailscale ip -4
```
    If it changed: set `TAILSCALE_IP` in the env file, update the IP in `CLAUDE.md`,
    and in the Tailscale admin console change the `lan` split-DNS nameserver.

19. Tailscale admin console: Machines > homelab > Disable key expiry.

20. Router (Virgin Hub): move the DHCP reservation for 192.168.0.210 to the new machine's
    MAC. The HA Pi, the SMB rule and the env file all expect that address.
    The HA Pi mounts the share by IP, so the new server must keep 192.168.0.210.
    Remove the old machine's reservation on the router, then add the new one.
    The new MAC is the third column for the LAN interface:
```bash
ip -br link
```

21. Start the core services.
```bash
scripts/core-up.sh
```

22. Put the `.lan` rewrites back in AdGuard (uses `TAILSCALE_IP`).
```bash
core/adguard/apply-rules.sh
```

23. Start the media stacks, one command each, in this order: `qbittorrent` (with Gluetun),
    `prowlarr`, `radarr`, `sonarr`, `radarr-remote`, `sonarr-remote`, `jellyfin`, `seerr`.
```bash
scripts/dc.sh media/qbittorrent up -d
```
```bash
scripts/dc.sh media/prowlarr up -d
```
```bash
scripts/dc.sh media/radarr up -d
```
```bash
scripts/dc.sh media/sonarr up -d
```
```bash
scripts/dc.sh media/radarr-remote up -d
```
```bash
scripts/dc.sh media/sonarr-remote up -d
```
```bash
scripts/dc.sh media/jellyfin up -d
```
```bash
scripts/dc.sh media/seerr up -d
```

24. Start the tools. Scrutiny lists disks by `/dev/sdX` name: check them with `lsblk`
    and fix `tools/scrutiny/compose.yaml` and its `collector.yaml` first if the names
    moved.
```bash
scripts/dc.sh tools/dozzle up -d
```
```bash
scripts/dc.sh tools/scrutiny up -d
```

25. Install the cron jobs (watchdog, Seerr router, HA and Scrutiny checks, image check).
```bash
scripts/install-cron.sh
```

26. Check: all Kuma monitors up, dashboard green, a film plays in Jellyfin.
```bash
scripts/kuma-status.py
```

27. Check the SMB rule for the HA Pi.
```bash
sudo scripts/docker-user-rules.sh show
```

28. Run a backup now, then check both journals (case b, steps 9–10).
```bash
sudo systemctl start homelab-backup.service
```

29. Phone: check the alerts arrive.
```bash
scripts/backup.sh test-alert
```

## d. Home Assistant
HA OS on the Pi (192.168.0.78) writes weekly encrypted `.tar` backups to the share
`/srv/homelab/ha-backups`, which restic backs up. `/srv/homelab/keep/` also holds an older
HA backup (`automatic_backup_2026_2_1.tar`).

**You need the HA backup encryption key** (password manager). Without it no copy restores.

1. If the share still has the `.tar` you want, skip to step 4. Otherwise list a snapshot.
```bash
sudo restic -r /mnt/backup/restic --password-file /etc/restic/password \
  --cache-dir /var/cache/restic ls latest /srv/homelab/ha-backups
```

2. Restore the share to `/tmp` (backup disk lost: use the B2 form from case b, step 2).
```bash
sudo restic -r /mnt/backup/restic --password-file /etc/restic/password \
  --cache-dir /var/cache/restic restore latest --target /tmp/restore-ha \
  --include /srv/homelab/ha-backups
```

3. **UNTESTED.** Copy the `.tar` back into the share.
```bash
sudo cp -a /tmp/restore-ha/srv/homelab/ha-backups/<file>.tar /srv/homelab/ha-backups/
```

4. **UNTESTED.** Then one of:
   - **HA still running**: Settings > System > Backups. The `.tar` shows under the
     `homelab` location. Restore it from there.
   - **New Pi or SD card**: copy the `.tar` to a laptop. In HA onboarding choose
     "Restore from backup" and upload it. Then add the network storage again
     (`docs/m4-backups.md`, stage C, "Steps in the HA UI").
```bash
scp homelab:/srv/homelab/ha-backups/<file>.tar .
```

5. Enter the backup encryption key when HA asks.

6. The new Pi must keep 192.168.0.78 (router DHCP reservation), or the share refuses it.

## e. Omada controller config
The Omada controller (`core/omada`, details in `docs/m3-omada.md`) writes a `.cfg`
every day at 03:00 to `/srv/homelab/omada/data/autobackup/` (keep 7), and restic backs
that folder up. The live MongoDB (`/srv/homelab/omada/data/db`) is **not** backed up:
a restore always goes through a `.cfg` and the web UI. Oldest fallback:
`/srv/homelab/keep/omada_backup_6.2.10.17_2026-10-02_22-33-10.cfg`.

A `.cfg` restores only into a controller on the **same or a newer** version.

**You need the old controller admin login** (password manager): the restore brings back
the old accounts.

While the controller is down or empty, the APs keep broadcasting Wi-Fi with their last
config. Keep the AP ports closed until step 10, so the APs never see an empty controller.

1. Server fine: list the auto-backups and pick the newest `.cfg`.
```bash
ls -lt /srv/homelab/omada/data/autobackup
```
   Folder lost or server dead: list it in a snapshot (backup disk lost: use the B2 form
   from case b).
```bash
sudo restic -r /mnt/backup/restic --password-file /etc/restic/password \
  --cache-dir /var/cache/restic ls latest /srv/homelab/omada/data/autobackup
```

2. Only if the folder came from restic: restore it to `/tmp`.
```bash
sudo restic -r /mnt/backup/restic --password-file /etc/restic/password \
  --cache-dir /var/cache/restic restore latest --target /tmp/restore-omada \
  --include /srv/homelab/omada/data/autobackup
```

3. Copy the `.cfg` to a laptop (from `/tmp/restore-omada/srv/homelab/omada/data/...`
   if it came from restic).
```bash
scp homelab:/srv/homelab/omada/data/autobackup/<file>.cfg .
```

4. **UNTESTED.** Close the AP ports first (case (c): `bootstrap.sh` added them).
```bash
sudo ufw delete allow from 192.168.0.0/24 to any port 29810 proto udp
```
```bash
sudo ufw delete allow from 192.168.0.0/24 to any port 29811:29817 proto tcp
```

5. **UNTESTED.** Server fine: get an empty controller. Stop it (60 s grace period for
   MongoDB), move its data aside and make a new empty folder.
   Case (c): skip this step. `scripts/core-up.sh` starts it empty, because `data/db`
   is not in the snapshot.
```bash
scripts/dc.sh core/omada stop
```
```bash
mv /srv/homelab/omada/data /srv/homelab/omada/data.broken
```
```bash
mkdir /srv/homelab/omada/data
```
```bash
scripts/dc.sh core/omada up -d
```

6. Wait for the UI (2-5 min on the first start). It answers once this shows a 302:
```bash
curl -sI http://192.168.0.210:8088/
```

7. Open `https://192.168.0.210:8043/` (or the Tailscale IP) and accept the cert warning.
   In the setup wizard, step 2 of 4, choose **"Restore from backup file"** and upload
   the `.cfg`. Don't stop the container while the controller restarts.

8. Log in with the old controller admin account.

9. **Check Controller Hostname/IP.** After the M3 restore it said `100.78.185.81` (the
   Tailscale IP), and the APs can't reach that. Set it to `192.168.0.210`. Also check
   firmware auto-upgrade, so the APs don't reboot by surprise.

10. Open the AP ports again.
```bash
sudo ufw allow from 192.168.0.0/24 to any port 29810 proto udp comment 'omada discovery'
```
```bash
sudo ufw allow from 192.168.0.0/24 to any port 29811:29817 proto tcp
```

11. Check: the APs connect within a few minutes (one line per AP), and Kuma is up.
```bash
ss -tn | grep ':29814'
```
```bash
scripts/kuma-status.py omada
```

12. Check Auto Backup is still on (daily 03:00, keep 7, Settings and User Info).

13. Only when it works: delete the moved-aside data and the restore folder.
```bash
rm -r /srv/homelab/omada/data.broken
```
```bash
sudo rm -r /tmp/restore-omada
```

## f. Keep OFF the server
Names only. Keep each one in the password manager, and the critical ones also on paper.
With these, the server can be rebuilt from B2 alone (the env file comes back in the
snapshot).

- [ ] restic repository password (local and B2 repos)
- [ ] B2 keyID
- [ ] B2 application key
- [ ] Backblaze account login
- [ ] Backblaze 2FA recovery codes
- [ ] Home Assistant backup encryption key ("emergency kit")
- [ ] Samba password for the `hass` share user
- [ ] Omada controller admin login
- [ ] Omada site device account
