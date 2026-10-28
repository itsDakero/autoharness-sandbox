---
name: remove-service
description: Stop and remove a homelab service, its compose dir and port entry; keeps its app data unless told otherwise.
argument-hint: <service name>
disable-model-invocation: true
---

# Remove a service: $ARGUMENTS

1. Find it: `git ls-files '*/$ARGUMENTS/compose.yaml'`. If that finds nothing, or `$ARGUMENTS` is a core
   service (`core/…`: traefik, adguard, uptime-kuma, ntfy, dashboard, docker-socket-proxy), stop and ask.
2. Tell the user what will happen and get an OK:
   - containers stopped and removed (`down`, without `-v`),
   - `<dir>` removed from git, CLAUDE.md port row removed,
   - `/srv/homelab/$ARGUMENTS/` **kept** (say its size: `du -sh /srv/homelab/$ARGUMENTS`) unless the user says delete it,
   - AutoKuma deletes the Kuma monitor (`AUTOKUMA__ON_DELETE=delete`); the dashboard tile disappears.
3. `scripts/dc.sh <dir> down`
4. `git rm -r <dir>`, then remove the `| <port> | $ARGUMENTS |` row from the CLAUDE.md port table. If the
   service was the last in its category, ask before removing the category from the Layout list.
   Remove its variables from `.env.example` if no other service uses them, and tell the user to remove them from `.env`.
5. Verify: `docker ps -a --filter name=^$ARGUMENTS$` is empty; `curl -s http://localhost:8000/api/services`
   no longer lists it (cached up to 15s); `scripts/kuma-status.py $ARGUMENTS` says no monitor (allow ~30s).
6. Only if the user asked to delete data: `rm -r /srv/homelab/$ARGUMENTS` (the user confirms the prompt).
7. `git commit -m "Remove $ARGUMENTS"`.
