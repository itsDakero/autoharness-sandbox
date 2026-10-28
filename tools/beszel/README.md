# beszel

Beszel (`henrygd/beszel` hub + `henrygd/beszel-agent`, both pinned to 0.21.1 in `compose.yaml`) keeps history of
the server's CPU, memory, disk, disk I/O and of each container's CPU, memory and network, and alerts
on thresholds. It fills the gap between Dozzle (live logs) and Uptime Kuma (up/down). Admin tile:
http://192.168.0.210:8089 (also http://beszel.lan).

## How it is wired
- `beszel` (hub, PocketBase): UI on 8090 inside / 8089 outside, data in `/srv/homelab/beszel/data`
  (`/beszel_data`: SQLite DB, users, history, alert settings; restic backs it up).
- `beszel-agent`: no published port. It connects out to the hub over the project's own `beszel` network
  (WebSocket, `HUB_URL=http://beszel:8090`, authenticated by `KEY` + `TOKEN`). `LISTEN=45876` is the hub's SSH
  fallback, reachable on the `beszel` network only. Agent state (its fingerprint) in `/srv/homelab/beszel/agent`.
- Docker API: `DOCKER_HOST=tcp://docker-socket-proxy:2375` on the `socket-proxy` network. No `docker.sock`.
- Extra disks: `/mnt/media` and `/mnt/backup` mounted `:ro` under `/extra-filesystems/` for their usage graphs.
  `/` is the container's root, i.e. the host's system disk.

## What the agent asks the Docker API, and what the proxy allows
Read from the agent source (`agent/docker.go`, v0.21.1). Every call is a GET:

| Call | Used for | Proxy (`core/docker-socket-proxy`) |
|---|---|---|
| `/version` | engine version check at start | `VERSION=1`: allowed |
| `/info` | engine/host info | `INFO=1`: allowed |
| `/containers/json` | container list (+ health status) | `CONTAINERS=1`: allowed |
| `/containers/<id>/stats?stream=0&one-shot=1` | per-container CPU/mem/net | `CONTAINERS=1`: allowed |
| `/containers/<id>/json` | hub's container detail view (the agent drops `Config.Env` before sending it) | `CONTAINERS=1`: allowed |
| `/containers/<id>/logs?tail=…` | hub's container log viewer | `CONTAINERS=1`: allowed |

So nothing needs a proxy change (only comments were added there). `POST=0` stays: Beszel never writes to the
Docker API. Note the last two rows: anyone with a Beszel login can read container logs, as in Dozzle. Keep
Beszel to Dan's admin account (no extra users).

## First start
1. `scripts/dc.sh tools/beszel up -d`. The agent restarts until it has a key and token; the hub is fine.
2. Open http://192.168.0.210:8089 and create the admin account (the first user becomes admin).
3. **Add system**: name `homelab`, host `beszel-agent`, port `45876`. The dialog shows the hub's public key and
   a token. Put them in `.env` as `BESZEL_AGENT_KEY` and `BESZEL_AGENT_TOKEN` (the token is a secret).
4. `scripts/dc.sh tools/beszel up -d` again: the agent connects and the system turns green within a minute.
5. Alerts: Settings > Notifications takes Shoutrrr URLs. Use the Discord webhook for non-urgent alerts and the
   ntfy topic (`ntfy://...` to `http://<LAN IP>:8081`) only for urgent ones, as elsewhere. Then set thresholds per
   system (bell icon), e.g. CPU, memory, disk > 85 %, and "status down".

## Health
- Hub: `/beszel health --url http://127.0.0.1:8090` (its own command; scratch image, no curl), and the Kuma
  monitor on `http://<LAN IP>:8089/api/health`.
- Agent: `/agent health`, which fails when the agent has had no hub connection for 90 s. A missing key/token or
  a hub outage therefore shows as unhealthy.

## Gaps
- **Host network throughput.** The agent runs on a bridge network so it can reach docker-socket-proxy by name;
  in host networking it could not (the proxy is not published, and publishing it on 127.0.0.1 would hand the
  Docker API, including container env, to every host-network container such as Omada). On a bridge the agent
  sees only its own interface, so the system-level network graph is not the host's NICs. Per-container network
  (from the Docker stats API), CPU, memory, disk usage and disk I/O (`/proc` is the host's) are correct.
- **GPU.** The GTX 970 is not monitored: that needs the `beszel-agent-nvidia` image and the NVIDIA runtime.
  Not added; a later note if wanted.
- **systemd services** (backup timer etc.) are not monitored: that needs the host's D-Bus socket mounted.
  Not added.
- `/srv/homelab` is only graphed separately if it is ever its own mount (add another `/extra-filesystems/` line).

## Upgrades
Hub and agent versions move together: bump both tags in `compose.yaml` to the same release.
