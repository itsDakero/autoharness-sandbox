---
name: add-service
description: Add a new web service to the homelab end to end (compose file, labels, port, start, verify, commit).
argument-hint: <service or idea, e.g. "dozzle" or "a recipe manager">
disable-model-invocation: true
---

# Add a service: $ARGUMENTS

Follow CLAUDE.md exactly. Work from the repo root. Ports in use: !`grep -E '^\| [0-9]+ \|' CLAUDE.md | cut -d'|' -f2 | tr -d ' ' | paste -sd' '`

## 1. Plan (stop and wait for OK)
Research the app (official docs/README, image registry) and show a short plan:
- **name** (lowercase-kebab; service = container = router name) and **category dir**
  (`media/` media apps, `tools/` admin utilities, `core/` infrastructure only, or propose a new one).
- **image**: the latest *stable* release, pinned exactly (e.g. `v8.14.3`), never `:latest`. Say where you
  found the tag (Docker Hub `https://hub.docker.com/v2/repositories/<ns>/<repo>/tags?page_size=50&ordering=last_updated`
  or GHCR / GitHub releases).
- **host port**: lowest free port ≥ 8082 that is not in the CLAUDE.md port table *and* not listening
  (`ss -ltnH "sport = :<port>"` is empty). Container port from the app docs.
- **volumes**: `${APPDATA_PATH}/<name>/…` for app data. Media as `${MEDIA_PATH}:/media:ro`. Read-write
  media needs explicit approval (the guard hook will ask).
- **networks**: `proxy`; add `socket-proxy` + `DOCKER_HOST=tcp://docker-socket-proxy:2375` only if it
  needs the Docker API (never `docker.sock`). Say if the socket proxy needs another endpoint enabled.
- **environment**: only what the app needs; secrets come from new `.env` vars that the user adds
  (add the names, empty, to `.env.example`, and tell the user to fill them in; never read `.env`).
- **labels**: homelab.name/group/icon/audience/description/port, Kuma monitor URL (a health endpoint
  if the app has one), `.lan` host name.

Do not change anything until the user approves the plan.

## 2. Build
1. Copy `templates/compose.yaml` to `<category>/<name>/compose.yaml` and replace `myservice` everywhere.
   Keep all three label groups (Traefik, Dashboard, Uptime Kuma); the port appears in `ports`,
   `homelab.port` and the Kuma URL. The icon is a slug from https://github.com/homarr-labs/dashboard-icons.
2. `mkdir -p /srv/homelab/<name>` (plus subdirs the app needs). If the image runs as a fixed uid other
   than 1000, say so. Fixing ownership needs root, which goes in bootstrap.sh for the user to run.
3. `scripts/dc.sh <dir> config -q` must pass (the compose-check hook also runs it after each edit).
4. `scripts/dc.sh <dir> up -d` (prompts), then `scripts/dc.sh <dir> ps` and `scripts/dc.sh <dir> logs --tail 50`.

## 3. Verify
- App answers: `curl -s -o /dev/null -w '%{http_code}\n' http://localhost:<port>/`.
- Dashboard tile: `curl -s http://localhost:8000/api/services` lists `<name>` with status `up`
  (not `unknown`). The dashboard caches for 15s, and Kuma checks every 60s, so retry for up to 2 minutes.
- Kuma monitor: `scripts/kuma-status.py <name>` shows the monitor, an `up` heartbeat and
  `notifications=ntfy-urgent`. If the monitor is missing, check `scripts/dc.sh core/uptime-kuma logs --tail 30 autokuma`.
- Anything else the app needs (e.g. it can see the Docker API, media visible).

## 4. Record and commit
- Add `| <port> | <name> |` to the CLAUDE.md port table (keep it sorted). New category → add it to the Layout list.
- `git add <dir> CLAUDE.md` (plus `.env.example` if changed), then `git commit` with a message like
  `Add <name> (<one line>)`.
- Report: URL `http://192.168.0.210:<port>/`, `.lan` name, anything the user must do (e.g. fill in `.env`, first-run setup).
