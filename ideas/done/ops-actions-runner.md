# Ops actions runner: auto-restart unhealthy non-core containers, with limits and an audit log

Value: 4   (the first "safe actions run automatically" lane)
Effort: 3  (registry, cooldowns, breaker, kill file, audit log)
Risk: 2    (it restarts containers on its own, within a fixed allowlist)
Score: 12
Source: claude 2026-10-25 (reports/Homelab autonomy and assistant gaps.md, roadmap #3)
Depends on: healthchecks-everywhere (it acts on `unhealthy`). Park if that isn't built yet.

## Problem
When a container hangs, nothing restarts it: Docker restart policies only act when a container exits.
Dan wants safe actions to run on their own and the rest to wait for him.

## Proposal
- `scripts/ops-actions.py`, host cron every 5 min (via `cron-run.sh` if `cron-deadman` is built), modelled on
  `scripts/idea-actions.py`. No new container and no second Docker socket: it runs as dan on the host with
  `scripts/dc.sh <dir> restart <service>`.
- Registry file in git (`scripts/ops-actions.yaml` or a dict in the script): which services may be
  auto-restarted. Start with non-core `media/*` and `tools/*` web apps. Never: anything in `core/`, gluetun,
  qbittorrent (it has its own watchdog), hermes.
- Rule: a registered container `unhealthy` for 2 checks in a row → restart once.
- Limits: per service at most 1 restart per hour and 3 per day; then stop and send one Discord message
  ("needs Dan"). Global breaker: more than 3 restarts across all services in an hour → stop all actions and
  alert. Kill file `/srv/homelab/ops-actions/PAUSE` stops everything.
- Append-only JSONL audit log in `/srv/homelab/ops-actions/` (time, service, reason, result); Discord line
  after each action (`scripts/discord.sh`).
- `--dry-run` prints what it would do. Docs: a section in `docs/m5-pipeline.md` or a new runbook, with the
  tier table (auto / approve / terminal only) from the report.

## Notes
- Later notes (Hermes asking for actions) feed this same runner; this note is rule-based only, no LLM.

## Plan
Goal: A host cron script restarts a registered non-core container after it has been `unhealthy` on 2 checks in a row. It has per-service caps, a global breaker, a kill file and a JSONL audit log. It uses no LLM and no new container.
Dependency: healthchecks-everywhere is built and reviewed (branch `idea/healthchecks-everywhere`) but not deployed yet. That is a runtime dependency only. Until it is deployed, most targets report Health "" and the runner does nothing, which is harmless. So Dan deploys it first (see Manual steps). cron-deadman (`idea/cron-deadman`) is also undeployed and changes the same ENTRIES block (see install-cron.sh below).
Kind: script/cron
Files:
- scripts/ops-actions.py (new, executable, python3 stdlib only; header docstring like idea-actions.py's). It runs as dan with no root.
  - Paths: `STATE_DIR = $APPDATA_PATH (default /srv/homelab)/ops-actions/`, created if missing. Files in it: `state.json`, `audit.jsonl`, `PAUSE`, `.lock`.
  - Registry: a dict in the script, `REGISTRY = {service: compose_dir}`, with exactly these entries:
    - prowlarr, radarr, radarr-remote, sonarr, sonarr-remote, seerr, jellyfin -> `media/<name>`
    - changedetection, dozzle, fitness, jelu, scrutiny, wardrobe -> `tools/<name>`
  - `NEVER = {"gluetun", "qbittorrent", "hermes"}`, plus a check at start that refuses any registry dir starting with `core/`. If either is ever violated, exit 2.
  - Lock: `fcntl.flock` non-blocking on `.lock`. If the lock is held, exit 0 quietly so two runs never overlap.
  - PAUSE: if the PAUSE file exists, log one syslog line and exit 0. It does nothing else: no state change, no Discord.
  - Health per service: `scripts/dc.sh <dir> ps --format json <service>` (timeout 60 s). Parse either a JSON array or JSON-lines, and read `State` and `Health`.
    - If dc.sh fails, times out or returns nothing: syslog that service, leave its streak unchanged, go on to the next service.
    - `unhealthy` while `State == running`: streak += 1.
    - Anything else (healthy, starting, "", exited, missing): streak = 0, and clear its `needs_dan` flag.
  - Rule: when streak >= 2, restart the service, subject to the limits below.
  - Limits (state keeps the restart timestamps for each service; drop entries older than 24 h):
    - Per service: if the service already had a restart in the last 1 h or 3 in the last 24 h, don't restart it. Send one Discord message, "ops-actions: <svc> still unhealthy, restart cap reached - needs Dan", and only if `needs_dan` is not set yet. Then set `needs_dan`.
    - Global: count restarts across all services in the last hour. If that count is already >= 3, don't restart. Instead write PAUSE (content: time + reason "breaker: >3 restarts/hour"), add an audit line, send Discord, and send ntfy using the same `NTFY_ALERT_TOPIC` pattern as scripts/disk-space-check.sh lines 20-28. Then stop the run.
  - Restart: `scripts/dc.sh <dir> restart <service>` (timeout 180 s). Record the timestamp whatever the result, reset the streak to 0, append to audit.jsonl `{"time": ISO, "service", "action": "restart", "reason": "unhealthy x<streak>", "result": "ok"|"failed rc=N"|"timeout"}`, then run `scripts/discord.sh "ops-actions: restarted <svc> (unhealthy x2): <result>"`.
  - At most one restart per run per service. Write state.json atomically (tmp file + `os.replace`).
  - A corrupt or missing state.json: start empty, keep the bad file as `state.json.bad`, and log to syslog.
  - `--dry-run`: print each service's health and what the runner would do (including cap and breaker decisions). Don't restart, don't write state, PAUSE or audit, and don't post to Discord or ntfy.
  - Syslog tag `ops-actions`.
- scripts/install-cron.sh: add one ENTRIES line, `*/5 * * * * $REPO/scripts/ops-actions.py # homelab`.
  - If the worktree's install-cron.sh already defines `R=...cron-run.sh` at build time (cron-deadman merged), use `*/5 * * * * $R ops-actions 600 $REPO/scripts/ops-actions.py # homelab` instead. In that case also add the 4 AutoKuma push-monitor labels for `cron-ops-actions` on core/uptime-kuma/compose.yaml (interval 1200, max_retries 0), copying the existing cron-* labels there.
- docs/ops-actions.md (new runbook):
  - What it does, with the registry and the never-list.
  - The rule and the limits.
  - Files in /srv/homelab/ops-actions.
  - How to pause and resume: `touch` / `rm` PAUSE. The breaker writes PAUSE, so Dan removes it after fixing the cause.
  - `--dry-run`; `journalctl -t ops-actions`.
  - How to add a service: its healthcheck must exist first.
  - The tier table, copied as these 3 rows:
    - Auto, notify after (Discord): restart one unhealthy non-core container (capped); qbit/Gluetun recovery (existing watchdog); image-prune.sh; anything read-only.
    - One tap (dashboard, later): image bumps beyond patch; compose edits; restarting core; a restart after the cap; any delete; anything touching /mnt/media.
    - Terminal only (Dan): bootstrap.sh/root, UFW/DOCKER-USER, Tailscale/DNS, NVIDIA driver, restic config, secrets, .claude/.
  - A note that Hermes requests are a later idea (hermes-action-requests) that will feed this runner.
- docs/README.md: one index line for docs/ops-actions.md.
- CLAUDE.md: in the Layout `scripts/` list, add `ops-actions.py [--dry-run]` (cron every 5 min: restart registered non-core containers unhealthy 2 checks running, capped 1/h + 3/day per service, breaker >3/h writes PAUSE; see docs/ops-actions.md).
New service: None
New env vars: None. It reuses NTFY_ALERT_TOPIC and DISCORD_WEBHOOK_URL through the existing readers.
Checks the builder must run:
- `python3 -m py_compile scripts/ops-actions.py`
- `bash -n scripts/install-cron.sh`
- `CRON_LIST=/dev/null scripts/install-cron.sh --check` (expect it to list ops-actions as missing, exit 1)
- `scripts/ops-actions.py --dry-run` from the worktree, read-only. Expect one line per registered service and no files created in /srv/homelab/ops-actions.
- If uptime-kuma was touched: `scripts/dc.sh <worktree>/core/uptime-kuma config -q`
Review focus:
- Docker/compose down or dc.sh erroring for every service -> no restarts, no Discord spam (syslog only), streaks unchanged.
- A service stuck unhealthy for hours -> at most 1 restart/h and 3/day, then exactly one "needs Dan" message until it turns healthy again.
- Several services unhealthy at once (host cause: full disk, VPN) -> no more than 3 restarts in any hour. On the 4th, PAUSE is written, one Discord + ntfy alert is sent, and later runs do nothing until Dan removes PAUSE.
- Overlapping runs (a slow restart past 5 min) -> the flock makes the second run exit 0 without acting.
- `--dry-run` or an unregistered/never-list name (gluetun, qbittorrent, hermes, core/*) -> never restarted; dry-run writes nothing.
Docs: CLAUDE.md scripts list (one entry); docs/README.md (one line); new docs/ops-actions.md. No port table change.

## Manual steps
- Deploy healthchecks-everywhere first, and check `scripts/dc.sh <dir> ps` shows "(healthy)" for the registered services. A wrong healthcheck that is always unhealthy would otherwise use up its restart caps.
- If cron-deadman was deployed between this build and its deploy, the ENTRIES block in install-cron.sh conflicts. Resolve it with the `$R ops-actions 600 ...` form and add the cron-ops-actions Kuma labels, as described in Files.
- After the deploy: `scripts/install-cron.sh` (deploy-idea reinstalls on drift), then `scripts/ops-actions.py --dry-run` once.
- The note asks nothing that breaks the repo rules. Its build goes to Dan, not auto-deploy: Risk 2, and it touches install-cron.sh.

## Review notes
1. /home/dan/homelab/.worktrees/ops-actions-runner/scripts/ops-actions.py:353-363: the plan says to block a restart if the service had one in the last hour, and the code does that. The side effect is that "restart cap reached - needs Dan" goes out about 10 minutes after the first restart, and the second and third restarts still happen later. Also, "starting" clears `needs_dan`, so if a run sees a restarted container while it is still "starting", the message can be sent again, up to 3 a day. It is never spam, but the review focus expected the message once, after the 3/day cap. Consider sending it only when the daily cap is hit, and clearing `needs_dan` only on `healthy`.
2. ops-actions.py:371-380: if writing PAUSE fails (disk full is one of the host causes this guards against), every 5-minute run trips the breaker again and sends Discord and ntfy each time. That is rare, but you could skip the alert when the audit/PAUSE write also fails, or alert only once.
3. ops-actions.py:334: a hand-edited state.json with non-numeric `restarts` entries raises a TypeError and the run dies. `load_state` only checks the top-level shape.
4. Dry-run never takes the lock. That is fine because it writes nothing, but a dry-run during a live run shows streaks from before that run.
5. The worktree has no .env, so the builder's dry-run hit "dc.sh ps rc=1" for all 13 services. That path behaved as planned: syslog only, streaks unchanged, nothing written, exit 0. The healthy path was not exercised in the worktree. I checked the parser separately against real `dc.sh media/prowlarr ps --format json` output: compose v5.6.0 gives JSON-lines and it parsed to `('prowlarr','running','')`.

## Declined to judge
- Restarting jellyfin while someone is watching: it is already unhealthy, and the plan registers it on purpose.
- The breaker trips again straight away if Dan removes PAUSE within the hour: the plan has Dan fix the cause first.
- "missing" container gives an empty ps output, so the streak stays unchanged rather than resetting to 0: the plan contradicts itself here, and this is the safer reading.
- An idle PAUSE writes one syslog line every 5 minutes: the plan specifies exactly that.
