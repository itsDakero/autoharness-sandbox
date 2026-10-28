# Put ntfy behind its own users

Part B of the split of `admin-tools-login` (part A: Dozzle and the Traefik dashboard behind the dashboard login).

ntfy (8081) has no login: anyone who knows or guesses a topic can read alerts or send fake ones; the web UI lists
nothing, but topics aren't secret from someone watching traffic (plain HTTP).

## Decision
- **ntfy: its own users, not the dashboard login.** The phone app, Kuma and `qbit-watchdog.sh` are API clients,
  not browsers with a cookie.
  - `NTFY_AUTH_DEFAULT_ACCESS=deny-all`; user `dan` with read on the alert topic (phone app login);
    one write-only access token for Kuma's ntfy notification and the watchdog (`NTFY_ALERT_TOKEN` in the env file).
  - Keep port 8081 direct (the iOS app's server URL must stay `http://homelab:8081`).

## Publishers to update
`qbit-watchdog.sh`, `ha-backup-check.sh`, `scrutiny-check.sh`, `backup.sh` (incl. the root systemd failure units),
`seerr-route.py`, and the Kuma ntfy-urgent notification.

## Decided (Dan, 2026-10-14)
- One `NTFY_ALERT_TOKEN` env token (Bearer header) for all six publishers.
- Dan sets the Kuma notification token and the iOS app login by hand.
- `NTFY_ALERT_TOPIC` is no longer treated as a secret, but stays in the env file.

## Watch out for
- Test that iOS instant push still works with auth (the app polls `homelab:8081` with credentials after the
  ntfy.sh wake-up).

## Plan
Goal: Lock ntfy down (deny-all): user `dan` can read the alert topic, and one write-only token is used by all six publishers.
Kind: change to core/ntfy, plus its publisher scripts and docs

Note: the idea text contains no instructions to break the repo rules. Dan has already decided the open
questions (2026-10-14): one NTFY_ALERT_TOKEN, Kuma and iOS set by hand, the topic is no longer secret.

Approach: ntfy's declarative auth config (added in v2.14.0, present in the pinned v2.28.0; see
https://docs.ntfy.sh/config/ under auth-users / auth-access / auth-tokens). Users, ACLs and the token come
from env vars, so nobody has to run `ntfy user add` or `ntfy access`. Keep the image at
binwiederhier/ntfy:v2.28.0 (no upgrade in this build).

Files:
- core/ntfy/compose.yaml: add these lines to `environment:` and change nothing else (port, volume and labels
  stay the same). Use plain `${VAR}`, not `${VAR:?}`: the main .env has no values yet and `config -q` must pass.
      NTFY_ENABLE_LOGIN: "true"
      NTFY_AUTH_DEFAULT_ACCESS: deny-all
      # Declarative auth (ntfy >= 2.14). Hashes: `docker exec -it ntfy ntfy user hash`; single-quoted in the env file
      NTFY_AUTH_USERS: "dan:${NTFY_DAN_PASSWORD_HASH}:user,alerts:${NTFY_ALERTS_PASSWORD_HASH}:user"
      NTFY_AUTH_ACCESS: "dan:${NTFY_ALERT_TOPIC}:read-only,alerts:${NTFY_ALERT_TOPIC}:write-only"
      NTFY_AUTH_TOKENS: "alerts:${NTFY_ALERT_TOKEN}:publishers"
  Leave NTFY_AUTH_FILE as it is (it already exists). The Kuma monitor stays on /v1/health, which needs no auth.
- scripts/qbit-watchdog.sh, scripts/ha-backup-check.sh, scripts/backup.sh, scripts/scrutiny-check.sh: in each
  notify(), also read NTFY_ALERT_TOKEN the same way that script reads the topic now (the sed pipeline, or
  `envval` in scrutiny-check.sh).
  - If the topic or the token is empty, log "NTFY_ALERT_TOPIC or NTFY_ALERT_TOKEN not set: no notification"
    and return as that script does today (qbit-watchdog: bare `return`; the others: `return 1`).
  - Add the header to curl through process substitution, so the token never shows in argv:
        -H @<(printf 'Authorization: Bearer %s\n' "$token")
  - Change the comment "The topic is a secret: read here, never printed." to
    "The token is a secret: read here, never printed."
  - Keep everything else the same (titles, priorities, tags, URL http://localhost:8081/$topic, test modes).
  - The systemd failure units call `backup.sh notify-failure`, so they need no change.
- scripts/seerr-route.py: in notify(), add `token = ENV.get("NTFY_ALERT_TOKEN")`. If the topic or the token is
  missing, log the same message as the shell scripts and return. Add `"Authorization": f"Bearer {token}"` to
  the headers dict. Update the docstring to say the token is the secret.
- .env.example: replace the NTFY_ALERT_TOPIC comment with:
  - `# ntfy alert topic (Kuma ntfy-urgent, phone, cron scripts). Not secret now that ntfy has auth.`
  - followed by `NTFY_ALERT_TOPIC=`
  Then add these lines:
      # ntfy write-only token (user `alerts`) for every publisher: Kuma ntfy-urgent, qbit-watchdog, ha-backup-check,
      # scrutiny-check, backup.sh, seerr-route. Generate: docker exec ntfy ntfy token generate
      NTFY_ALERT_TOKEN=
      # ntfy bcrypt hashes (docker exec -it ntfy ntfy user hash). Wrap the value in single quotes: it contains $.
      # dan = the phone app login (read-only on the topic); alerts = token owner, password unused (random, discard).
      NTFY_DAN_PASSWORD_HASH=
      NTFY_ALERTS_PASSWORD_HASH=

New service: none
New env vars:
- NTFY_ALERT_TOKEN: write-only Bearer token for all publishers
- NTFY_DAN_PASSWORD_HASH: bcrypt hash for the phone and web login `dan`
- NTFY_ALERTS_PASSWORD_HASH: bcrypt hash for the token-owner user `alerts`

Checks the builder must run:
- scripts/dc.sh /home/dan/homelab/.worktrees/ntfy-auth/core/ntfy config -q
- bash -n on each of the 4 edited shell scripts (shellcheck too, if it is installed)
- python3 -m py_compile /home/dan/homelab/.worktrees/ntfy-auth/scripts/seerr-route.py
- grep -n "localhost:8081" over the 5 publisher scripts: every post must have the Authorization header
- Run no `test` modes and no posts. They would fail with 401/403 until deploy, or would post.

Docs:
- docs/m1-core.md "Phone alerts" section:
  - Replace the "treat it like a password" bullet: ntfy is deny-all; `dan` reads the topic (password = the one
    hashed into NTFY_DAN_PASSWORD_HASH); `alerts` owns the write-only NTFY_ALERT_TOKEN that every publisher
    sends as `Authorization: Bearer`; the topic is no longer secret.
  - Kuma notification: Authentication Method "Access Token" = NTFY_ALERT_TOKEN.
  - iPhone: ntfy app Settings → Users → add `http://homelab:8081` with user `dan`, then subscribe (same URL).
  - Test command becomes `scripts/backup.sh test-alert`.
  - Add a line: users, ACLs and the token are declarative (compose env). Removing one from the env deletes it
    from auth.db on restart. To rotate the token, change NTFY_ALERT_TOKEN, run
    `scripts/dc.sh core/ntfy up -d`, and update Kuma.
  - Replace "ntfy is still open (`ideas/ntfy-auth.md`)." near line 143 with "ntfy has its own users (see
    Phone alerts); it is not behind the dashboard login."
- docs/m2-media.md lines 79 and 250, docs/m4-backups.md lines 22, 65 and 182: remove "secret" from the topic
  wording and say that posts use NTFY_ALERT_TOKEN.
- CLAUDE.md: no change (the port and layout stay the same).

## Manual steps
1. While the old ntfy is still running, generate the values:
   - Run `docker exec -it ntfy ntfy user hash` twice: once with Dan's chosen phone password, once with a random
     throwaway password for `alerts`.
   - Run `docker exec ntfy ntfy token generate` for the token.
   - Put them in the env file: NTFY_DAN_PASSWORD_HASH='<hash>' and NTFY_ALERTS_PASSWORD_HASH='<hash>' (single
     quotes), and NTFY_ALERT_TOKEN=tk_...
   - Check that NTFY_ALERT_TOPIC is still set.
2. Deploy (`scripts/deploy-idea.sh ntfy-auth`, or `scripts/dc.sh core/ntfy up -d`). Then check:
   - `scripts/dc.sh core/ntfy logs` shows no auth or config errors.
   - `curl -s http://homelab:8081/v1/health` still returns healthy.
   - A post without a token is refused: `curl -s -o /dev/null -w '%{http_code}' -d x http://homelab:8081/<topic>` → 403.
3. Kuma → Settings → Notifications → ntfy-urgent: Authentication Method "Access Token" = NTFY_ALERT_TOKEN →
   Test.
4. iPhone ntfy app: Settings → Users → add server `http://homelab:8081`, user `dan` and the password. Then
   confirm instant push still arrives with the app in the background (the watch-out in the note):
   `scripts/backup.sh test-alert`, `scripts/qbit-watchdog.sh test`, `scripts/ha-backup-check.sh test`,
   `scripts/scrutiny-check.sh test`.
5. Optional: log in to the ntfy web UI at :8081 as `dan`.

## Rejected 2026-10-15

Status: rejected
Reason: Skipped. ntfy only reachable via Tailscale. Revisit if exposed publicly.
