# Cron dead-man's switch: alert when a cron job stops running or fails

Value: 4   (12 cron jobs fail silently today: output is discarded and there is no mail)
Effort: 2  (a small wrapper + one Kuma push monitor per job)
Risk: 1    (no service changes; adds monitors and a wrapper)
Score: 16
Source: claude 2026-10-25 (reports/Homelab autonomy and assistant gaps.md, roadmap #1)

## Problem
`scripts/install-cron.sh` installs 12 jobs (idea-actions, seerr-route, ha-backup-check, scrutiny-check,
disk-space-check, arr-missing-search, storage-cleanup, image-check, card-prices, the cron self-check,
wardrobe-daily, fitness-weekly). If one crashes, hangs or never runs (crontab lost, script error), nothing
tells Dan. The scout already suggested a `cron-run.sh` wrapper; this is that, plus the alerting.

## Proposal
- `scripts/cron-run.sh <name> <cmd...>`: runs the job with a timeout, logs to syslog (tag `cron-<name>`), and
  on exit 0 pings an Uptime Kuma **push monitor** for that job; on failure pings it with `status=down` and
  the last log line (no secrets, no env values).
- One Kuma push monitor per job (`cron-<name>`), interval = job period + grace (every-minute jobs: 10 min;
  daily: 26 h; weekly: 8 d). Kuma's existing notifications do the alerting. Push tokens live in the env
  file, never in git.
- `install-cron.sh` ENTRIES wrap each job with `cron-run.sh`; `--check` keeps working.
- Every-minute jobs (idea-actions, seerr-route): ping at most every 5 min so Kuma isn't flooded.

## Notes
- No new service. If Kuma is down, the wrapper logs and carries on (never blocks the job).
- Update CLAUDE.md's scripts list and `docs/m4-backups.md` (or the doc that lists the cron jobs).

## Plan
Goal: Wrap every homelab cron job in `scripts/cron-run.sh`. The wrapper logs the job's output to syslog and pushes an Uptime Kuma push monitor per job (up, or down with a reason). Kuma's existing ntfy-urgent notification then alerts when a job fails, hangs or stops running.
Kind: script/cron (plus AutoKuma labels on core/uptime-kuma)
Files:
- scripts/cron-run.sh: new (spec below), chmod +x
- scripts/install-cron.sh: wrap every ENTRIES line; fix the name extraction in `check()`
- core/uptime-kuma/compose.yaml: 13 AutoKuma push monitors and one external dashboard tile, as labels on the uptime-kuma service
- .env.example: add KUMA_CRON_PUSH_SECRET under the Kuma block, with the line `openssl rand -hex 12`
- CLAUDE.md: add `cron-run.sh` to the scripts list
- docs/m1-core.md: new section "Cron dead-man's switch"

Note vs repo: the note says 12 jobs, but ENTRIES has 13 (it leaves out qbit-watchdog). Wrap all 13.

cron-run.sh spec: `cron-run.sh <name> <timeout-secs> [--ok <codes>] <cmd> [args...]`
- Runs `timeout --kill-after=30 <secs> <cmd...>` and captures stdout and stderr to a mktemp file. Deletes the file on exit (trap).
- Pipes every line of the captured output to `logger -t cron-<name>`, then logs "exit <rc> in <s>s".
- Status:
  - up when rc is 0 or is in `--ok` (comma list, default "0");
  - down otherwise;
  - rc 124 or 137 gives the message "timed out after <secs>s";
  - any other down gives "exit <rc>: <last non-empty output line>", cut to 150 chars.
- Throttle (state file `${XDG_STATE_HOME:-$HOME/.local/state}/homelab/cron-run/<name>.last`, holding "<epoch> <status>"):
  - push when the status differs from the last pushed status, or when 300 s or more have passed since the last push;
  - otherwise skip the push.
  - Only daily and weekly jobs exist besides the every-minute ones, so this only limits the every-minute jobs.
- Secret:
  - read KUMA_CRON_PUSH_SECRET from `$REPO/.env` the way discord.sh reads its webhook URL (sed, never printed);
  - if it is empty, log "KUMA_CRON_PUSH_SECRET not set: no push" and skip the push.
- Push: `curl -fsG -m 10 -o /dev/null http://127.0.0.1:3001/api/push/<secret>-<name>` with `--data-urlencode` for status, msg ("OK" when up) and ping (duration in ms).
  - Put the URL in a `-K -` config on stdin, as discord.sh does, so the token never appears in ps.
  - If curl fails, log "kuma push failed" and carry on. Update the state file only after a successful push.
- Always exit with the job's own rc. Usage errors exit 2.

ENTRIES (same schedules; `$REPO/scripts/cron-run.sh <name> <timeout> [--ok 0,1] <original cmd>`):

| Job (`<name>`) | Timeout (s) | --ok |
|---|---|---|
| qbit-watchdog | 300 | |
| idea-actions | 3600 | |
| seerr-route | 300 | |
| ha-backup-check | 600 | 0,1 |
| scrutiny-check | 600 | 0,1 |
| disk-space-check | 600 | 0,1 |
| arr-missing-search | 7200 | |
| storage-cleanup | 1800 | |
| image-check | 1800 | |
| card-prices | 1800 | |
| self-check (`install-cron.sh --check --notify`) | 600 | 0,1 |
| wardrobe-daily | 600 | |
| fitness-weekly | 900 | |

`--ok 0,1` is there because those four scripts exit 1 after they have already sent their own ntfy or Discord alert. Without it, each finding would be alerted twice. Missed runs and timeouts are still caught for them. Say this in a comment.

`check()`: the missing-names list now uses awk `$7` (the job name) instead of the basename of `$6`.

Labels on uptime-kuma, per job `<name>`:
- `kuma.cron-<name>.push.name=cron-<name>`
- `kuma.cron-<name>.push.push_token=${KUMA_CRON_PUSH_SECRET:-}-<name>`
- `kuma.cron-<name>.push.interval=<s>`:
  - 600 for qbit-watchdog, idea-actions and seerr-route;
  - 93600 (26 h) for the daily jobs;
  - 691200 (8 d) for arr-missing-search, storage-cleanup, image-check and fitness-weekly.
  - Kuma 2.x caps intervals at 2073600 s.
- `kuma.cron-<name>.push.max_retries=0`

Use `:-` rather than `:?`, so `config -q` and auto-deploy don't fail before Dan sets the secret.

Dashboard tile: `homelab.external.cron.{name=Cron jobs, group=Infrastructure, icon=healthchecks, audience=admin, description=Scheduled jobs: last run OK}`. Its status comes from the monitors named `cron-*`. Before writing the push labels, confirm the push field names on https://autokuma.bigboot.dev/dev/entity-types/push/ (`push` is a listed AutoKuma type).

New service: None
New env vars: KUMA_CRON_PUSH_SECRET: random part of each job's Kuma push token (shared by core/uptime-kuma labels and cron-run.sh)

Checks the builder must run:
- `bash -n scripts/cron-run.sh scripts/install-cron.sh`
- `shellcheck` on both, if it is installed
- `scripts/dc.sh <worktree>/core/uptime-kuma config -q`
- `CRON_LIST=<fixture of the new ENTRIES> scripts/install-cron.sh --check`: should print "cron: in sync".
- The same with one line removed: should print "missing: ..." and the job name.
- `scripts/cron-run.sh t1 5 false`: exits 1, and `journalctl -t cron-t1` shows "exit 1".
- `scripts/cron-run.sh t2 2 sleep 10`: exits 124, logged as "timed out".
- `scripts/cron-run.sh t3 5 --ok 0,1 false`: status up.
- `scripts/cron-run.sh t4 5 sh -c 'exit 3'`: exits 3.
- Afterwards, delete the t* state files the tests created under `~/.local/state/homelab/cron-run/`.

Review focus:
- Kuma down or 3001 unreachable -> job still runs to the end, one syslog line, the job's rc is kept, and the state file is not updated (so the next run retries).
- Secret unset -> no push and no weak `-<name>` token is ever pushed. The monitors then go down, which is the visible signal.
- An every-minute job flaps between ok and failing -> a down push goes out at once and recovery pushes at once (status change). Steady state is at most one push per 5 min, so no alert spam.
- Job hangs -> killed at its timeout, a down push saying "timed out after Ns", and the next run is not blocked. idea-actions gets 3600 s, so a 20-minute deploy is never killed.
- Job output contains odd characters or is empty -> msg is URL-encoded and cut to 150 chars. Empty output gives "exit <rc>". No env values are logged by the wrapper.

Docs:
- CLAUDE.md scripts list: add `cron-run.sh <name> <timeout> [--ok codes] <cmd>` (wraps every cron job: syslog `cron-<name>` and a Kuma push monitor `cron-<name>`).
- docs/m1-core.md: new section covering:
  - how it works and the interval table;
  - the `--ok 0,1` exceptions;
  - where logs go: `journalctl -t cron-<name>`;
  - how to add a job: an ENTRIES line plus 4 labels;
  - the token scheme;
  - that after the deploy, `scripts/install-cron.sh --check` should print in sync.

## Manual steps
- Before deploying, add KUMA_CRON_PUSH_SECRET to the env file: `openssl rand -hex 12`. The note says Risk 1, so this may auto-deploy. If the secret is missing, the three every-minute monitors go down and alert within 10 minutes.
- Deploy recreates uptime-kuma and autokuma, then reinstalls cron on drift (deploy-idea does both).
- Check: `scripts/kuma-status.py cron` lists 13 push monitors, and the every-minute ones are up within about 5 min.

## Review notes
1. /home/dan/homelab/.worktrees/cron-deadman/scripts/cron-run.sh:31-32: if `mktemp` fails (for example /tmp is full), `out` is empty, the redirect fails and the job never runs. It still pushes "exit 1" as down, so Dan sees it. A fallback to `/dev/null` would keep the "never blocks the job" promise.
2. The `--ok 0,1` choice comes from the plan, and it also hides exit-1 paths where no alert went out. Two examples: disk-space-check exits with rc=1 after "alert ... NOT sent" when the ntfy post fails, and with rc=1 on a state-write error. The same goes for an ha-backup-check or scrutiny-check whose `notify` failed. Missed runs and timeouts are still caught.
3. Every-minute jobs now write "exit 0 in 0s" to the journal three times a minute (about 4300 lines a day). This is journal noise, not alert noise. Job output that used to be thrown away now also goes to syslog, and the last line goes into the Kuma or ntfy message. I found no cron script that prints secrets (none use requests or httpx, and none use `set -x`).
4. Manual steps say this "may auto-deploy". In fact `AUTO_PROTECTED` in /home/dan/homelab/.worktrees/cron-deadman/scripts/idea-actions.py:51 blocks auto-deploy, because the build touches the env example file and `install-cron.sh`. Dan deploys it himself, which is the safer outcome. With the secret unset, the monitors are created with the guessable token `-<name>`, which anyone on the LAN could push to. The plan accepts this.
5. Kuma push tokens are now in uptime-kuma's container labels, so anything that reads containers through the socket proxy can see them (dashboard, autokuma). These are low-value tokens and the dashboard only reads `homelab.*` labels. An OOM kill (rc 137) would be reported as "timed out".

## Declined to judge
- idea-actions being killed at 3600 s while three or more queued 20-minute deploys run back to back: this follows the plan's timeout table and is a rare case.
- Running cron-run.sh's own test cases (t1-t4): they write to syslog and the state directory, which is outside the read-only checks I'm allowed. I judged the logic by reading it instead.
- Moving the doc section to m1-core.md instead of m4-backups.md: the plan chose this explicitly.
- Tile description "Scheduled jobs, last run OK" instead of the plan's colon: wording only.
- shellcheck: not installed on the host.
