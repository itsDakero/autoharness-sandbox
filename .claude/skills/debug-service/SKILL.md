---
name: debug-service
description: Diagnose a homelab service that is down, unknown or misbehaving (containers, logs, dashboard, Uptime Kuma). Read-only; suggests fixes.
argument-hint: <service name>
allowed-tools: Read, Grep, Glob, Bash(scripts/dc.sh * ps *), Bash(scripts/dc.sh * logs *), Bash(scripts/dc.sh * config -q), Bash(scripts/dc.sh * config --images), Bash(scripts/kuma-status.py *), Bash(curl -s http://localhost:*), Bash(curl -s http://192.168.0.210*), Bash(docker ps *), Bash(docker inspect --format *), Bash(docker logs *), Bash(ss -ltn *), Bash(git log *), Bash(git diff *)
disallowed-tools: Edit, Write, MultiEdit, NotebookEdit
---

# Debug: $ARGUMENTS

Read-only. **Change nothing** (no up/restart/edits) until the user approves a fix.
Never print secrets: no `config` without `-q`, no `docker inspect` without `--format`, no env dumps, no `.env`.

## Gather
1. Compose dir: `git ls-files '*/$ARGUMENTS/compose.yaml'`. Read it. `scripts/dc.sh <dir> config -q`.
2. Containers: `scripts/dc.sh <dir> ps -a`, then
   `docker inspect --format '{{.State.Status}} exit={{.State.ExitCode}} restarts={{.RestartCount}} health={{if .State.Health}}{{.State.Health.Status}}{{end}} started={{.State.StartedAt}}' $ARGUMENTS`.
3. Logs: `scripts/dc.sh <dir> logs --tail 100`. Look for the first error, not the last.
4. Reachability: `curl -s -o /dev/null -w '%{http_code}\n' http://localhost:<homelab.port>/` and the Kuma
   URL from the labels. `ss -ltn 'sport = :<port>'` for port conflicts.
5. Dashboard: `curl -s http://localhost:8000/api/services`. Find the entry and its status, and check whether `kuma` is true.
   `unknown` = no Kuma monitor named `$ARGUMENTS` or `$ARGUMENTS-*`.
6. Kuma: `scripts/kuma-status.py $ARGUMENTS --beats 10` (monitor URL, heartbeats with error messages).
   AutoKuma: `scripts/dc.sh core/uptime-kuma logs --tail 50 autokuma`.
7. Recent changes: `git log --oneline -5 -- <dir>`, `git diff -- <dir>`.

## Known issues (check these)
- **Dashboard says down but Kuma says up** (or vice versa) after a monitor URL change: Kuma keeps the old URL's
  `/metrics` series. The dashboard logs "has several metric series" (`scripts/dc.sh core/dashboard logs --tail 50`).
  Fix: `scripts/dc.sh core/uptime-kuma restart`.
- **AutoKuma "You are not logged in"** after Kuma restarted on its own: `scripts/dc.sh core/uptime-kuma restart autokuma`.
- **Kuma check fails but the app answers on localhost**: a container can't reach a port published by another
  container on the same network (UFW drops it). Kuma checks via its `monitor` network. Make sure the
  monitor URL uses `http://192.168.0.210:<port>`, not a container name on `proxy`.
- **Docker API errors** (403 from docker-socket-proxy): the endpoint isn't enabled in
  `core/docker-socket-proxy/compose.yaml` (GET-only flags such as `INFO: 1`).
- **Permission denied on /srv/homelab/<svc>**: image uid ≠ 1000. Ownership fixes need root and go in bootstrap.sh.
- **Image pull / DNS failures** after resolv.conf changes: restart docker (via bootstrap.sh).

## Report
Show the root cause with evidence (log lines, status codes), the proposed fix (exact commands or diff), and the risk.
Wait for approval before applying it.
