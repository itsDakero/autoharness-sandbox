# Homelab Town, stage 1: the homelab as a live pixel-art town

Value: 3   (a fun, at-a-glance view of what the homelab and its agents are doing; Dan asked for it)
Effort: 3  (one read-only page, pixel-art canvas, data the dashboard mostly already has)
Risk: 1    (read-only view; changes no service, no secrets, no host setup)
Score: 9
Source: Dan 2026-10-25 (session with Claude; mockup in `docs/town-mockup.html`)

## Problem
The dashboard shows status as tiles and tabs. Dan wants the homelab to look like a game: a town where he can
watch the services and the agents (build loop, Hermes, ops-actions, cron jobs) at work.

## Proposal
- A read-only "town" page, served by the dashboard (`core/dashboard`, e.g. `/town`, behind the admin
  login like `/admin`) or as its own small service if the planner finds that cleaner. A canvas drawing, no
  framework; refreshes its data every few seconds from a JSON endpoint.
- Start from `docs/town-mockup.html`: reuse its building list, road routing, character movement, speech
  bubbles, dialogue box and town log. The mockup runs on a scripted demo; stage 1 replaces that with live data.
- Buildings = services (mapping in the mockup: Watchtower = uptime-kuma, Town Hall = dashboard, Library =
  jelu, Gym = fitness, Tailor = wardrobe, Arcade = leafgreen, Post Office = ntfy/Discord, Cinema = jellyfin,
  Arr Warehouse = radarr/sonarr/prowlarr/seerr, Tunnel Cave = qbittorrent + gluetun, Market =
  changedetection, Clinic = ops-actions, Guild Hall = build loop, Vault = backups, Construction Site =
  idea worktrees, Clock Tower = cron jobs, Observatory = Mac mini, City Wall = adguard). Lit windows =
  healthy, flicker = starting, dark + smoke = unhealthy/down, from the data the dashboard already uses
  (Docker health via the socket proxy, Kuma).
- Characters move when the real thing happens, from data that already exists:
  - build loop: planner/builder/reviewer from `ideas/` and the `idea/<slug>` branches (queued → planning,
    branch without a reviewed commit → building at the site, reviewed → ready flag on the site);
  - scout: leaves on a run, comes back when new `ideas/proposed/` notes appear;
  - medic: walks to a building for each new line in `$APPDATA_PATH/ops-actions/audit.jsonl` (read-only mount);
  - cron jobs: Clock Tower townsfolk; a ghost when a Kuma `cron-*` monitor is down;
  - Hermes: if there's a cheap signal for "answered on Discord" (its feed or logs), else leave Hermes idle.
  The town log and dialogue box show the same events in plain words.
- Art style, agreed with Dan: inspired by GBA-era handheld RPG overworlds, never copied (no ripped tiles,
  game names, logos or the games' own building designs). 16 px tile grid on a bigger map than the mockup;
  buildings with a tall tiled roof, a flat front wall, a centred door, mat and sign; tree borders, ledges,
  flower beds, a pond with a sandy edge; trainer-style characters about 16x20 px with 4-way walk cycles;
  a GBA-like palette with dark outlines; each agent has an original creature companion following it
  (e.g. a fox for the scout, a turtle for the reviewer, a spark sprite for Hermes). Day/evening/night tint
  from the real clock.
- A dashboard tile or link to the town. A short section in the dashboard's docs.

## Not in this stage
- EXP, levels, streaks (stage 2), badges and quests, the SSD "boss" (stage 3): later notes. The mockup's
  HUD, quest and badge panels stay out of stage 1 (or show as "coming soon" at most).
- No buttons that change anything: deploys and reviews stay on the existing Deploy/Proposed tabs.

## Notes
- Expect an art polish pass with Dan afterwards; correct data and movement matter more than perfect pixels.

## Plan
Goal: A read-only, admin-only `/town` page in the dashboard: the homelab drawn as a live pixel-art town, built from the mockup and fed by live data.
Kind: change to core/dashboard
Files:
- core/dashboard/app/town.py: new. `snapshot()` builds the `/api/town` JSON (described below).
- core/dashboard/app/main.py: add the `GET /town` page and the `GET /api/town` route. `all_services()` also stores the raw Kuma dict in `_cache["monitors"]`, which is never returned by `/api/services`. `to_service()` adds `"starting": "(health: starting)" in Status`.
- core/dashboard/app/static/town.html: new. A single file (canvas, no framework, no outside requests: drop the mockup's Google Fonts and use a monospace stack).
- core/dashboard/app/static/index.html: add a footer link `<a id="town" href="/town" hidden>Town</a>`, shown only when ADMIN.
- core/dashboard/compose.yaml: change the image to `homelab/dashboard:0.17.0`. Add the volume `${APPDATA_PATH}/ops-actions:/ops-actions:ro` and the env var `OPS_ACTIONS_DIR: /ops-actions`.
- docs/m1-core.md: add a section `## Town (/town)`.
- docs/README.md: change the town-mockup line to "the look the live /town page (docs/m1-core.md) is built from".

Routes:
- `/town`: copy `/admin`. Without a login it redirects 303 to `/login`. Otherwise it serves town.html (no-cache) and slides the session.
- `/api/town`: `dependencies=[Depends(auth.require_admin)]`, GET only. Nothing on the page writes anything (no buttons, no POSTs).

`/api/town` JSON. All parts are read in parallel with `asyncio.to_thread` for the file reads. Each part has its own `ok` flag, so one failure never fails the whole response.
- `services`:
  - All services, as `{id, name, status}`. Status is up, down, starting, unknown or maintenance: "starting" = Kuma pending or Docker health starting.
  - Comes from `all_services()`. On HTTPException: `{"ok": false}`.
- `buildings`: building id -> worst status of its members. Members missing from Docker/Kuma are skipped; if none are found the status is "unknown".
  - BUILDINGS map, from the note:
    - watchtower = uptime-kuma
    - hall = dashboard
    - library = jelu
    - gym = fitness
    - tailor = wardrobe
    - arcade = leafgreen
    - post = ntfy
    - cinema = jellyfin
    - warehouse = radarr, sonarr, prowlarr, seerr, radarr-remote, sonarr-remote
    - tunnel = qbittorrent, gluetun, plus Kuma qbittorrent-vpn
    - market = changedetection
    - clinic = Kuma `cron-ops-actions`
    - guild = Kuma `cron-idea-actions`
    - vault = Kuma `ha-backups`
    - clock = worst of Kuma `cron-*`
    - observatory = external `mac-mini`
    - wall = adguard
  - The site has no status; it gets its state from the build loop.
- `cron`: `[{name (without "cron-"), status}]` from the Kuma monitors `cron-*`.
- `loop`:
  - `queued`: titles from `ideas.queue()["ideas"]`.
  - `building`: slugs, from `ideas.deploys()["building"]`.
  - `ready`: slug and title, from `ideas.deploys()["ready"]`.
  - `parked`: count.
  - `runner`: ok, stale or missing.
- `scout`:
  - `proposed`: count of `ideas/proposed/*.md` matching `ideas.SLUG`.
  - `last_run`: mtime of `ideas/proposed/.last-scout` as ISO, or null.
- `ops`:
  - `paused`: whether the file `/ops-actions/PAUSE` exists.
  - `recent`: the last 20 parsed lines of `audit.jsonl` (time, service, action, result), read from only the last 64 KB. Bad or partial lines are skipped. A missing file gives `[]`.
- `hermes`: the status of the `hermes` container. There is no activity signal: his session/log dir is private, so it is not mounted.
- `now`: server ISO time.

town.html:
- Map: a 16 px tile grid, 40x24 tiles (640x384), scaled up with pixelated rendering. Reuse the mockup's buildings, labels, road routing (`door`/`route`), speech bubbles, typewriter dialogue box and town log. Re-lay them out on the bigger map.
- Remove the mockup's EXP, HUD, quests, badges and Deploy/Review buttons, and its EVENTS/IDEAS demo script.
- Art: the style agreed in the note. Buildings with a tall tiled roof, a flat front wall, a centred door, mat and sign; tree borders, ledges, flower beds, a pond with a sandy edge. Characters about 16x20 px with 4-way walk cycles. Each agent has an original companion: fox = scout, turtle = reviewer, spark = hermes, plus one each for planner, builder and medic. Dark outlines, and a day/evening/night tint from the browser clock. No game names, logos or copied tiles or buildings.
- Building looks: up = lit windows, starting = flicker, down = dark + smoke, unknown = plain (no smoke). The clinic shows a "CLOSED" sign when `ops.paused`.
- Polling: `/api/town` every 5 s, paused while the tab is hidden. The page diffs each response against the previous one:
  - A new slug in `building`: the planner walks hall -> guild, then the builder walks to the site and works there.
  - A slug moves to `ready`: the reviewer walks to the site and a flag goes up with the slug.
  - A slug leaves both lists: the site clears.
  - Queued notes but nothing building: the planner stands at the hall saying "Reading <title>".
  - `proposed` goes up or `last_run` changes: the scout walks out of the gate and back with "N proposals".
  - New `ops.recent` entries (newer `time` than the last one seen): the medic walks to that service's building (if it has one), says the action/result, and walks back.
  - A `cron` item is down: a ghost by the Clock Tower naming the job(s).
  - `hermes` is down: Hermes sleeps ("Zzz") at the Post Office; otherwise he idles there.
  - Any service status change: one town log line ("changedetection is unhealthy").
- The first response only sets the baseline: no replayed walks. The last 5 ops entries go to the log as history.

New service: None (no new port, labels or Kuma monitor).
New env vars: None (`OPS_ACTIONS_DIR` is set in compose.yaml, not in the env file).

Checks the builder must run:
- `scripts/dc.sh /home/dan/homelab/.worktrees/homelab-town/core/dashboard config -q`
- `python3 -m py_compile core/dashboard/app/*.py`
- A small Python check that imports `app.town` with temp `IDEAS_DIR`, `ACTIONS_DIR` and `OPS_ACTIONS_DIR`, covering:
  - a missing `audit.jsonl`;
  - a file with a bad line and a partial last line;
  - a missing `.last-scout`;
  - a missing `actions/status.json`.

  Each must give `ok` parts or `[]`, never an exception. Run it from `core/dashboard` with `PYTHONPATH=.` (fastapi/httpx are needed; if they aren't installed on the host, test `town.py`'s file helpers on their own).
- `grep -n "googleapis\|https://" core/dashboard/app/static/town.html` must return nothing.

Review focus:
- Docker API down (503), or Kuma unreachable/no key -> `services`/`buildings` are `ok:false` or unknown. The town shows a plain sign "Status unavailable" with no smoke and no ghosts. The loop, scout and ops parts still update.
- `audit.jsonl` missing, empty, mid-write (partial line) or large -> bad lines are skipped and only the 64 KB tail is read. The first load replays no medic walks, and the same entry never triggers a second walk on later polls.
- Tab hidden for hours, or several changes in one poll -> each character runs at most one queued walk at a time (a short queue, dropping the oldest). Every change still gets its log line. There is no unbounded timer or path build-up.
- Not logged in, or the session expires mid-poll -> `/town` redirects to login and `/api/town` returns 401. On a 401 the page stops polling and shows "Logged out: log in again" with a link to `/login`. The family page and `/api/services` stay unchanged (no `monitors` key returned).
- An empty queue, no proposals dir, or a missing `status.json` (runner missing) -> the site sits empty, the scout and planner idle at the guild, and the guild sign says "runner not reporting" when runner != ok.

Docs:
- docs/m1-core.md `## Town (/town)`: admin only, read-only; the data sources table (part -> source); the building map; the `/ops-actions:ro` mount; Hermes has no activity signal on purpose; stage 2/3 (EXP, badges) are later notes.
- docs/README.md: change the mockup line as above.
- No port table or CLAUDE.md changes.

## Manual steps
- Run `scripts/deploy-idea.sh homelab-town`. It rebuilds the dashboard as 0.17.0.
- Open `http://homelab:8000/town` (or click the admin footer link) and check the buildings against `/admin`.
- Art polish pass with Dan afterwards, as the note says.

Notes for Dan:
- Choices not spelled out in the note:
  - I left Hermes idle because his only activity data is his private session/log dir, which I didn't want to mount.
  - The Vault follows the ha-backups Kuma monitor: restic itself has no Kuma or dashboard signal yet.
  - Unmapped services (traefik, dozzle, scrutiny, omada) get town log lines but no building.
- No rejected idea matches this one.

## Review notes
1. `core/dashboard/app/static/town.html:605`: the ops baseline (`seenOps`) is only seeded when the first response has `ops.ok`. If the first poll returns `ops: {ok:false}` and a later one returns ok, up to 20 old audit lines go into the log and the medic makes up to 2 walks for them. This is unlikely because `read_ops` barely fails. Fix later by seeding on the first ok ops part, not on the first response.
2. `town.html:632`: the scout's trip fires whenever `proposed` goes up. That includes a Hermes proposal, which then shows as "The scout is back". The `last_run` signal alone would be more accurate if Dan cares.
3. `town.html:651`: after a Docker outage (hermes status "unknown"), "Hermes is awake" is logged on recovery even though he never slept. This is cosmetic.
4. `town.html:669-671`: if the tab is hidden and shown again while a fetch is in flight, a second poll can start at the same time. This is harmless because `!pollTimer` stops a second timer chain.
5. Art is at the "polish later" level, as the note expects. Characters are about 12x20 px with a 2-frame leg swap, and the building labels are overlays, not painted signs.

## Declined to judge
- Clock Tower flickering if Kuma reports a push monitor as pending: Kuma's own state, shown the same way as on /admin.
- Down containers still smoking when only Kuma is unreachable: they really are down per Docker, and the plan's "no smoke" covers the unknown status.
- `starting` field now appearing in admin `/api/services` and the Hermes status feed: the plan asked for it in `to_service()`. The family output (PUBLIC_FIELDS) is unchanged.
- How exact the GBA-style art is: the note says Dan will do an art pass afterwards.
- No Kuma monitor or tile for /town: the plan says no new service, port or monitor.
