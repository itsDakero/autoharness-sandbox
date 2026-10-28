# New cron job checklist

Every step for adding a cron job. Background (cron-run.sh, push tokens, throttle) is in `docs/m1-core.md`
"Cron dead-man's switch"; the merge rules are in `docs/m5-pipeline.md` "Merge-friendly registries".
`<name>` below is the job name: lowercase-kebab, unique, and the same in every file.

Jobs that need root (e.g. anything reading the restic repo) are not cron jobs: they get a systemd
service + timer in `systemd/`, an `OnFailure=` ntfy unit, and a line in `bootstrap.sh`'s unit list (see
`scripts/restore-drill.sh` and `docs/m4-backups.md`, stage E). Same for monthly jobs: no push monitor covers them.

## 1. The script
- [ ] `scripts/<name>.sh` or `scripts/<name>.py`, executable, with a header comment: what it does, when it runs,
      its flags (`--dry-run`/`--print`/`test` where it sends anything).
- [ ] No root, no sudo. Runs as dan from the repo checkout; reads the repo `.env` itself if it needs a key.
- [ ] Alerts: urgent → ntfy, non-urgent → `scripts/discord.sh`. If it exits 1 after sending its own alert,
      it gets `--ok 0,1` (step 2) so Kuma doesn't alert twice. Any other non-zero exit = a real failure.
- [ ] Output is short: every line goes to syslog, and the last line becomes Kuma's down message (150 chars).
- [ ] Finishes well inside its timeout and inside the gap between two runs.
- [ ] New `.env` keys: add them to `.env.example` in their service's section, not at the end. Never commit `.env`.

## 2. Cron entry: `scripts/cron.d/<name>.cron`
- [ ] Optional `#` comment lines, then exactly one crontab line:
      `<m> <h> <dom> <mon> <dow> $R <name> <timeout-secs> [--ok 0,1] $REPO/scripts/<name>.py [args]`
- [ ] `$R` and `$REPO` stay as literal text; `install-cron.sh` swaps them in and adds ` # homelab`.
- [ ] The 7th field is `<name>` and equals the file name, or `install-cron.sh` exits 2 (and no job is installed).
- [ ] LF line endings (a CRLF `\r` ends up in the crontab line and shows as drift).
- [ ] Timeout: 300 for quick checks, 1200–1800 for API pulls or anything slow. It must be shorter than the period.
- [ ] Pick a minute nobody else uses at that hour (`grep -h '\$R' scripts/cron.d/*.cron` shows the current ones).

## 3. Kuma push monitor: `core/uptime-kuma/compose.d/cron-<name>.yaml`
- [ ] Copy an existing fragment (e.g. `cron-card-prices.yaml`) and change the name everywhere:
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
- [ ] `<suffix>` = `<name>` without hyphens, padded with `0` or cut to exactly 16 characters
      (`card-prices` → `cardprices000000`, `arr-missing-search` → `arrmissingsearch`). It must match what
      `cron-run.sh` computes and be unique: check it against the other fragments, especially for long names that get cut.
- [ ] `<secs>` = period + grace:

  | Schedule | Interval |
  |---|---|
  | every minute | 600 |
  | every 5 min | 900 |
  | hourly | 5400 |
  | daily | 93600 (26 h) |
  | weekly | 691200 (8 d) |

  Kuma 2.x caps intervals at 2073600 s (24 d); a monthly job can't be covered by a push monitor.

## 4. Docs and lists
- [ ] `scripts/README.md`: one bullet for the script, in its alphabetical spot, starting with
      `(cron …: what it does; where it reports)`.
- [ ] `docs/m1-core.md` "Cron dead-man's switch": add the job to the intervals line if it is every-minute, 5-min,
      hourly or weekly, and to the `--ok 0,1` line if it uses it.
- [ ] The service's own README or milestone doc, if the job belongs to one (e.g. `tools/fpl/README.md`).

## 5. Checks before handing it over
- [ ] `bash -n scripts/<name>.sh` or `python3 -m py_compile scripts/<name>.py`; a `--dry-run`/`--print` run if it has one.
- [ ] `scripts/dc.sh core/uptime-kuma config -q` passes (the fragment parses and merges).
- [ ] Every `scripts/cron.d/<n>.cron` has a `core/uptime-kuma/compose.d/cron-<n>.yaml` and the other way round.
- [ ] `scripts/install-cron.sh --check` lists the new job only as `missing:` (nothing else drifts). Never run
      `install-cron.sh` without `--check` from a worktree: it installs that checkout's paths.

## 6. Deploy (Dan)
- [ ] Merge via `scripts/deploy-idea.sh <slug>` or by hand on main. A new `scripts/cron.d/` file is never
      auto-deployed (`AUTO_PROTECTED` in `scripts/idea-actions.py`).
- [ ] `scripts/install-cron.sh` from main (deploy-idea.sh does it on drift); then `--check` prints "cron: in sync".
- [ ] `scripts/dc.sh core/uptime-kuma up -d` (deploy-idea.sh does it when a fragment changed). Only ever through
      `dc.sh`: without it the fragments are dropped and AutoKuma (`ON_DELETE=delete`) deletes every cron monitor.
- [ ] After the first run: `journalctl -t cron-<name>` shows `exit 0 in Ns`, and `scripts/kuma-status.py cron-<name>`
      shows the monitor up. It also appears on the dashboard's "Cron jobs" tile.

## Removing a job
Delete `scripts/cron.d/<name>.cron`, `core/uptime-kuma/compose.d/cron-<name>.yaml`, the script and its `scripts/README.md`
bullet and doc mentions together; then `install-cron.sh` and `dc.sh core/uptime-kuma up -d` from main, so the crontab
line and the monitor both go (AutoKuma deletes the monitor).
