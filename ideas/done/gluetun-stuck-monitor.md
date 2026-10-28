# Alert when Gluetun stays unhealthy

If the VPN tunnel drops and Gluetun can't reconnect, nobody is alerted. The kill switch blocks
traffic (no leak), but downloads stop. Kuma's `qbittorrent` monitor checks the Web UI on 8083,
which Gluetun still serves while the tunnel is down, so it stays green. `qbit-watchdog.sh`
skips while Gluetun isn't healthy. Seen while planning the alert tests on 2026-10-07: a short
drop heals itself in about 45 s, but one that lasts hours would go unnoticed.

## Idea
- A Kuma HTTP monitor on Gluetun's control server, `GET http://gluetun:8000/v1/vpn/status`,
  over the `proxy` network. Down unless the body says `"status":"running"` (keyword match).
- The route is key-protected (`scripts/gluetun-auth.py`). The key stays in `.env`, **never
  in a label**: an AutoKuma label goes through compose interpolation into the container's
  labels, where anything that reads them can see it. So add the monitor by hand in Kuma, or
  give AutoKuma the key some other way. Maybe a separate `kuma` role with only that route,
  so the dashboard key can change on its own.
- Interval and retries chosen so the ~45 s self-heal doesn't page: e.g. 60 s, alert after
  5 failed checks.
- Urgent ntfy like every Kuma monitor. Test: `docker exec gluetun ip link set tun0 down`
  (done safely on 2026-10-04) shows down then up; with the retries, a short drop must not alert.
- Check first: a Kuma "Docker container" monitor through `docker-socket-proxy` may already
  treat `unhealthy` as down. If so, it needs no key at all.

## Plan
Goal: Send an urgent alert when Gluetun stays unhealthy (VPN tunnel down) for about 5 minutes. A short drop that heals itself in about 45 s must not alert.
Kind: change to core/uptime-kuma and media/qbittorrent (an AutoKuma Docker-container monitor; no key needed)

Why a Docker monitor (I checked the item the note says to check first):
- Uptime Kuma 2.5.5, server/model/monitor.js, docker type: if Health.Status is "unhealthy" it throws, so the beat is DOWN and the normal retries apply. "starting" gives PENDING. A restarting container gives PENDING. A stopped container gives DOWN. (2.0.0 used to give PENDING for unhealthy; the pinned 2.5.5 does not.)
- Gluetun has a HEALTHCHECK (`/gluetun-entrypoint healthcheck`, every 5s, 3 retries). It is `running/healthy` now.
- AutoKuma 2.0.0 supports `docker_host` entities (fields name, connection_type, path) and `docker.docker_host_name` (it is built with private-api). Monitor fields `max_retries` and `retry_interval` are supported.
- So there is no Gluetun key, no new auth role and no hand-made monitor. The note's warning about keys in labels does not apply. The note has no instructions that break the rules.
- Trade-off for Dan to accept at deploy: uptime-kuma joins the `socket-proxy` network. That gives it the same read-only Docker API access as Traefik, AutoKuma, the dashboard and Dozzle. Container inspect output includes env.
- Kuma has no Docker host yet (the docker_host table is empty). `socket-proxy` is an internal network.

Files:
- core/uptime-kuma/compose.yaml:
  - In the `uptime-kuma` service `networks:` map, add `socket-proxy: {}` after `proxy: {}` with the comment `# Docker monitors (read-only API via docker-socket-proxy)`. Leave `monitor`'s `gw_priority: 1` as it is.
  - The top-level `socket-proxy: external: true` already exists.
  - Add these labels to uptime-kuma, after the existing AutoKuma labels:
      # Docker host for Kuma "docker" monitors (AutoKuma docker_host entity)
      - kuma.socket-proxy.docker_host.name=socket-proxy
      - kuma.socket-proxy.docker_host.connection_type=tcp
      - kuma.socket-proxy.docker_host.path=tcp://docker-socket-proxy:2375
- media/qbittorrent/compose.yaml:
  - Add a `labels:` block to the `gluetun` service. It has none today, so do not add Traefik or homelab labels.
      labels:
        # Uptime Kuma (AutoKuma): down when Gluetun's healthcheck says unhealthy (tunnel down, not
        # reconnecting) or the container is stopped. Named qbittorrent-* so the qbittorrent tile shows it.
        # 60 s checks, down after 5 failures in a row, so the ~45 s self-heal doesn't page.
        - kuma.qbittorrent-vpn.docker.name=qbittorrent-vpn
        - kuma.qbittorrent-vpn.docker.docker_container=gluetun
        - kuma.qbittorrent-vpn.docker.docker_host_name=socket-proxy
        - kuma.qbittorrent-vpn.docker.interval=60
        - kuma.qbittorrent-vpn.docker.retry_interval=60
        - kuma.qbittorrent-vpn.docker.max_retries=4
  - Update the existing comment on qbittorrent's Kuma label to: `# Uptime Kuma (AutoKuma) – Web UI; Gluetun still serves it with the tunnel down (see gluetun's qbittorrent-vpn)`.
  - The ntfy-urgent notification attaches by itself through AUTOKUMA__DEFAULT_SETTINGS (`*.notification_id_list`).
- core/docker-socket-proxy/compose.yaml: comment only. Line 1 becomes `# Read-only Docker API for Traefik, AutoKuma, Uptime Kuma (docker monitors), the dashboard and Dozzle.` Make no other change.
- scripts/kuma-status.py: show the container for docker monitors.
  - Add `docker_container` to the SELECT column list and the loop unpacking.
  - Set `target = url if mtype == "http" else (docker_container if mtype == "docker" else host or url)`.
  - Read-only; nothing else changes.

New service: none (no port, no Traefik route, no .lan host).
New env vars: None

Checks the builder must run (WT=/home/dan/homelab/.worktrees/gluetun-stuck-monitor):
- scripts/dc.sh $WT/core/uptime-kuma config -q
- scripts/dc.sh $WT/media/qbittorrent config -q
- scripts/dc.sh $WT/core/docker-socket-proxy config -q
- python3 -m py_compile $WT/scripts/kuma-status.py, then `python3 $WT/scripts/kuma-status.py qbittorrent`. It must still list the qbittorrent monitor (read-only DB).
- `grep -n 'kuma\.' $WT/media/qbittorrent/compose.yaml $WT/core/uptime-kuma/compose.yaml`: the labels must be exactly as above. There must be no `${...}` and no key in any kuma label.
- Do not run up/restart. Dan deploys.

Docs:
- docs/m2-media.md: add a section after "Watchdog", titled `### VPN-down alert (Kuma qbittorrent-vpn)`. It says:
  - the `qbittorrent` monitor stays green with the tunnel down, because Gluetun still serves 8083;
  - `qbittorrent-vpn` is a Kuma Docker monitor on the `gluetun` container through docker-socket-proxy. It is down when the container is unhealthy or stopped, and pending while it is starting or restarting;
  - it checks every 60 s and goes down after 5 failures in a row, which is about 5 min, then sends an urgent ntfy alert;
  - it needs no Gluetun key;
  - it shows on the qbittorrent dashboard tile (worst status);
  - test it with `docker exec gluetun ip link set tun0 down`: at most one or two pending beats, then up, with no alert.
- docs/m1-core.md, Notes: add one bullet. uptime-kuma is also on `socket-proxy` for Docker-container monitors. Its Docker host `socket-proxy` (tcp://docker-socket-proxy:2375) is defined by AutoKuma labels on uptime-kuma. A docker monitor uses `kuma.<id>.docker.docker_container=<container>` and `docker_host_name=socket-proxy`.
- CLAUDE.md: no change.

## Manual steps
1. Deploy when no download is running. Changing gluetun's labels recreates gluetun, and qbittorrent rejoins through depends_on:
   - `scripts/dc.sh core/uptime-kuma up -d` (AutoKuma restarts with it)
   - `scripts/dc.sh media/qbittorrent up -d`
2. Check `scripts/kuma-status.py qbittorrent`. It should show `qbittorrent-vpn [docker] gluetun ... notifications=ntfy-urgent` and beats `up healthy`. If AutoKuma logs a missing docker host on the first pass, wait one sync or run `scripts/dc.sh core/uptime-kuma restart autokuma`.
3. Short-drop test: `docker exec gluetun ip link set tun0 down`. Gluetun heals in about 45 s. Kuma should show at most pending, and no phone alert should arrive. A test of a long outage is optional. Faking one means keeping Gluetun unhealthy for more than 5 min, so skip it unless wanted.
4. Accept the trade-off: Uptime Kuma now has read-only Docker API access, like the dashboard and Dozzle.
