# Put Dozzle, the Traefik dashboard and ntfy behind a login

The dashboard login (`docs/m1-core.md`, Admin login) protects only the dashboard. These three have no login, and
anyone on the LAN or tailnet can open them:
- Dozzle (8082): every container's live logs (torrent names, who watches what, anything an app logs by mistake).
- Traefik dashboard (8080, `--api.insecure=true`): all routers, services and middlewares, read-only.
- ntfy (8081): anyone who knows or guesses a topic can read alerts or send fake ones; the web UI lists nothing,
  but topics aren't secret from someone watching traffic (plain HTTP).

## Decision
- **Dozzle and Traefik: reuse the dashboard login via Traefik forward auth.** One login for all admin web UIs.
  - Dashboard gets `GET /auth/verify`: 200 with a valid `homelab_admin` cookie, else a redirect to
    `http://<same host>:8000/login`. Cookies ignore ports, so a login at `homelab:8000` also counts at
    `homelab:8082` and `homelab:8080` (one login per host name, as now).
  - Ports 8080 and 8082 move from the containers to Traefik entrypoints (`--entrypoints.dozzle.address=:8082`,
    the API on its own entrypoint without `api.insecure`), each router with the forward-auth middleware. Then
    nothing reaches them without passing Traefik. `homelab.port` stays the same, so tiles and the port table
    don't change.
  - Dozzle: `DOZZLE_AUTH_PROVIDER=forward-proxy` (dashboard returns `Remote-User`), or none and rely on Traefik.
  - The `.lan` routes (`dozzle.lan`, `traefik.lan`) get the same middleware. They can't share the cookie
    (different host names, and browsers refuse `Domain=lan`), so they'd redirect to `home.lan`'s login and
    still fail – drop those two `.lan` routes rather than add a second login flow.
- **ntfy: its own users, not the dashboard login.** The phone app, Kuma and `qbit-watchdog.sh` are API clients,
  not browsers with a cookie.
  - `NTFY_AUTH_DEFAULT_ACCESS=deny-all`; user `dan` with read on the alert topic (phone app login);
    one write-only access token for Kuma's ntfy notification and the watchdog (`NTFY_ALERT_TOKEN` in `.env`).
  - Keep port 8081 direct (the iOS app's server URL must stay `http://homelab:8081`).

## Watch out for
- Uptime Kuma monitors must not hit the login: Traefik `/ping` and Dozzle via their internal addresses
  (`http://traefik:8080/ping`, `http://dozzle:8080/healthcheck`), or a forward-auth-free health router.
- AutoKuma `kuma.*` labels change with the URLs.
- New core entrypoints change Traefik's ports: update the CLAUDE.md port table notes and the permissions'
  core ask list if a service is added.
- ntfy: test that iOS instant push still works with auth (the app polls `homelab:8081` with credentials
  after the ntfy.sh wake-up).
- Do this with HTTPS in mind: once there's TLS, add `Secure` to the cookie and the redirect target changes.

Plan it as a change to dashboard, Traefik, Dozzle and ntfy, not via add-service.

## Parked 2026-10-14

## Questions
Planner proposes splitting into A "admin-tools-forward-auth" (dashboard /auth/verify forward auth
in front of Dozzle + Traefik dashboard) and B "ntfy-auth" (deny-all + token for every publisher:
qbit-watchdog.sh, ha-backup-check.sh, scrutiny-check.sh, backup.sh incl. root systemd failure
units, seerr-route.py, Kuma ntfy-urgent notification, iOS app login).

1. Split into A (forward auth for Dozzle/Traefik) and B (ntfy auth), A first? Yes/no.
2. A: Kuma monitoring of Dozzle/Traefik once behind login - auth-free health route on Traefik
   (e.g. internal-only ping entrypoint), or internal addresses only (http://traefik:8080/ping,
   http://dozzle:8080/healthcheck)? If internal: is Kuma on the proxy network?
3. A: OK to remove dozzle.lan and traefik.lan entirely (AdGuard rewrites/bookmarks stay manual)?
4. B: token from the repo env file (NTFY_ALERT_TOKEN, Bearer header) in all six publishers, incl.
   the root systemd path via backup.sh? Will you set the Kuma notification token and iOS login
   by hand?
5. B: should NTFY_ALERT_TOPIC stay a secret once auth is on?

## Answers 2026-10-14

1. Yes, split. A first.
2. Internal addresses only. Kuma joins the proxy network if not already on it.
3. Yes, remove both. I’ll clean up AdGuard and bookmarks by hand.
4. Yes, one env token for all six. I’ll set the Kuma token and iOS login by hand.
5. No, not a secret. Keep it in the env file anyway.

## Plan
Goal: Part A of the split Dan approved. Dozzle (8082) and the Traefik dashboard (8080) go behind the
dashboard's admin login, using Traefik forward auth. Part B (ntfy auth) is queued as its own idea.
Kind: change to core/dashboard, core/traefik, tools/dozzle (+ docs, + new idea note)

Files:
- core/dashboard/app/auth.py: add `verify_redirect(request) -> str | None`.
  - Read `X-Forwarded-Host` (Traefik sets it to the original Host, e.g. `homelab:8082`).
  - hostname = `urlsplit("//" + value).hostname`, lowercased.
  - If the hostname is missing or doesn't match `^[a-z0-9.-]{1,253}$`, return None.
  - Otherwise return `f"http://{hostname}:8000/login"`.
  - Add a comment: once there's HTTPS, the scheme and port change here and the cookie gets Secure.
- core/dashboard/app/main.py: add `@app.get("/auth/verify")`, with no dependencies.
  - `auth.is_admin(request)` true: `Response(status_code=200)`, empty body.
  - Else, if `verify_redirect` gives a URL: `RedirectResponse(url, 302)`.
  - Else: `PlainTextResponse("login required", 401)`.
  - Add no `next=` parameter (avoids an open redirect). After login the user lands on /admin and clicks
    the tile again.
- core/dashboard/compose.yaml: change only `image: homelab/dashboard:0.11.0` to `0.12.0`.
- core/traefik/compose.yaml:
  - command:
    - keep `--entrypoints.web.address=:80`.
    - replace `--entrypoints.traefik.address=:8080` with `--entrypoints.traefik-ui.address=:8080`.
    - add `--entrypoints.dozzle.address=:8082` and `--entrypoints.ping.address=:8090`.
    - keep `--api.dashboard=true` and `--ping=true`; add `--ping.entrypoint=ping`.
    - DELETE `--api.insecure=true`.
    - Leave the other flags unchanged.
    - Fix the comment: "dashboard and Dozzle on their own entrypoints, both behind admin-auth; ping on
      8090, not published, for Kuma".
  - ports: "80:80", "8080:8080" (comment `# host port = homelab.port`), and add
    "8082:8082" (comment `# dozzle, behind admin-auth`). Do not publish 8090.
  - labels (Traefik group), replace with:
    traefik.enable=true
    traefik.http.routers.traefik.rule=PathPrefix(`/`)
    traefik.http.routers.traefik.entrypoints=traefik-ui
    traefik.http.routers.traefik.service=api@internal
    traefik.http.routers.traefik.middlewares=admin-auth@docker
    traefik.http.middlewares.admin-auth.forwardauth.address=http://dashboard:8000/auth/verify
    The old `Host(traefik.${DOMAIN})`/web router goes, so traefik.lan is gone.
    The middleware is defined on traefik itself so it always exists while traefik runs. If the dashboard
    is down, auth fails closed.
  - homelab.* labels: unchanged (port stays 8080).
  - Kuma: `kuma.traefik.http.url=http://traefik:8090/ping` (name unchanged).
- tools/dozzle/compose.yaml:
  - remove the `ports:` block. Port 8082 is now published by traefik.
  - Traefik labels become:
    traefik.enable=true
    traefik.docker.network=proxy
    traefik.http.routers.dozzle.rule=PathPrefix(`/`)
    traefik.http.routers.dozzle.entrypoints=dozzle
    traefik.http.routers.dozzle.middlewares=admin-auth@docker
    traefik.http.services.dozzle.loadbalancer.server.port=8080
    The comment says "port 8082 via Traefik entrypoint, behind the dashboard login; no dozzle.lan".
  - No DOZZLE_AUTH_PROVIDER: rely on Traefik. Forward-proxy mode would trust a Remote-User header from
    anything on the proxy network.
  - homelab.port=8082 unchanged.
  - Kuma: `kuma.dozzle.http.url=http://dozzle:8080/healthcheck`. Fix the comment: internal address,
    because the published port needs a login. Today `/healthcheck` returns 200.
  - Everything else unchanged.
- Kuma networks: uptime-kuma is already on `proxy` (with traefik, dozzle and dashboard), so no change there.
- ideas/ntfy-auth.md (new): part B as its own note.
  - Title: "Put ntfy behind its own users".
  - Copy the ntfy bullets and the ntfy "watch out" item from ideas/admin-tools-login.md.
  - Publishers: qbit-watchdog.sh, ha-backup-check.sh, scrutiny-check.sh, backup.sh (incl. the root
    systemd failure units), seerr-route.py, and the Kuma ntfy-urgent notification.
  - Record Dan's 2026-10-14 answers as decided:
    - one `NTFY_ALERT_TOKEN` env token (Bearer) for all six publishers;
    - Dan sets the Kuma notification token and the iOS app login by hand;
    - NTFY_ALERT_TOPIC is no longer treated as a secret but stays in the env file.
- Do not move or edit ideas/admin-tools-login.md (the loop handles that).

New service: none. No new host ports: 8080 and 8082 change owner (both now traefik). 8090 is
container-internal only.
New env vars: None

Checks the builder must run:
- python3 -m py_compile core/dashboard/app/auth.py core/dashboard/app/main.py
- scripts/dc.sh <worktree>/core/traefik config -q; scripts/dc.sh <worktree>/tools/dozzle config -q;
  scripts/dc.sh <worktree>/core/dashboard config -q
- git grep -n -e 'api.insecure' -e 'dozzle\.lan' -e 'traefik\.lan' -e '8082:8080' -- ':!ideas'
  must return nothing, apart from deliberate doc mentions that the routes were removed.
- If fastapi is importable on the host (`python3 -c 'import fastapi'`), run a quick TestClient check
  from core/dashboard with test env vars set (a 32+ char secret, and a hash made with
  scripts/dashboard-passwd.py logic or a fake scrypt string):
  - /auth/verify with no cookie and X-Forwarded-Host `homelab:8082` → 302 to `http://homelab:8000/login`
  - X-Forwarded-Host `evil"host` → 401
  - valid cookie from auth.new_session() → 200
  If fastapi isn't importable, say so in the report. Do not build or start containers.

Docs:
- CLAUDE.md, Rules: "Traefik publishes 80, AdGuard 53" becomes "Traefik publishes 80, 8080 (its dashboard)
  and 8082 (Dozzle), AdGuard 53".
- CLAUDE.md, port table: 8080 = "traefik dashboard (entrypoint `traefik-ui`, dashboard login)".
  8082 = "dozzle (published by traefik, dashboard login)".
- docs/m1-core.md, Admin login: add `/auth/verify` (Traefik forward auth, middleware `admin-auth`, defined
  on traefik). It returns 200 with a session, else a 302 to `http://<same host>:8000/login`; it is open
  but only reports cookie validity.
  - Replace the "Only the dashboard is protected…" bullet: Dozzle and the Traefik dashboard now need the
    dashboard login (same cookie, one login per host name). Log in at :8000, then reopen the tile.
    `dozzle.lan` and `traefik.lan` were removed. ntfy is still open (`ideas/ntfy-auth.md`).
  - Note "add Secure and https in verify_redirect with HTTPS".
- docs/m1-core.md, Notes: the "Kuma monitors the published ports" bullet gets an exception. Traefik and
  Dozzle are checked internally (`http://traefik:8090/ping`, `http://dozzle:8080/healthcheck`) because
  their ports need a login.
- docs/restore.md: no change needed (traefik starts before dozzle there).

## Manual steps
1. Before `scripts/deploy-idea.sh admin-tools-login`, run `scripts/dc.sh tools/dozzle stop`.
   - Why: deploy starts the changed dirs in sorted order (core/dashboard, core/traefik, tools/dozzle).
     Traefik would fail to bind 8082 while the old Dozzle container still holds it.
   - Deploy then recreates dozzle without the port.
   - This is a terminal deploy: core/traefik is on the sensitive list.
2. After deploy, `scripts/dc.sh core/uptime-kuma restart` so the changed Kuma URLs take effect (m1 note).
   Then check `scripts/kuma-status.py traefik` and `scripts/kuma-status.py dozzle`.
3. Browser check:
   - Logged out, `http://homelab:8082` and `:8080` → redirect to the :8000 login.
   - After logging in, both open, and Dozzle's live logs stream.
4. Remove the dozzle.lan / traefik.lan AdGuard rewrites, if any are specific, and your bookmarks.
   AdGuard is manual-only.
5. Part B (ntfy-auth) is queued as ideas/ntfy-auth.md and will be planned by the loop after this merges.
