# Homelab

Ubuntu 24.04 server `homelab`, user `dan`. LAN 192.168.0.210 (DHCP reservation),
Tailscale 100.78.185.81. Docker + compose plugin, Tailscale, UFW.

## Layout
- `core/` – infrastructure (docker-socket-proxy, traefik, adguard, uptime-kuma, ntfy, dashboard,
  ha-backups = SMB share for Home Assistant backups, omada = Omada controller for the APs)
- `media/` – media apps (qbittorrent + gluetun, prowlarr, radarr, sonarr, radarr-remote, sonarr-remote, jellyfin, seerr)
- `tools/` – admin utilities (dozzle, scrutiny = SMART disk health, hermes = Discord assistant on the Mac mini's
  model, M6; no port; reads the dashboard's status + personal files and docs/ (read-only), writes only `ideas/proposed/`,
  fitness = Garmin sync + morning check-in + FiiT log + training plan (goal, block, today's session), health data, admin; see `tools/fitness/README.md`,
  changedetection = price/restock watches, books = reading tracker (Goodreads CSV import, Open Library covers), admin; see `tools/books/README.md`,
  wardrobe = clothes catalogue + outfit generator + gap analysis, Mac mini vision tagging, admin; see `tools/wardrobe/README.md`,
  fpl = FPL collector + projections/squad/solver page + team goals and player points models, admin; see `tools/fpl/README.md`,
  lms = Last Man Standing picker (Odds API), admin; see `tools/lms/README.md`,
  mealie = recipes + meal plans + shopping lists, family; see `tools/mealie/README.md`,
  paperless = Paperless-ngx documents + OCR (+ its own Redis), admin; see `tools/paperless/README.md`,
  stirling-pdf = PDF merge/split/convert/OCR in the browser, family; see `tools/stirling-pdf/README.md`,
  immich = photo/video backup from phones (+ its own ML on CPU, Postgres, Valkey), family; see `tools/immich/README.md`,
  beszel = host + per-container resource history and alerts (hub + agent, Docker API via the socket proxy), admin; see `tools/beszel/README.md`)
- `games/` – game helpers (leafgreen = LeafGreen Field Notes, walkthrough + Nuzlocke web app; own `CLAUDE.md`)
- `forensics/` – forensic parsers: Python scripts run by hand, one dir per parser (see `forensics/README.md`)
- `templates/` – compose template with the required labels
- `scripts/` – one script per line, alphabetical (new ones go in their spot; new cron jobs = `scripts/cron.d/<name>.cron` + `core/uptime-kuma/compose.d/cron-<name>.yaml`)
  - `arr-import.py` (Library Import)
  - `arr-missing-search.py` (cron, weekly: re-search missing monitored titles in all four arr apps, capped; Discord summary)
  - `arr-organise.py`
  - `arr-rename.py` (preview/apply file renames)
  - `arr-setup.py` (arr apps + Prowlarr wiring)
  - `backup.sh` + `backup-excludes.txt` (nightly restic to `/mnt/backup/restic`, then `offsite` copy to B2; root via systemd; `test-alert`)
  - `card-prices.py` (cron daily: LeafGreen card watchlist price history; Discord on a drop; `--dry-run`)
  - `cert-expiry-check.sh` (cron daily: ntfy when a TLS cert nears expiry, today Omada's 8043; warn 30 days weekly, crit 7 days daily)
  - `check.sh` (by hand + CI `.github/workflows/check.yml`: bash -n, py_compile, shellcheck (skipped if missing), compose-lint, unit tests; pass/fail summary, exit 1 on any failure)
  - `compose-lint.py [--root DIR] [FILE ...]` (read-only: every `<category>/<service>/compose.yaml` against the Rules: pinned image, logging cap + healthcheck (m1-core exceptions), web labels, unique + tabled `homelab.port`, docker.sock, `/mnt/media` `:ro` unless commented "approved"; exit 1 on findings, 2 usage)
  - `core-up.sh`
  - `cron-run.sh <name> <timeout> [--ok codes] <cmd>` (wraps every cron job: syslog `cron-<name>` and a Kuma push monitor `cron-<name>`)
  - `dashboard-passwd.py` (hash for the dashboard's /admin login; user runs it, pastes into `.env`)
  - `dc.sh` (docker compose with the repo `.env`)
  - `deploy-idea.sh [<slug>|drop <slug>|reject <slug>]` (Dan merges + starts a reviewed build, or rejects it)
  - `discord.sh "<msg>"|test` (Discord feed: non-urgent; ntfy stays for urgent alerts)
  - `disk-space-check.sh` (cron: ntfy when a disk fills; media 70%, system/backup 85%, any 95%)
  - `docker-user-rules.sh` (root: DOCKER-USER rule, SMB from the HA Pi only)
  - `fitness-weekly.sh` (cron Sundays 19:00: the fitness app's weekly written summary to Discord; Mac mini model)
  - `fpl-job.sh <job> <threshold> <secs>` (cron: one FPL collector pull run inside the fpl container; Discord once after N failures in a row)
  - `fpl-web-job.sh <solve|deadline|teams|players>` (cron: daily solver run 06:45, deadline Discord line 18:00, hourly team model :25, hourly player model :40)
  - `gluetun-auth.py` (Gluetun control-server API-key role for the dashboard)
  - `ha-backup-check.sh` (cron: ntfy if HA backups are older than 9 days)
  - `idea-actions.py` (cron: runs the dashboard's Parked/Deploy tab buttons: answer, requeue, deploy, reject; auto-deploys approved Risk 1 builds, see m5)
  - `idea.sh` (the build loop's git steps; `kit-paths`/`terminal` for `.claude/` plans, `unblocked <slug>` = notes waiting on it, `research-ok`; `scout-due`/`scout-done`/`scout-topic-done` for the M6 scout; held topics in `ideas/proposed/_topics.md`)
  - `image-check.py` (cron Mondays: Discord digest of newer image tags; ntfy on security releases; `--propose`: a Risk 1 note in ideas/proposed/ per patch bump)
  - `image-prune.sh [--dry-run|--apply]` (old `homelab/*` tags beyond the newest two + build cache >7d; lists other unused images for Dan; deploy-idea runs it after a build)
  - `install-cron.sh` (entries from `scripts/cron.d/<name>.cron`; `--check`: daily Discord on drift; deploy-idea.sh reinstalls on drift)
  - `jellyfin-library-check.py [--dry-run]` (cron daily 09:30: Discord when a Jellyfin library is missing, empty or its scan failed/stalled)
  - `jellyfin-setup.py` (libraries + NVENC; `plugins` = Intro Skipper)
  - `kuma-status.py`
  - `lms-job.sh <odds|alerts|results>` (cron: LMS odds, Discord nudges, results)
  - `loop-alert.sh` (Claude Code hook: Discord line when the loop waits on a prompt, auto mode denies a call or a turn stops on an API error; only with `HOMELAB_LOOP=1`)
  - `loop.sh` (starts/attaches the loop's tmux session `ideas` with HOMELAB_LOOP=1 and a 150K auto-compact window)
  - `media-cleanup.py` (plan; user applies)
  - `model-bench.py` (by hand: Ollama model bench on the Mac mini, table into `docs/mac-mini.md`; `--memory`: memory budget table)
  - `morning-brief.py [test|--print]` (cron 07:00: one Discord brief from the dashboard's agent feed: outfit when the wardrobe toggle is on, readiness/illness, yesterday's activity, deals, services not up, items waiting for Dan; `MORNING_BRIEF_ENABLED=0` turns it off)
  - `omada-ap-check.py [--dry-run]` (cron hourly :50: Discord when fewer than 3 APs hold a link to Omada on 29814, via `ss`; daily repeat, recovery line)
  - `ops-actions.py [--dry-run]` (cron every 5 min: restart registered non-core containers unhealthy 2 checks running, capped 1/h + 3/day per service, breaker >3/h writes PAUSE; see docs/ops-actions.md)
  - `qbit-setup.py` (qBittorrent login + settings)
  - `qbit-watchdog.sh` (cron, via `install-cron.sh`)
  - `restore-drill.sh [<folder>]` (root via systemd, monthly on the 1st: `restic restore --verify` of one service's appdata (rotates by month) into a temp dir, file/byte check, fails if the snapshot is >48h old; Discord line, ntfy on failure; `test-alert`)
  - `scrutiny-check.sh` (cron: ntfy on a disk problem in Scrutiny; holds the sda 187/188 exception)
  - `seerr-route.py` (cron: remote users' requests → remote pair)
  - `seerr-setup.py` (Seerr servers, users, permissions)
  - `secret-scan.sh install|history|<dir> <range>` (gitleaks v8.30.1 in ~/.local/bin; idea.sh/deploy-idea.sh scan before every push, a hit or a missing binary = no push)
  - `storage-cleanup.py report [--print]` (cron, Sundays: read-only dry-run list of watched media to clean, ntfy)
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
- Skills (user-invoked): `/add-service <idea>`, `/remove-service <name>`, `/debug-service <name>`
  (read-only), `/update-stack [name]`, `/build-ideas` (background loop, run as `/loop /build-ideas`: subagents
  `idea-planner` (Opus), `idea-researcher` (Sonnet, when the planner says RESEARCH), `idea-builder` (Sonnet),
  `idea-reviewer` (Opus) in `.claude/agents/`; reviewed builds wait on `idea/<slug>` branches for
  `scripts/deploy-idea.sh`; plans that write under `.claude/` go to `ideas/terminal/` instead (protected path:
  a background builder stalls on the prompt), and Dan builds them with `/build-ideas <slug>`; see `docs/m5-pipeline.md`), `/scout [topic]` (M6:
  `idea-scout` (Opus) sweeps AI tech, a homelab audit and GitHub, writes 3 proposals to `ideas/proposed/`; the
  loop runs it on Fridays; see `docs/m6-research.md`).
- `scripts/kuma-status.py [name]`: Kuma monitors, heartbeats and attached notifications, read-only from the DB.
- Hook `guard.py` (PreToolUse) blocks: reading/editing `.env`; commands that print secrets indirectly
  (`compose config` without `-q`, `docker inspect` without a safe `--format`, container env dumps,
  `/proc/*/environ`, recursive grep without `--exclude`); `sudo`; writes to `/mnt/media`; `docker.sock` outside
  the socket proxy; `:latest`/untagged images; `ANTHROPIC_API_KEY`. A media mount without `:ro` asks first.
  Fails closed (`onFailure: block`, 10 s timeout): a guard crash or timeout blocks the call.
  Tests: `python3 -m unittest discover -s scripts/tests` (`test_guard.py`, blocked/allowed/ask cases).
- Hooks `Notification` (permission_prompt), `PermissionDenied` and `StopFailure` run `scripts/loop-alert.sh`.
- Hook `compose-check.sh` (PostToolUse) runs `config -q` after every `compose.yaml` edit and re-checks the
  whole file (pinned images, docker.sock), then `compose-lint.py` on it (its findings + repo-wide port-unique;
  skipped with a warning if PyYAML or the script is missing). Read-write media mounts are approved via the guard's ask.
- Permissions: git, `dc.sh` config/ps/logs and homelab `curl` run freely; up/down/stop/restart ask;
  `rm -rf`, `sudo`, reading `.env` and `dc.sh` up/down/build/… on `.worktrees/*` are denied. Exception: `dc.sh core/dashboard` build/up/restart run
  freely. Ask rules beat allow rules and can't say "except", so the up/down/stop/restart ask rules name
  each other core service (incl. `core/omada`): **a new core service must be added there**
  (`media/*`, `tools/*` are wildcards; `games/*` still needs adding).

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
