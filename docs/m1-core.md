# M1 core services – runbook

## Access
- Dashboard: `http://192.168.0.210/` (any device), `http://homelab/` (tailnet; LAN only if the
  router resolves hostnames), `http://home.lan/` (devices using AdGuard DNS).
- Services: same host + port from the CLAUDE.md port table, or `http://<name>.lan`.
- `/` = family view (audience=family, no login), `/admin` = everything, behind a login (see Admin login below).

## Bring-up (first time)
1. `sudo ./bootstrap.sh` – frees port 53 (systemd-resolved stub off) and creates `/srv/homelab`.
   Log out/in afterwards so the docker group applies.
2. `cp .env.example .env` and check the values.
3. `scripts/core-up.sh` – creates the `proxy` and `socket-proxy` networks, app data dirs, and
   starts docker-socket-proxy → traefik → adguard → ntfy → uptime-kuma → dashboard.
   AutoKuma is skipped while `KUMA_PASSWORD` is empty.
4. AdGuard wizard at `http://192.168.0.210:3000`: keep web UI on **3000** and DNS on **53**,
   create the admin user. Put it in `.env` (`ADGUARD_USERNAME`, `ADGUARD_PASSWORD`).
5. `core/adguard/apply-rules.sh` – installs the `*.lan` rewrite (tailnet clients get the
   Tailscale IP, everyone else the LAN IP).
6. Uptime Kuma at `http://192.168.0.210:3001`: create the admin user, then
   Settings → API Keys → add. Put them in `.env` (`KUMA_USERNAME`, `KUMA_PASSWORD`, `KUMA_API_KEY`).
7. `scripts/core-up.sh uptime-kuma dashboard` – starts AutoKuma, gives the dashboard status.
8. Admin login: `scripts/dashboard-passwd.py` and the session secret into `.env` (see Admin login below),
   then `scripts/dc.sh core/dashboard up -d`.

## Day to day
- One service: `scripts/dc.sh core/<service> up -d` / `logs -f` / `down`.
- Upgrade: bump the pinned tag in compose.yaml, `scripts/dc.sh core/<service> up -d`.
- New service: copy `templates/compose.yaml`, take a free port, add it to the CLAUDE.md table.
  AutoKuma creates the monitor; the dashboard picks up the tile automatically.

## Outside the server
- **Router (Virgin Hub)**: DHCP reservation for the server's `enp2s0` MAC → 192.168.0.210.
  No DNS change, no port forwards.
- **Tailscale admin console → DNS**: add nameserver `100.78.185.81`, "Restrict to domain" `lan`;
  MagicDNS on. **Machines → homelab → Disable key expiry.**

## Notes
- Published ports bypass UFW: everything above is reachable from the LAN and tailnet.
- Uptime Kuma monitors the published ports (`http://192.168.0.210:<port>`), the same path family
  devices use. The dashboard matches monitors named `<container>` or `<container>-*` and shows
  the worst status. A stopped container shows as down immediately.
  Exception: Traefik and Dozzle are checked internally (`http://traefik:8090/ping`,
  `http://dozzle:8080/healthcheck`) because their ports need a login.
- A container can't reach a port published by another container on the *same* network (Docker
  sends that via the host INPUT chain, which UFW drops). So Kuma's checks leave via its own
  `monitor` network (`gw_priority`), and its self-check uses `localhost`.
- AutoKuma 2.0.0 doesn't re-login after Uptime Kuma restarts ("You are not logged in" in its
  logs). Compose restarts it together with Kuma; if Kuma restarts any other way, run
  `scripts/dc.sh core/uptime-kuma restart autokuma`. Fixed upstream in 2.1.0 (still RC).
- After changing a Kuma monitor's URL, restart uptime-kuma (`scripts/dc.sh core/uptime-kuma restart`).
  Kuma keeps the old URL's `/metrics` series until then. The dashboard uses the first series and
  logs a warning.
- uptime-kuma is also on `socket-proxy` for Docker-container monitors. Its Docker host `socket-proxy`
  (tcp://docker-socket-proxy:2375) is defined by AutoKuma labels on uptime-kuma. A docker monitor uses
  `kuma.<id>.docker.docker_container=<container>` and `docker_host_name=socket-proxy`.
- AdGuard runs as root: its first launch needs root or an ambient CAP_NET_BIND_SERVICE.
- After changing `/etc/resolv.conf`, restart docker (bootstrap.sh does) or pulls/builds fail DNS.

## Phone alerts (Kuma → ntfy, urgent)
- Topic: `homelab-alerts-<random>`. Not in the repo; it's in Kuma's notification and on the phone.
  Anyone who knows it can read or post, so treat it like a password.
- Kuma → Settings → Notifications → Setup Notification: type **ntfy**, name `ntfy-urgent`,
  **Server URL `http://ntfy`** (the form defaults to `https://ntfy.sh`; change it), the topic,
  priority **5**, tick **Default enabled** and **Apply on all existing monitors**.
- AutoKuma attaches it to every monitor it manages via `AUTOKUMA__DEFAULT_SETTINGS`
  (`*.notification_id_list: {"1": true}` in `core/uptime-kuma/compose.yaml`). `1` is the
  notification's Kuma id. If you recreate the notification, it gets a new id, so update it there
  (`scripts/kuma-status.py` shows each monitor's notifications).
- iPhone (Tailscale on): ntfy app → **+** → topic → **Use another server** `http://homelab:8081` → Subscribe.
  The server URL must match `NTFY_BASE_URL` exactly: iOS push is keyed on sha256(URL/topic) via ntfy.sh.
- Test: `curl -d test -H 'Priority: urgent' http://homelab:8081/<topic>`, or the Test button in Kuma.

## Cron dead-man's switch
- Every cron job in `scripts/install-cron.sh` runs as `scripts/cron-run.sh <name> <timeout-secs> [--ok codes] <cmd>`.
  It kills the job at the timeout, logs the output to syslog and pushes the job's Kuma push monitor `cron-<name>`:
  up, or down with "exit N: <last line>" / "timed out after Ns". Kuma's `ntfy-urgent` then alerts, also when a job
  stops running (no push within the interval).
- Logs: `journalctl -t cron-<name>`. Kuma down or secret unset: logged, job unaffected, its rc kept.
- Push throttle: on a status change at once, otherwise at most one push per 5 min (state in
  `~/.local/state/homelab/cron-run/<name>.last`).
- Intervals (AutoKuma labels on `core/uptime-kuma`): every-minute jobs (qbit-watchdog, idea-actions, seerr-route)
  600 s; ops-actions (every 5 min) 900 s; daily jobs 93600 s (26 h); weekly jobs (arr-missing-search, storage-cleanup, image-check, fitness-weekly)
  691200 s (8 d). Kuma 2.x caps intervals at 2073600 s.
- `--ok 0,1`: ha-backup-check, scrutiny-check, disk-space-check, cert-expiry-check, jellyfin-library-check and self-check exit 1 after sending their own
  alert, so exit 1 counts as up (no double alert). Crashes (other codes), timeouts and missed runs still alert.
- Token: `<KUMA_CRON_PUSH_SECRET><suffix>`, exactly 32 letters/digits (Kuma rejects anything else, and AutoKuma's
  sync then stalls). Secret: 16 hex (`openssl rand -hex 8`); suffix: the job name without hyphens, padded with `0` or
  cut to 16 (`arr-missing-search` → `arrmissingsearch`, `card-prices` → `cardprices000000`). Suffixes must stay unique.
  Secret in the env file (invalid length: cron-run.sh logs and skips the push; unset = monitors go
  down, the visible signal). Push URL: `http://127.0.0.1:3001/api/push/<token>`.
- Add a job: `scripts/cron.d/<name>.cron` (comments + one crontab line, `$R` and `$REPO` literal, 7th field = name)
  plus `core/uptime-kuma/compose.d/cron-<name>.yaml` (the 4 labels `name`, `push_token` = secret + its suffix,
  `interval`, `max_retries=0`). `install-cron.sh` reads the folder; `scripts/dc.sh` merges the fragments. Run
  `core/uptime-kuma` only through `dc.sh`, or the cron labels are dropped and AutoKuma (ON_DELETE=delete) deletes
  the monitors. After a deploy `scripts/install-cron.sh --check` should print "cron: in sync".
- Dashboard tile "Cron jobs" shows the monitors `cron-*`; `scripts/kuma-status.py cron` lists them.

## Dashboard widgets (v1)
- Backend (`core/dashboard/app/widgets.py`) fetches each widget's data and caches it (live ~3 s,
  others ~25 s, failures too); the browser gets display fields only, never credentials. Any error →
  `{"ok": false}` → that card shows "unavailable"; the rest of the page is unaffected. Errors are logged
  (`scripts/dc.sh core/dashboard logs`, "widget … unavailable").
- Browser polls live widgets every 5 s, the rest every 30 s; paused while the tab is hidden.
- The page sets `<meta name="referrer" content="no-referrer">` (qBittorrent's CSRF check 401s tile
  clicks otherwise; see `docs/m2-media.md`).
- Admin look (0.13.0): always dark command-center theme scoped to `body.admin` (family view unchanged); Overview opens with a KPI strip (services up, CPU, RAM, GPU, VPN) fed by the existing services/health/vpn polls; header shows overall status + clock; service group headings show up counts.

| Widget | View | Source | Refresh |
|---|---|---|---|
| Downloads | admin | qBittorrent `http://gluetun:8083` (Web UI login, `QBITTORRENT_USERNAME`/`PASSWORD`): unfinished torrents (top 8), speed, ETA, evening limit = alternative speed mode; the pill toggles it (`POST /api/widgets/downloads/limit`: same-origin JSON + admin session; schedule untouched, a manual flip lasts until the next scheduled switch or a qBittorrent restart) | 5 s |
| VPN | admin | Gluetun control server `http://gluetun:8000` (`/v1/vpn/status`, `/v1/publicip/ip`): Protected = running + public IP found through the tunnel; exit city/country | 30 s |
| Now playing | admin | Jellyfin `/Sessions` (`JELLYFIN_API_KEY`): user, device, title/episode, position, paused, Direct play / Direct stream / Transcoding (HW) | 5 s |
| Requests | admin | Seerr `/request` (`SEERR_API_KEY`): waiting for approval, in progress (download % from the arr queue, else "Searching"), recently available; titles/posters via Seerr's TMDB lookup, cached a day | 30 s |
| Server health | admin | Host-wide `/proc/stat`, `/proc/meminfo`, `/proc/loadavg`, `/proc/uptime` (not namespaced); CPU package temp from `/sys/class/hwmon` (coretemp); disks via `statvfs` on read-only mounts (`HEALTH_DISKS`: System = empty `${APPDATA_PATH}/dashboard`, Media = `${MEDIA_PATH}`); GPU via `nvidia-smi` (util, NVENC/NVDEC %, VRAM, temp, power, encode sessions) | 5 s |
| Recently added | admin | Jellyfin `/Items` as an admin user, newest movies + episodes grouped by series (episodes within a week of the newest count as "new"); `720p` = remote libraries | 30 s |

| New to watch | family | Same Jellyfin query, **main libraries only** (the remote 720p copies aren't in the household's libraries), 8 newest; poster opens the item in Jellyfin; "Added today / yesterday / N days ago" | 30 s |
| Requests | family | Same Seerr lists, household-level: title, year, poster and Ready to watch / On its way / Waiting for approval. No usernames, no progress; a title asked for twice shows once | 30 s |

- Family view (`/`, no login): app tiles first (no status dots), then New to watch and Requests. It only calls
  `/api/services`, `/api/family/*` and the poster proxy, never `/api/widgets/*`; the family endpoints
  return only the fields above.
- Posters: TMDB images load straight from `image.tmdb.org` (public, no key); Jellyfin posters go
  through `/api/img/jellyfin/<32-hex id>` (backend fetches with the key, browser caches a day).

- Gluetun's control server is not published; it's reachable only on the `proxy` network, and needs an
  API key (`GLUETUN_API_KEY`, sent as `X-API-Key`) for the two routes above only. See `docs/m2-media.md`.
- Server health needs no Docker API access: read-only root filesystem (`/tmp` tmpfs), both disk mounts
  `:ro` and never read (statvfs only), GPU through the nvidia runtime with driver capability `utility`
  only (nvidia-smi; no compute/video libraries), no extra capabilities, `no-new-privileges`, uid 1000.
  No GPU / missing mount → that row shows "unavailable"; bars turn amber at 75%, red at 90%.
- Checked 2026-10-04 (0.2.1; Stage B on 0.3.2 with sample sessions; Stage C on 0.4.1 incl. sample high load / no GPU; Stage D family view on 0.5.0 at 390 px, no admin calls, no usernames/ports/IPs/torrent names in its text): phone (390 px) and desktop, light and dark, no horizontal scroll; forced
  API failure → both cards "unavailable", tiles still load; family view has no widgets.
- Checked 2026-10-05 (0.6.0 login, on a throwaway copy with test credentials): family page open with 2 tiles and no
  admin calls; `/admin` → login, `/api/widgets/*` 401 without a session; login, 30-day HttpOnly/Lax cookie (not
  readable from JS), session gone → back to login, logout; lockout after 5 failures, direct and via Traefik with a
  forged `X-Forwarded-For`; restart lifts it; cross-site posts 403; phone (390 px) and desktop, light and dark.

## Admin login
- One user. `.env`: `DASHBOARD_ADMIN_USERNAME`, `DASHBOARD_ADMIN_PASSWORD_HASH` (from `scripts/dashboard-passwd.py`:
  scrypt, random salt; hex and colons only so compose leaves it alone) and `DASHBOARD_SESSION_SECRET`
  (`openssl rand -hex 32`). Any of them missing/invalid → the login refuses everyone ("not set up"); the family
  page is unaffected. Code: `core/dashboard/app/auth.py`.
- Login required: `/admin`, `/api/widgets/*`. Open: `/`, `/api/family/*`, `/api/img/jellyfin/*` (posters by id),
  `/healthz`. `/api/services` is open but without a session lists only family tiles, without status.
- Session: cookie `homelab_admin` = expiry + HMAC-SHA256 (secret; user, expiry, password hash). HttpOnly,
  SameSite=Lax, Path=/, 30 days, renewed on every `/admin` visit. Not `Secure` while the site is HTTP – add it
  with HTTPS. Cookies ignore ports, so the browser also sends it to the other services on the same host name;
  they don't use it. One login per host name (IP, `homelab`, `home.lan`, Tailscale IP).
- Login/logout posts with another site's `Origin` → 403. The login page has no `no-referrer` meta (Chrome would
  send `Origin: null`); logout accepts `null` (the admin page has the meta; a forced logout is harmless).
- Limits (in memory): 5 failures per client IP in 15 min → that IP locked 15 min; 20 failures from all clients
  in 15 min → login locked for everyone for 15 min; each failure answers after ~1 s. Via port 80 the client IP
  is the last `X-Forwarded-For` entry, trusted only when the request comes from the `traefik` container.
  Logs: "Admin login from / failed from / locked out" (`scripts/dc.sh core/dashboard logs`); never the password.
- **Locked out** ("Too many failed attempts"): `scripts/dc.sh core/dashboard restart` clears all counters and
  lockouts. Sessions survive (they're in the cookie).
- **Change the password**: run `scripts/dashboard-passwd.py`, replace the line in `.env`,
  `scripts/dc.sh core/dashboard up -d`. Every device is logged out.
- **Log out every device** (lost phone): new `DASHBOARD_SESSION_SECRET` in `.env`, `scripts/dc.sh core/dashboard up -d`.
- Dozzle (8082) and the Traefik dashboard (8080) also need this login, through Traefik forward auth: middleware
  `admin-auth` (defined on the traefik container) calls `GET /auth/verify` on the dashboard. It returns 200 with a
  valid session, else a 302 to `http://<same host>:8000/login`; it is open but only reports cookie validity.
  Same cookie, one login per host name: log in at :8000, then reopen the tile. Both ports are Traefik entrypoints
  (`dozzle`, `traefik-ui`); nothing reaches the containers without passing the middleware. `dozzle.lan` and
  `traefik.lan` were removed (a second login flow wasn't worth it). With HTTPS: add `Secure` and https in
  `verify_redirect`.
- ntfy is still open (`ideas/ntfy-auth.md`).
- Container logs are capped per service in compose (`logging:` json-file, 10m x 3, from `templates/compose.yaml`).
  The cap takes effect when a container is recreated (`dc.sh <dir> up -d`); old oversize logs are dropped then.
  adguard and omada are left out on purpose (always-manual); Dan adds the block to them by hand if wanted.

## Town (/town)
The homelab as a live pixel-art town. Admin only (same login as `/admin`; `/town` redirects to `/login`,
`/api/town` returns 401) and read-only: no buttons, no POSTs. One file, `app/static/town.html` (canvas, no
framework, no outside requests); the data is `GET /api/town` every 5 s (paused while the tab is hidden), built by
`app/town.py`. Each part has its own `ok`, so a failing source blanks only its part. The look comes from
`docs/town-mockup.html`.
- Data sources: `services`/`buildings`/`cron` = the dashboard's Docker (socket proxy) + Kuma data; `loop` =
  `ideas/` queue + the runner's `status.json` (`ideas.deploys()`); `scout` = count of `ideas/proposed/*.md` +
  mtime of `ideas/proposed/.last-scout`; `ops` = `PAUSE` + the last 20 lines (from the last 64 KB) of
  `audit.jsonl`, via the **`${APPDATA_PATH}/ops-actions:/ops-actions:ro`** mount; `hermes` = his container status.
- Buildings: Watchtower = uptime-kuma, Town Hall = dashboard, Library = books, Gym = fitness, Tailor = wardrobe,
  Arcade = leafgreen, Post Office = ntfy, Cinema = jellyfin, Arr Warehouse = radarr/sonarr/prowlarr/seerr (+
  remote pair), Tunnel Cave = qbittorrent + gluetun + Kuma `qbittorrent-vpn`, Market = changedetection,
  Clinic = Kuma `cron-ops-actions` ("CLOSED" when PAUSE exists), Guild Hall = Kuma `cron-idea-actions`, Vault =
  Kuma `ha-backups` (restic has no signal yet), Clock Tower = all Kuma `cron-*`, Observatory = `mac-mini`,
  City Wall = adguard. The Construction Site has no status: it shows the build loop. Traefik, dozzle, scrutiny and
  omada have no building (a town log line on a status change only).
- Lit windows = up, flicker = starting, dark + smoke = down, plain = unknown. Docker or Kuma unreachable: a
  "Status unavailable" sign, no smoke or ghosts; loop, scout and ops still update.
- Hermes has no activity signal on purpose (his session/log dir is private and not mounted): he idles at the
  Post Office, asleep when his container is down.
- The first response is only the baseline (no replayed walks; the last 5 ops entries go to the log).
- Later stages (separate notes): EXP and streaks, badges and quests, the SSD "boss".

## Healthchecks
Every service has one: the image's own `HEALTHCHECK`, or the block from `templates/compose.yaml` (interval 60s,
timeout 10s, retries 3, start_period 120s). Use a tool the image already has (curl/wget/python/the app's CLI), the
app's unauthenticated health URL else its port; never install packages. The dashboard shows a running container
whose Docker status says `(unhealthy)` as down (`(health: starting)` or no check: Kuma decides as before).
Each check below was run in its live container (`docker exec <name> <test>`) on 2026-10-25 and passed.

| Service | Check (inside the container) |
|---|---|
| ntfy | `wget` `/v1/health`, grep `"healthy":true` |
| traefik | `wget --spider http://127.0.0.1:8090/ping` |
| docker-socket-proxy | `wget` `http://127.0.0.1:2375/_ping`, grep OK |
| radarr, radarr-remote | `curl` `:7878/ping` |
| sonarr, sonarr-remote | `curl` `:8989/ping` |
| prowlarr | `curl` `:9696/ping` |
| qbittorrent | `curl` `http://127.0.0.1:8083/` (shares gluetun's network; gluetun and `depends_on` untouched) |
| seerr | `wget` `:5055/api/v1/status` |
| changedetection | `python3` urllib on `:5000/` |
| scrutiny | `curl` `:8080/api/health` |
| hermes | `python3` scans `/proc/*/cmdline` for the `hermes_cli ... gateway run` process (no Discord or model call; tighter than a bare "gateway" match, which also hits the s6 supervisor) |

Already healthy from image or compose, left alone: dashboard, omada, uptime-kuma, jellyfin, gluetun, fitness,
wardrobe, leafgreen, dozzle, ha-backups. Skipped: autokuma (not a web service, no port); adguard (always-manual,
like the logging cap: recreating it drops DNS briefly; Dan adds `wget --spider http://127.0.0.1:3000/` by hand if
wanted; omada already has the image's own). No image lacked a tool.
