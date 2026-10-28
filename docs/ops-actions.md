# Ops actions runner

`scripts/ops-actions.py` (cron every 5 min, as dan, no LLM, no new container) restarts a registered non-core
container that is stuck `unhealthy`. Docker restart policies only act on exit, so a hung container otherwise stays hung.

## Registry
In the script (`REGISTRY`): prowlarr, radarr, radarr-remote, sonarr, sonarr-remote, seerr, jellyfin (`media/`);
books, changedetection, dozzle, fitness, lms, scrutiny, wardrobe (`tools/`).
Never: anything in `core/`, gluetun, qbittorrent (has its own watchdog), hermes. The script exits 2 if the
registry ever contains one.

## Rule and limits
- A registered container `unhealthy` (and running) on 2 checks in a row: `scripts/dc.sh <dir> restart <service>`.
- Per service: at most 1 restart per hour and 3 per day. Beyond that one Discord message ("needs Dan"), sent
  once until the service turns healthy again.
- Global breaker: 3 restarts already in the last hour and a 4th is due: write PAUSE, alert on Discord + ntfy, stop.
- If `dc.sh` fails or times out for a service: syslog only, its streak stays as it was.
- Overlapping runs: a `flock` makes the second run exit quietly.

## Files in /srv/homelab/ops-actions
`state.json` (streaks, restart times; a corrupt one is kept as `state.json.bad`), `audit.jsonl` (append-only:
time, service, action, reason, result), `PAUSE`, `.lock`.

## Pause and resume
- Pause: `touch /srv/homelab/ops-actions/PAUSE`. Resume: `rm /srv/homelab/ops-actions/PAUSE`.
- The breaker writes PAUSE itself. Fix the cause (disk, VPN, a bad healthcheck), then remove it.

## Checking
- `scripts/ops-actions.py --dry-run`: prints each service's health and what it would do; changes nothing.
- `journalctl -t ops-actions`; `tail /srv/homelab/ops-actions/audit.jsonl`.

## Adding a service
Its healthcheck must exist and report healthy first (healthchecks-everywhere). Then add it to `REGISTRY`.
A wrong healthcheck that is always unhealthy would use up its caps.

## Action tiers
| Tier | Actions |
|---|---|
| Auto, notify after (Discord) | restart one unhealthy non-core container (capped); qbit/Gluetun recovery (existing watchdog); image-prune.sh; anything read-only |
| One tap (dashboard, later) | image bumps beyond patch; compose edits; restarting core; a restart after the cap; any delete; anything touching /mnt/media |
| Terminal only (Dan) | bootstrap.sh/root, UFW/DOCKER-USER, Tailscale/DNS, NVIDIA driver, restic config, secrets, .claude/ |

Hermes requests for actions are a later idea (hermes-action-requests) that will feed this runner.
