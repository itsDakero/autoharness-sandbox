---
name: add-cron-job
description: Add a homelab cron job end to end (script, scripts/cron.d entry, Kuma push monitor, README bullet, checks). Use when a script should run on a schedule.
argument-hint: <job name or what it should do, e.g. "docs-index-check, weekly">
---

# Add a cron job: $ARGUMENTS

Full checklist and the why: `docs/new-cron-job.md` (read it first). Background: `docs/m1-core.md` "Cron dead-man's
switch". Work from the repo root. Times in use: !`grep -h '\$R' scripts/cron.d/*.cron | awk '{print $1, $2, $5, $7}' | sort -k2,2 -k1,1n | paste -sd';'`

Not a cron job: anything needing root (e.g. reading the restic repo) or running monthly. Those get a systemd
service + timer in `systemd/` with an `OnFailure=` ntfy unit and a line in `bootstrap.sh` (see `scripts/restore-drill.sh`).

## 1. Name and schedule
- `<name>`: lowercase-kebab, unique, and identical in every file below (script, `.cron`, fragment, Kuma monitor).
- Schedule: pick a minute no other job uses in that hour (list above). Period must be longer than the timeout.
- Timeout: 300 for quick checks, 600 for checks that post, 1200–1800 for API pulls or anything slow.

## 2. The script: `scripts/<name>.sh` or `scripts/<name>.py`
- Executable (`chmod +x`), runs as dan from the repo checkout, no root/sudo. Reads `.env` itself only if it needs a key
  (sed it out like `scripts/discord.sh`; never print a secret or put it on a command line).
- Header comment: what it does, when it runs (`Cron (weekly, Mondays 09:35, user dan): …`), its flags, exit codes,
  test overrides (shell env, not `.env`). `-h|--help` prints it; bad arguments exit 2.
- Alerts: **urgent → ntfy** (something is broken or about to be: disk full, backup stale, disk failing;
  copy `notify()` from `scripts/disk-space-check.sh`). **Non-urgent → Discord** via `scripts/discord.sh "<msg>"`
  (digests, drift, "fix when you can"). Say which and why in the header.
- `--dry-run` (or `--print`) whenever it sends anything: do all the work, print the message, send nothing, write no
  state. A `test` argument that sends one test message is optional (`disk-space-check.sh test`).
- Exit codes: 0 = all fine; 1 = finding, alert already sent (gets `--ok 0,1`, so Kuma does not alert twice);
  2 or anything else = real failure (post failed, bad input): Kuma alerts. Without its own alert, any non-zero = failure.
- Output short: every line goes to syslog, the last line becomes Kuma's down message (150 chars), so end with the
  summary.
- New `.env` keys go in `.env.example` in their service's section. Never commit `.env`.

## 3. Cron entry: `scripts/cron.d/<name>.cron`
Optional `#` comment lines, then exactly one line, LF endings, `$R`/`$REPO` left literal:
```
35 9 * * 1 $R <name> <timeout-secs> [--ok 0,1] $REPO/scripts/<name>.sh [args]
```
`$R` is `scripts/cron-run.sh <name> <timeout> [--ok codes] <cmd>`: it runs the job under `timeout`, logs output to
syslog (`journalctl -t cron-<name>`), and pushes Kuma monitor `cron-<name>` up (rc 0 or in `--ok`) or down
("exit N: <last line>" / "timed out after Ns"). The 7th field must equal the file name or `install-cron.sh` exits 2.

## 4. Kuma push monitor: `core/uptime-kuma/compose.d/cron-<name>.yaml`
Copy `cron-omada-ap-check.yaml` and replace the name in every line:
```yaml
# Kuma push monitor for scripts/cron.d/<name>.cron (merged by scripts/dc.sh)
services:
  uptime-kuma:
    labels:
      - kuma.cron-<name>.push.name=cron-<name>
      - kuma.cron-<name>.push.push_token=${KUMA_CRON_PUSH_SECRET:-}<suffix>
      - kuma.cron-<name>.push.interval=<secs>
      - kuma.cron-<name>.push.max_retries=0
```
- `<suffix>`: `n=<name>; s="${n//-/}0000000000000000"; echo "${s:0:16}"` (same as `cron-run.sh`). It must be unique:
  `grep -h push_token core/uptime-kuma/compose.d/*.yaml | sed 's/.*}//' | sort | uniq -d` prints nothing.
- `<secs>` = period + grace: every minute 600, every 5 min 900, hourly 5400, daily 93600, weekly 691200.
  Nothing over 2073600 (Kuma's cap), so no monthly jobs.

## 5. Docs, same change
- `scripts/README.md`: one bullet in its alphabetical spot:
  `` `<name>.sh [--dry-run]` (cron <when>: <what it does>; <Discord|ntfy> <when>) ``.
- `docs/m1-core.md` "Cron dead-man's switch": add the name to the intervals line (every-minute, 5-min, hourly or weekly
  jobs) and to the `--ok 0,1` line if it uses it.
- The owning service's README or milestone doc, if the job belongs to one. A new doc gets a line in `docs/README.md`.

## 6. Test without a server
No Docker daemon, crontab, `.env`, Kuma or Discord is needed for these:
- `bash -n scripts/<name>.sh` + `shellcheck scripts/<name>.sh`, or `python3 -m py_compile scripts/<name>.py`.
- `scripts/<name>.sh --dry-run`; then force each exit path with the test overrides (scratch dirs, never real data).
- The wrapper: `XDG_STATE_HOME=<scratch> scripts/cron-run.sh <name> 300 --ok 0,1 scripts/<name>.sh --dry-run; echo $?`
  (no `.env`: it logs "no push" and keeps the job's rc).
- The cron entry: write a scratch crontab with every other job's line (`$R`/`$REPO` expanded, ` # homelab` appended),
  then `CRON_LIST=<that file> scripts/install-cron.sh --check` must print only `missing: … <name> …`. Never run
  `install-cron.sh` without `--check` outside main.
- The fragment: `scripts/dc.sh core/uptime-kuma config -q` on the server; in the sandbox,
  `docker compose --env-file .env.example --project-directory core/uptime-kuma -f core/uptime-kuma/compose.yaml`
  plus `-f` for each `compose.d/*.yaml`, then `config -q` (no daemon needed).
- Pairs: every `scripts/cron.d/<n>.cron` has `compose.d/cron-<n>.yaml` and the other way round.
- `scripts/check.sh` passes.

## 7. Final checklist
- [ ] `scripts/<name>.*` executable, header, `--dry-run`, exit 0/1/2 as above, ntfy-or-Discord chosen and stated
- [ ] `scripts/cron.d/<name>.cron`: one line, 7th field = `<name>`, unique minute, timeout < period, `--ok 0,1` iff exit 1 = alerted
- [ ] `core/uptime-kuma/compose.d/cron-<name>.yaml`: name in all 4 labels, unique 16-char suffix, interval from the table
- [ ] `scripts/README.md` bullet, `docs/m1-core.md` lines, `.env.example` keys if any
- [ ] Section 6 checks run; report any that could not run
- [ ] Deploy is Dan's (`docs/new-cron-job.md` step 6): `install-cron.sh` from main, `dc.sh core/uptime-kuma up -d`
      (only via `dc.sh`, or AutoKuma deletes every cron monitor), then `journalctl -t cron-<name>` and
      `scripts/kuma-status.py cron-<name>` after the first run
