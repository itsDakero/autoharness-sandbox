# M3 Omada controller – runbook

TP-Link Omada Software Controller for the 3 access points. Compose:
`core/omada/compose.yaml`. Data: `/srv/homelab/omada/` (`data/`, `logs/`).

## Design
- **Image**: `mbentley/omada-controller:6.2.14.11`, pinned. The 6.2 line, newer than
  the 6.2.10.17 backup it was restored from. The image's MongoDB 8 needs AVX (the
  i5-9400F has it).
- **Host network** (`network_mode: host`), as upstream recommends: APs find and adopt
  the controller over L2 (29810/udp broadcast). This breaks two repo rules on purpose:
  - more than one host port: host mode binds every Omada port;
  - no Traefik: host mode can't join the `proxy` network, and the UI is HTTPS-only on
    8043 with a self-signed cert (8088 just redirects to `https://<host>:8043/`).
- **Ports go through UFW**. Docker-published ports bypass UFW, host-mode ports don't.
  So the LAN needs explicit rules (below). The tailnet already has every port
  (`ufw allow in on tailscale0`).
- **Dashboard**: `homelab.port=8088`, admin tile under Infrastructure. The link
  `http://<host>:8088/` redirects to `https://<host>:8043/` (browser cert warning
  until HTTPS comes).
- **Kuma**: `https://${LAN_IP}:8043/`, `ignore_tls=true` (self-signed).
- **Owner**: `PUID`/`PGID` from the env file (1000), so owners match
  `keep/owners.txt`. The image default is 508.
- **Shutdown**: `stop_grace_period: 60s`. MongoDB gets corrupted if it is killed early.
- **MongoDB** listens on `127.0.0.1:27217` only. Check:
```bash
ss -tln | grep ':27217'
```

## Ports and UFW
| Port | Proto | Purpose | UFW from LAN |
|---|---|---|---|
| 8043 | tcp | UI (HTTPS) + AP firmware upgrades | allow 192.168.0.0/24 |
| 8088 | tcp | UI (HTTP, redirects to 8043), dashboard link | allow 192.168.0.0/24 |
| 8043 | tcp | Uptime Kuma check (container → host) | allow 172.20.0.0/16 |
| 29810 | udp | device discovery | allow 192.168.0.0/24 |
| 29811-29817 | tcp | device manage, adopt, upgrade, rtty | allow 192.168.0.0/24 |
| 27001 | udp | Omada phone app discovery | closed (not used) |
| 8843 | tcp | guest captive portal (HTTPS) | closed (not used) |
| 8044 | tcp | ES switch upgrades | closed (no ES devices) |
| 27217 | tcp | embedded MongoDB, 127.0.0.1 only | closed |

`bootstrap.sh` (UFW section) holds the same rules, so a rebuild gets them back.

**Kuma rule**: Uptime Kuma's checks leave via the `monitor` network (172.20.0.0/16).
A container reaching a host-mode port goes through UFW's INPUT chain, so it needs its
own rule. After a rebuild the subnet can differ. Check it:
```bash
docker network inspect monitor
```

Rules as they stand:
```bash
sudo ufw status numbered
```

Rollback deletes, one per rule:
```bash
sudo ufw delete allow from 192.168.0.0/24 to any port 8043 proto tcp
```
```bash
sudo ufw delete allow from 192.168.0.0/24 to any port 8088 proto tcp
```
```bash
sudo ufw delete allow from 172.20.0.0/16 to any port 8043 proto tcp
```
```bash
sudo ufw delete allow from 192.168.0.0/24 to any port 29810 proto udp
```
```bash
sudo ufw delete allow from 192.168.0.0/24 to any port 29811:29817 proto tcp
```

## How the APs find the controller
- Adopted APs keep the controller's IP and connect to `192.168.0.210:29814` (v5+
  firmware). The new controller has the same IP and ports, so after a restore they come
  back with no change on the APs. No re-adoption, no factory reset.
- While the controller is unreachable, the APs keep broadcasting their last SSID
  config. Wi-Fi keeps working; only controller features wait.
- **Ordering**: keep the AP ports (29810-29817) closed in UFW until the restore is done
  and checked. The APs then never see an empty controller ("Managed by others").
- Check the APs are connected (one line per AP):
```bash
ss -tn | grep ':29814'
```

What can go wrong:
- An empty controller sees the APs first: they show "Managed by others" and need the
  old site device account to adopt. The UFW ordering avoids this.
- Restored settings differ from what the APs run: the controller re-provisions them
  (a short Wi-Fi blip per AP).
- Firmware auto-upgrade in the restored settings can reboot the APs. Check it before
  opening the AP ports.
- **Controller Hostname/IP** points somewhere the APs can't reach (see the lesson below).
- Another Omada controller still running elsewhere fights for the APs. Shut it down.
- Missing UFW rule: APs stay "Disconnected". Wi-Fi is fine; fix the rule.

## The restore (2026-10-07, M3 stage B)
Restored from `/srv/homelab/keep/omada_backup_6.2.10.17_2026-10-02_22-33-10.cfg` into
the empty 6.2.14.11 controller.

1. Stage A left the controller running and empty. UFW allowed only 8043/8088 from the
   LAN and the Kuma rule. The AP ports were closed.
2. In the setup wizard, step 2 of 4, chose **"Restore from backup file"** and uploaded
   the `.cfg`. The controller restarted with the old site, settings and the 3 APs.
3. Logged in with the old controller admin account (password manager).
4. **Lesson**: after the restore, **Controller Hostname/IP said `100.78.185.81`**
   (the Tailscale IP), not `192.168.0.210`. The APs are not on the tailnet, so they
   would have been told to use an address they can't reach. Set it to `192.168.0.210`
   **before** opening the AP ports. Check it after every restore.
5. Opened 29810/udp and 29811-29817/tcp from 192.168.0.0/24.
6. All 3 APs connected on 29814 (`ss -tn | grep ':29814'` shows 3 established links).

## Auto-backup
Global view > Settings > Maintenance > Backup > Auto Backup:
- enabled, **daily at 03:00** (restic runs at 04:00)
- **keep 7**
- **Settings** and **User Info** ticked

Files land in `/opt/tplink/EAPController/data/autobackup` =
`/srv/homelab/omada/data/autobackup/`, which restic backs up. The live MongoDB
(`/srv/homelab/omada/data/db`) is excluded in `scripts/backup-excludes.txt`: a copy
taken while it runs can be corrupt. Logs are excluded by `/srv/homelab/*/logs`.
Omada is not in `backup.sh`'s pause list: restic only needs the finished `.cfg` files.

Check the newest backups:
```bash
ls -lt /srv/homelab/omada/data/autobackup | head
```

Restore: `docs/restore.md`, section e.

## Upgrades
- **Back up first**: Backup > Backup Now in the UI, and copy the `.cfg` somewhere safe
  (e.g. `/srv/homelab/keep/`).
- **No downgrades.** An Omada controller can't go back to an older version: a newer
  database breaks an older controller. Read the release notes before bumping.
- Stop it cleanly. `stop_grace_period: 60s` in the compose file gives MongoDB its
  60 s. Don't `docker kill` it.
- Bump the pinned tag in `core/omada/compose.yaml`, then:
```bash
scripts/dc.sh core/omada up -d
```
- **6.3 later**: `6.3.0.45` exists but is a new minor line. Stay on 6.2.x until it
  has settled, then move to 6.3 as its own step (backup first).
