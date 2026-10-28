# Scripts

One bullet per script, in alphabetical order. A new script gets its bullet in its alphabetical spot in the
same change, with its usage summary and exit codes. Cron jobs start with `(cron …: what it does; where it reports)`.

Rules for new scripts and cron jobs are in `CLAUDE.md` (Layout, `scripts/`); the full cron checklist is
`docs/new-cron-job.md`.

- `arr-import.py` (Library Import)
- `arr-missing-search.py` (cron, weekly: re-search missing monitored titles in all four arr apps, capped; Discord summary)
- `arr-organise.py`
- `arr-rename.py` (preview/apply file renames)
- `arr-setup.py` (arr apps + Prowlarr wiring)
- `backup.sh` + `backup-excludes.txt` (nightly restic to `/mnt/backup/restic`, then `offsite` copy to B2; root via systemd; `test-alert`)
- `card-prices.py` (cron daily: LeafGreen card watchlist price history; Discord on a drop; `--dry-run`)
- `cert-expiry-check.sh` (cron daily: ntfy when a TLS cert nears expiry, today Omada's 8043; warn 30 days weekly, crit 7 days daily)
- `check.sh` (by hand + CI `.github/workflows/check.yml`: bash -n, py_compile, shellcheck (skipped if missing), compose-lint, service-catalog --check, unit tests; pass/fail summary, exit 1 on any failure)
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
- `secret-scan.sh install|history|<dir> <range>` (gitleaks v8.30.1 in ~/.local/bin; idea.sh/deploy-idea.sh scan before every push, a hit or a missing binary = no push)
- `seerr-route.py` (cron: remote users' requests → remote pair)
- `seerr-setup.py` (Seerr servers, users, permissions)
- `service-catalog.py [--check]` (writes `docs/services.md` from the `homelab.*` labels; `--check` in check.sh: exit 1 if it is stale or the Ports table disagrees with `homelab.port`, 2 usage)
- `storage-cleanup.py report [--print]` (cron, Sundays: read-only dry-run list of watched media to clean, ntfy)
