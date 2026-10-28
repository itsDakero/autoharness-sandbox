# Cap Docker Container Logs

Value: 4   (prevents disk bloat, helps identify noisy containers)
Effort: 2  (update Compose templates or Traefik config)
Risk: 2    (standard logging config, easy to revert)
Source: hermes 2026-10-15

## Problem
Docker containers accumulate logs without bounds, potentially filling disk space. No current limit on log size/retention visible in status.

## Proposal
Add `ulimits`, `max_size`, and `log_opts` to each service's logging config in compose templates:
```
logging:
  driver: "json-file"
  options:
    max-size: "10m"   # 10MB per file
    max-file: "3"     # 3 files = 30MB total rotation
```

Apply to all containers (Traefik, Jellyfin, radarr/sonarr, etc.).

## Rough plan
1. Create/update each service compose template with logging options
2. Adjust `max_size` per service: keep small for dev/test, larger for long-running services
3. Document as a standard in homelab infra notes
4. Roll out and monitor disk usage for 1-2 weeks

_Approved on the dashboard, 2026-10-15._

## Plan
Goal: Cap every container's json-file logs at 10m x 3 files with a per-service `logging:` block in compose.
Kind: change to compose files (all services except adguard and omada) + template + docs
Decisions (they change what the note asked for):
- Put the cap in compose, not in `/etc/docker/daemon.json`. Changing daemon.json means a bootstrap edit
  and a docker restart (every container, DNS included), and the default only applies to newly created
  containers anyway.
- Same cap everywhere. Drop the note's per-service sizes ("dev/test" doesn't exist here). Drop `ulimits`:
  it has nothing to do with logs.
- Leave out adguard and omada (always-manual list). Dan adds the block to those by hand if he wants it
  (Manual steps).
- The note's step 4, "monitor disk usage for 1-2 weeks", is not part of this build.
Files:
- Add this block, verbatim, to every service in the files below. Put it right after `restart:` (or
  after `container_name:` if there is no `restart:`):
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
  Services, one block each:
  - core/dashboard/compose.yaml (dashboard)
  - core/docker-socket-proxy/compose.yaml (docker-socket-proxy)
  - core/ha-backups/compose.yaml (ha-backups)
  - core/ntfy/compose.yaml (ntfy)
  - core/traefik/compose.yaml (traefik)
  - core/uptime-kuma/compose.yaml (uptime-kuma AND autokuma)
  - games/leafgreen/compose.yaml (leafgreen)
  - media/jellyfin, prowlarr, radarr, radarr-remote, seerr, sonarr, sonarr-remote compose.yaml (one each)
  - media/qbittorrent/compose.yaml (gluetun AND qbittorrent)
  - tools/dozzle, tools/hermes, tools/scrutiny compose.yaml (one each)
  Change nothing else in these files: no YAML anchors, no reformatting.
- templates/compose.yaml: add the same block after `restart:`, with comment
  `# cap container logs (CLAUDE.md rule)`.
- Do NOT touch core/adguard/compose.yaml or core/omada/compose.yaml.
New service: None
New env vars: None
Checks the builder must run:
- `scripts/dc.sh /home/dan/homelab/.worktrees/docker-log-limit/<dir> config -q` for every edited dir
  (17 dirs) and for templates/ if dc.sh accepts it.
- `git diff --stat`: exactly 17 compose files + template + CLAUDE.md (+ docs/m1-core.md), with
  adguard/omada absent.
- `grep -c 'max-file: "3"'` per file: matches its service count (2 for uptime-kuma and qbittorrent,
  1 elsewhere).
Review focus:
- a service in a multi-service file missed (autokuma, gluetun) -> its logs stay unbounded; every
  `services:` entry has the block.
- block placed under the wrong key or mis-indented (e.g. inside `labels:` or `environment:`) -> config -q
  fails or silently ignores it; it must be a direct child of the service.
- adguard/omada edited -> forbidden (always-manual); diff must not touch them.
- deploy recreates traefik, gluetun and the socket proxy -> expected one-time short blip; the runbook
  says so and says to deploy from a terminal (several dirs are SENSITIVE in deploy-idea.sh).
- Dozzle and scripts that read `docker logs` -> still work after rotation (only old lines drop); no
  script change needed.
Docs:
- CLAUDE.md Rules: add the line "Every service gets the `logging:` json-file cap from
  `templates/compose.yaml` (10m x 3)."
- docs/m1-core.md Notes: one short paragraph saying:
  - the cap is per service in compose;
  - it takes effect when a container is recreated (`dc.sh <dir> up -d`), and old oversize logs are
    dropped then;
  - adguard and omada are left to Dan.

## Manual steps
- Deploy from a terminal: `scripts/deploy-idea.sh docker-log-limit`. It touches the sensitive
  core/traefik, docker-socket-proxy and ha-backups. It recreates every changed service, so expect a
  short blip on the dashboard, `.lan` routes, the VPN and qBittorrent.
- Optional: add the same block to core/adguard and core/omada yourself, then
  `scripts/dc.sh core/adguard up -d` and `scripts/dc.sh core/omada up -d` at a quiet moment (DNS drops
  briefly).
- Check: `docker inspect --format '{{.HostConfig.LogConfig}}' <name>` shows `max-size:10m max-file:3`.

## Review notes
1. The cap only takes effect when a container is recreated. Until `scripts/deploy-idea.sh docker-log-limit` has run, nothing changes on the host. After deploying, check with `docker inspect --format '{{.HostConfig.LogConfig}}' gluetun` and the same for autokuma.
2. adguard and omada still have no cap. The plan leaves them to Dan on purpose, and they are listed under Manual steps.
3. The CLAUDE.md rule says "Every service gets…", but adguard and omada don't have the block yet. A small "(adguard/omada: manual)" note on that line would avoid confusing future reviewers. This is optional.

## Declined to judge
- Size of the 10m x 3 cap (for example, whether jellyfin or gluetun troubleshooting needs more history): the plan sets one cap for every service.
- A daemon.json default instead of per-service blocks: the plan rejected it on purpose.
- Watching disk usage for 1-2 weeks after rollout: the plan puts it out of scope.
