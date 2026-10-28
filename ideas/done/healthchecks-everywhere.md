# Healthchecks on every web service

Value: 3   (Docker only knows "running", not "working"; the ops runner needs a real signal)
Effort: 2  (one `healthcheck:` block per compose file, checked one at a time)
Risk: 1    (no behaviour change: a healthcheck only sets a status)
Score: 12
Source: claude 2026-10-25 (reports/Homelab autonomy and assistant gaps.md, roadmap #2; scout item)

## Problem
Only `core/ha-backups` and `tools/dozzle` have a `healthcheck:`. A hung container still shows as running, so
nothing can tell "up but broken" apart, and Hermes has no healthcheck at all (a scout runner-up).

## Proposal
- Add a `healthcheck:` to every web service in `core/`, `media/`, `tools/`, `games/` that lacks one, using a
  tool the image already contains (curl/wget/python/the app's own CLI); check per image, never install
  packages. Endpoint = the app's health/ping URL where one exists, else its port.
- Conservative timings: interval 60s, timeout 10s, retries 3, start_period long enough for the slowest app
  (Jellyfin, Omada).
- Hermes: a check that proves the process is alive (no Discord/Ollama call).
- Show `unhealthy` on the dashboard if it isn't shown already (it reads status via the socket proxy).
- Copy the block into `templates/compose.yaml` so new services get one.

## Notes
- Images where no tool exists: leave them out and list them in the note, don't add sidecars.
- Changing a compose file recreates the container on the next `up`; deploy outside media hours.

## Plan
Goal: Every long-running container that has no healthcheck gets one, using a tool already in its image, and the dashboard shows an unhealthy container as down.
Kind: change to existing compose files + dashboard
Already healthy from their image or compose (leave them alone and don't override): dashboard, omada, uptime-kuma, jellyfin, gluetun, fitness, wardrobe, leafgreen, dozzle, ha-backups (checked with `dc.sh ps`, which shows "(healthy)"). Skipped: autokuma (not a web service, no port).
Standard block (exec form or CMD-SHELL): interval 60s, timeout 10s, retries 3, start_period 120s.
Files:
- core/adguard/compose.yaml: `CMD-SHELL`, `wget -q --spider http://127.0.0.1:3000/ || exit 1`
- core/ntfy/compose.yaml: `CMD-SHELL`, `wget -q --tries=1 -O - http://127.0.0.1:80/v1/health | grep -q '"healthy":true'`
- core/traefik/compose.yaml: `CMD-SHELL`, `wget -q --spider http://127.0.0.1:8090/ping || exit 1`
- core/docker-socket-proxy/compose.yaml: `CMD-SHELL`, `wget -q -O - http://127.0.0.1:2375/_ping | grep -q OK`
- media/radarr, media/radarr-remote/compose.yaml: `curl -fsS -o /dev/null http://127.0.0.1:7878/ping`
- media/sonarr, media/sonarr-remote/compose.yaml: the same on port 8989
- media/prowlarr/compose.yaml: the same on port 9696
- media/qbittorrent/compose.yaml: qbittorrent service only (it shares gluetun's network): `curl -fsS -o /dev/null http://127.0.0.1:8083/`. Don't touch gluetun or its depends_on.
- media/seerr/compose.yaml: `wget -q -O /dev/null http://127.0.0.1:5055/api/v1/status`
- tools/changedetection/compose.yaml: `python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/', timeout=8)"`
- tools/jelu/compose.yaml: the first that works of curl / wget on http://127.0.0.1:11111/, else `bash -c 'exec 3<>/dev/tcp/127.0.0.1/11111'` (port only). start_period 180s (JVM).
- tools/scrutiny/compose.yaml: `curl -fsS -o /dev/null http://127.0.0.1:8080/api/health`, with the same fallback order as jelu
- tools/hermes/compose.yaml: a process-alive check only, no Discord or Ollama call: `python3 -c` that scans /proc/*/cmdline and exits 0 if any process has "gateway" in its cmdline, else 1.
- core/dashboard/app/main.py: in to_service, a running container whose `Status` string (from the Docker list API) contains "(unhealthy)" gets status "down". "(health: starting)" and no healthcheck work as before (Kuma).
- core/dashboard/compose.yaml: image tag homelab/dashboard:0.15.0 -> 0.16.0
- templates/compose.yaml: add the standard block after volumes, with a comment: "use a tool the image already has (curl/wget/python/app CLI), health URL else port; omit if the image has its own HEALTHCHECK; never install packages"
- CLAUDE.md: one Rules bullet: "Every service gets a healthcheck (the image's own or the template block); images without a tool are listed in docs/m1-core.md."
- docs/m1-core.md: a short "Healthchecks" section: the convention, the table above (service -> command), the skipped containers and why, and the dashboard's unhealthy -> down.
Tool check per image: before writing each block, the builder confirms the tool exists in the running container with a read-only `docker exec <name> sh -c 'command -v curl wget python3 bash'`. If that call is denied or would prompt, use the commands above as given and record "unverified" next to that service in the m1-core.md table. If a tool is missing, use the next one in the fallback order. If none works, leave the healthcheck out and list the service in the doc.
New service: None
New env vars: None
Checks the builder must run:
- `scripts/dc.sh <worktree>/<dir> config -q` for every changed compose file, templates/compose.yaml included
- `python3 -m py_compile core/dashboard/app/main.py`
- `grep -c healthcheck` on each changed file (expect 1, or 2 for media/qbittorrent counting the comment)
Review focus:
- healthcheck tool missing from the image -> the container goes unhealthy, then the dashboard shows it down forever. Each command must use a tool confirmed or listed as above, never an installed one.
- the app needs a login at the probed URL -> use the unauthenticated endpoint (/ping, /v1/health, /api/v1/status, /api/health) or plain `/`, which returns the login page with 200.
- slow start (jelu JVM, arr DB migration after an upgrade) -> start_period covers it, so the tile doesn't flash down after a deploy.
- Docker `Status` is missing or in an odd format -> to_service treats it as not unhealthy (uses `.get("Status", "")`) and never raises.
- qbittorrent's check must not change the gluetun depends_on/restart logic, and hermes's check must not call Discord or the model.
Docs: CLAUDE.md Rules (one bullet); docs/m1-core.md "Healthchecks" section. No port table change.

## Manual steps
- Deploy outside media hours: each changed stack is recreated on `up` (arr apps, qbittorrent, seerr, traefik, adguard (DNS blips briefly), ntfy, socket-proxy, hermes, jelu, scrutiny, changedetection), and the dashboard is rebuilt.
- About 3 minutes after the deploy, run `scripts/dc.sh <dir> ps` per stack. Every changed service should show "(healthy)". Any "(unhealthy)" means that block's tool or URL is wrong: fix it or remove that block.
- Note: nothing in the idea note asks to break the repo rules.

## Review notes
1. /home/dan/homelab/.worktrees/healthchecks-everywhere/tools/hermes/compose.yaml:11: the check is stricter than the plan. It needs both `hermes_cli` and `gateway\0run` in a process's cmdline, where the plan only asked for "gateway". This is justified: a bare "gateway" also matches the s6 `rc.init ... gateway run` line. I checked the host process list and the live gateway is `/opt/hermes/.venv/bin/python ... from hermes_cli.main import main ... gateway run --replace`, so the check matches it. If a process exits between the glob and the `open()`, the check can raise and fail once. With retries 3 that does no harm.
2. With interval 60s, Docker's first probe runs at about 60s, so every changed container shows "(health: starting)" for about a minute. deploy-idea.sh's 2-minute wait per service covers this. A deploy of all 15 stacks will feel slower but won't fail.
3. AdGuard, traefik and docker-socket-proxy are on deploy-idea.sh's SENSITIVE list, and the note has manual steps. So this build won't auto-deploy as a Risk 1 build: Dan confirms it, as the plan intends. adguard is listed in the manual steps (DNS blip).
4. I couldn't read the filesystems of adguard, docker-socket-proxy, changedetection, jelu and scrutiny directly. For those I checked the image history instead:
   - adguard and socket-proxy are Alpine minirootfs, so busybox `wget` is there.
   - changedetection is a python:3 base.
   - jelu's Temurin base installs curl and wget.
   - the scrutiny omnibus image installs curl.
   I could read the filesystems of the arr apps, qbittorrent, ntfy, traefik, seerr and hermes, and each has the tool its check uses.

## Declined to judge
- ops runner or alerting on Docker health: the plan only asks for the status signal and the dashboard tile. The runner is a separate queued idea.
- Logging cap / healthcheck for omada: omada is "already healthy" per the plan and an always-manual area. It was left untouched.
