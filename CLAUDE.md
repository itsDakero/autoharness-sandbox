# Homelab

Ubuntu 24.04 server `homelab`, user `dan`. LAN 192.168.0.210 (DHCP reservation),
Tailscale 100.78.185.81. Docker + compose plugin, Tailscale, UFW.

## Layout
- `core/` – infrastructure (docker-socket-proxy, traefik, adguard, uptime-kuma, ntfy, dashboard,
  ha-backups = SMB share for Home Assistant backups, omada = Omada controller for the APs)
- `media/` – media apps (qbittorrent + gluetun, prowlarr, radarr, sonarr, radarr-remote, sonarr-remote, jellyfin, seerr)
- `tools/` – admin/family utilities (dozzle, scrutiny, hermes, fitness, changedetection, books, wardrobe, fpl, lms,
  mealie, paperless, stirling-pdf, immich, beszel). What each does: `docs/services.md`; per-tool READMEs: `docs/README.md`.
  hermes (Discord assistant on the Mac mini's model, no port) reads docs/ and personal files read-only and writes only
  `ideas/proposed/`.
- `games/` – game helpers (leafgreen = LeafGreen Field Notes, walkthrough + Nuzlocke web app; own `CLAUDE.md`)
- `forensics/` – forensic parsers: Python scripts run by hand, one dir per parser (see `forensics/README.md`)
- `templates/` – compose template with the required labels
- `scripts/` – host scripts; **`scripts/README.md` lists every one** (usage, cron schedule, where it reports). Read it
  before adding or changing a script.
  - A new script gets one bullet in `scripts/README.md`, in its alphabetical spot, in the same change.
  - Every cron job runs through `scripts/cron-run.sh <name> <timeout> [--ok codes] <cmd>` (syslog `cron-<name>` +
    Kuma push monitor `cron-<name>`) and is two files: `scripts/cron.d/<name>.cron` +
    `core/uptime-kuma/compose.d/cron-<name>.yaml`. Checklist: `docs/new-cron-job.md`.
  - `scripts/dc.sh <dir> <args>` for compose; `scripts/check.sh` runs the local checks (syntax, lint, unit tests).
- `systemd/` – host units (backup service/timer, off-site copy, monthly restore drill, failure alerts, DOCKER-USER rule), installed by `bootstrap.sh`
- `ideas/` – queue for the build loop (`ideas/done/`, `ideas/parked/`, `ideas/rejected/`, `ideas/terminal/` = plans that
  write under `.claude/`, built by Dan with `/build-ideas <slug>` in a terminal; `ideas/waiting/` = notes with
  `Depends on: <slug>`, queued once that idea is deployed); the dashboard's admin Ideas tab adds
  new ones (a writable mount). LLM-written proposals wait in `ideas/proposed/` (the loop never reads it) until Dan's
  Approve (Proposed tab) moves them to `ideas/`; Dismiss files them in `ideas/dismissed/`. Both git-ignored. Builds happen in `.worktrees/<slug>` (git-ignored), branch `idea/<slug>`
- `docs/` – milestones, runbooks; `docs/README.md` indexes them (read it first, add a line per new doc)
- `bootstrap.sh` – all root-level host setup

## Access model
- Primary: dashboard at `http://192.168.0.210/` or `http://homelab/`; each service at
  `http://<same host>:<homelab.port>`. Family devices use the ISP router's DNS – no custom names.
- Bonus: `http://<service>.lan` via Traefik, for devices using AdGuard DNS
  (Tailscale split DNS for `lan`).
- HTTP only for now; HTTPS comes later.

## Rules
- One compose file per service: `<category>/<service>/compose.yaml`.
- Names are lowercase-kebab; service name = container name = Traefik router name.
- Every web service gets Traefik, dashboard and Uptime Kuma labels (copy `templates/compose.yaml`).
- Every web service publishes exactly one host port, recorded in `homelab.port`. Take a free port
  from the table below and add it there. Traefik publishes 80, 8080 (its dashboard)
  and 8082 (Dozzle), AdGuard 53. Published ports bypass
  UFW (reachable from LAN and tailnet) – never forward them on the router.
- Docker API only via `docker-socket-proxy` (read-only, `socket-proxy` network).
  Never mount `docker.sock` anywhere else.
- Pin image versions. No `:latest`.
- Every service gets the `logging:` json-file cap from `templates/compose.yaml` (10m x 3).
- Every service gets a healthcheck (the image's own or the template block); images without a tool are listed in docs/m1-core.md.
- App data lives in `${APPDATA_PATH}/<service>/` (`/srv/homelab`), never in the repo.
- Run compose via `scripts/dc.sh <dir> <args>` so `.env` is interpolated.
- Config via `.env` (see `.env.example`); pass containers only what they need via `environment:`.
  Never commit `.env` or secrets.
- Forensic test data/evidence lives in `/srv/homelab/forensics/`, never in the repo or git; it is excluded
  from restic so it never reaches the B2 off-site copy. Keep it that way.
- Never modify contents of `/mnt/media`. Mount it read-only unless write access is approved.
- No sudo: anything needing root goes in `bootstrap.sh`, which must stay idempotent and logged.
- Never create or use `ANTHROPIC_API_KEY`.
- Commit and push after each milestone stage.
- GPU: GTX 970 (Maxwell) on NVIDIA driver branch 580, the last that supports it. Never install a newer branch.

## Claude Code kit (`.claude/`)
Skills, agents, hooks and permissions: `docs/claude-kit.md`. Every session needs only this:
- Skills: `/add-service`, `/remove-service`, `/debug-service` (read-only), `/update-stack`, `/build-ideas`
  (loop: `docs/m5-pipeline.md`), `/scout` (M6: `docs/m6-research.md`).
- Hook `guard.py` blocks `.env` reads/edits, indirect secret dumps (`compose config` without `-q`, `docker inspect`
  without a safe `--format`, env dumps, recursive grep without `--exclude`), `sudo`, `/mnt/media` writes,
  `docker.sock` outside the proxy, `:latest`/untagged images and `ANTHROPIC_API_KEY`; it fails closed.
  `compose-check.sh` lints every `compose.yaml` edit.
- Permissions (`.claude/settings.json`): `rm -rf`, `sudo`, `.env` reads and `dc.sh` up/down/build/… on `.worktrees/*`
  are denied; up/down/stop/restart ask, and those ask rules name each core service: **a new core service must be
  added there** (`media/*`, `tools/*` are wildcards; `games/*` still needs adding).

## Dashboard labels
| Label | Value |
|---|---|
| `homelab.name` | Display name |
| `homelab.group` | Group heading |
| `homelab.icon` | dashboard-icons slug, e.g. `adguard-home` |
| `homelab.audience` | `admin` or `family` |
| `homelab.description` | One line |
| `homelab.port` | Published host port |
| `homelab.external.<id>.<field>` | A tile for something outside Docker (fields name/group/icon/audience/description; status from Kuma monitors `<id>-*`; no link). The Mac mini's are on `core/uptime-kuma`, next to its monitor |

## Ports
| Port | Service |
|---|---|
| 53 | adguard (DNS) |
| 80 | traefik (`.lan` routes, dashboard catch-all) |
| 445 | ha-backups (SMB; LAN IP only, HA Pi only; not HTTP, so no `homelab.port`/Traefik labels) |
| 3000 | adguard UI |
| 3001 | uptime-kuma |
| 5055 | seerr |
| 7878 | radarr |
| 7879 | radarr-remote |
| 8000 | dashboard |
| 8043 | omada UI, HTTPS (host network: 8843, 29810-29817, 27001 too, through UFW) |
| 8080 | traefik dashboard (entrypoint `traefik-ui`, dashboard login) |
| 8081 | ntfy |
| 8082 | dozzle (published by traefik, dashboard login) |
| 8083 | qbittorrent (published by gluetun) |
| 8084 | scrutiny |
| 8085 | leafgreen |
| 8086 | fitness |
| 8087 | changedetection |
| 8088 | omada (`homelab.port`; redirects to 8043; host network, no Traefik) |
| 8089 | beszel |
| 8090 | books |
| 8091 | wardrobe |
| 8092 | fpl |
| 8093 | lms |
| 8094 | mealie |
| 8095 | paperless |
| 8096 | jellyfin |
| 8097 | immich |
| 8098 | stirling-pdf |
| 8989 | sonarr |
| 8990 | sonarr-remote |
| 9696 | prowlarr |
