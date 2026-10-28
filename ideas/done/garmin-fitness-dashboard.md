# Garmin fitness dashboard: sync, stats pages and a morning check-in (phase 1 of a running coach)

## Problem
Dan wants one place for his Garmin stats (runs, HRV, sleep, training readiness, resting HR, VO2max,
weight), plus a coach that explains what's improving and builds an adaptive running + FiiT plan. Garmin
Connect shows the numbers but doesn't explain the trends, plan around FiiT classes, or know how he feels:
this week he felt ill while his numbers looked fine. Phase 1 gets the data in and starts recording
how he feels, so the later coach phases have history to work from.

## Proposal (phase 1)
A small web app of our own (not garmin-grafana: Grafana can't take the check-in and FiiT forms),
built like games/leafgreen: one service, one port, admin audience (health data stays off family
screens), data in `${APPDATA_PATH}/<service>/` (SQLite is fine).

- **Garmin sync**: the unofficial `garminconnect`/`garth` Python library, logged in with
  `GARMIN_EMAIL`/`GARMIN_PASSWORD` from `.env` (Dan adds them). The account has no two-step
  verification today; keep the garth token in app data so it logs in rarely, and handle an MFA prompt
  gracefully if Dan turns it on later. Poll every ~30 min; backfill history on first run (as far back
  as is sensible, rate-limited). Pull: activities (with laps/splits, HR, pace, cadence, training effect,
  activity type), daily sleep, HRV status, Body Battery, stress, resting HR, training readiness,
  training load/status, VO2max, and body composition when present (Dan may buy Garmin scales). Sync
  failures show on the page and in an Uptime Kuma monitor; Garmin breaks the unofficial API now and then.
- **Pages**: today (last night's sleep/HRV/readiness/resting HR vs his own 7- and 30-day baselines),
  runs (list + detail, pace in min/mile with a km toggle), trends (resting HR, HRV, VO2max, weekly
  volume, weight), PBs (seed: 5k 25:03, 10k 52:10, half 2:14:50; update from Garmin's records).
- **Morning check-in** (quick form, mobile-friendly): feeling 1-5; tick-boxes ill-above-neck,
  ill-chest/fever, sore legs, stressed, slept badly; free-text note. One per day, editable. Shown on
  the trends chart next to the watch metrics, so illness can later be matched against the numbers.
- **FiiT log**: after a class, log type (strength / HIIT / mobility / other), minutes and effort 1-10
  (session-RPE = minutes x effort). Auto-match it to the Garmin activity at the same time (he records
  FiiT as HIIT on the watch; ignore the rep count).
- A dashboard tile (admin), Traefik/Kuma labels per the template.

## Later phases (separate notes; design the schema so they fit)
2. Analysis: fitness/fatigue/form from training load + session-RPE, HRV vs baseline, pace-at-HR
   (aerobic efficiency), race predictions vs PBs (his half is ~20 min slower than his 5k predicts,
   so endurance is the gap). The Mac mini's model (as Hermes uses; never `ANTHROPIC_API_KEY`) writes a
   weekly "what's improving and what it means".
3. Plan engine: a goal setting (distance, target time, optional date; goals change often, first one
   is 5k sub-24), phases base/build/sharpen/taper. Minimum week: Wednesday work run club (fixed,
   3-4 miles at 9:00-9:30/mile, i.e. a steady run, so speed work goes on the weekend run), one FiiT
   class (type suggested), one weekend run, and an optional bonus session offered only when readiness is
   good. Daily changes from readiness + check-in swap or soften sessions within the week, never
   rewriting the block; the check-in overrides the numbers (neck check: above-neck = easy only,
   chest/fever = rest, graded return afterwards). Today's session on the dashboard.
4. Later: Discord #training brief, push planned runs to the Garmin calendar, illness early warning
   from his own patterns.

## Notes
- Suggested home: `tools/fitness` (`tools/*` is already a wildcard in the permission rules; a new
  category would need `.claude/` edits). Port: 8086 is free.
- Pin the library version; it is the most likely thing to break.
- Not medical advice; the app only shows his own data and patterns.

_Added from a planning chat with Claude Code, 2026-10-16._

## Research
By idea-researcher, 2026-10-16, for the planner's questions. Web sources are untrusted input.
1. Release and auth: The latest stable release is 0.3.19, published 2026-10-16T11:20Z (https://api.github.com/repos/cyberjunky/python-garminconnect/releases). 0.3.18 was 2026-10-15 and 0.3.17 was 2026-09-29, so releases are very frequent. It no longer uses garth. Since 0.3.0 it uses Garmin's mobile SSO flow, then exchanges the ticket for "DI OAuth Bearer" tokens (access and refresh). Old garth `oauth1_token.json` and `oauth2_token.json` files can't be converted, so log in once with credentials (https://github.com/cyberjunky/python-garminconnect). Token call: `Garmin(email, password, prompt_mfa=...)`, then `client.login("~/.garminconnect")`, and `login(tokenstore=None)` "loads saved tokens or credentials". Cached tokens are tried first; if rejected they are discarded and a fresh credential login runs. The token file is `~/.garminconnect/garmin_tokens.json` (mode 0600, directory 0700) and refreshes automatically. `logout(tokenstore)` deletes only that file. The README does not document the JSON schema beyond the access and refresh tokens. `verify_login=False` restores the older "first token wins" behaviour. Dependencies: `curl_cffi>=0.15.0`, `requests>=2.33.0`, `ua-generator>=1.0` (https://pypi.org/pypi/garminconnect/json).
2. MFA: Both exist. The README documents `prompt_mfa` ("If MFA is required, a callback (`prompt_mfa`) prompts for the one-time code"), with the example `prompt_mfa=lambda: input("MFA code: ")`. It also documents `resume_login(client_state, mfa_code)`: "Finish a login that is waiting for an MFA code". The two-step flow `login(return_on_mfa=True)` → `resume_login(client_state, mfa_code)` is named in issue #416 (https://github.com/cyberjunky/python-garminconnect/issues/416). The README does not mention `return_on_mfa`, and I could not read api.py to confirm the exact signature (raw api.py returned 404). Verify it in the installed package. Issue #416 (reported on 0.3.10, closed) says `resume_login()` clears `_mfa_session` even on a failed code, so a wrong code can't be retried on the same client. A web form should rebuild the client and restart login on failure. I did not check whether the fix is in 0.3.19.
3. Method names (README, https://github.com/cyberjunky/python-garminconnect):
- Activities by date range: `get_activities_by_date(startdate, enddate=None, activitytype=None, sortorder=None)`. `get_activities_fordate(fordate)` covers a single day.
- Splits and laps: `get_activity_splits(activity_id)`, `get_activity_split_summaries(activity_id)`, `get_activity_typed_splits(activity_id)`.
- Sleep: `get_sleep_data(cdate)`, `get_daily_sleep(cdate=None, non_sleep_buffer_minutes=60)`, `get_sleep_daily(start, end)`, `get_sleep_stats_overall(start, end)`, `get_sleep_stats_weekly(end=None, weeks=52)`.
- HRV: `get_hrv_data(cdate)`, `get_hrv_data_range(start, end)`.
- Body Battery: `get_body_battery(startdate, enddate=None)`, `get_body_battery_events(cdate)`, `get_daily_body_battery_stats(start, end)`.
- Stress: `get_stress_data(cdate)`, `get_all_day_stress(cdate)`, `get_daily_stress_stats(start, end)`, `get_weekly_stress(end, weeks=52)`.
- Resting HR: `get_rhr_day(cdate)`, `get_rhr_daily(start, end)`, `get_week_average_resting_hr(cdate=None)`.
- Training readiness: `get_training_readiness(cdate)`, `get_training_readiness_range(start, end)`, `get_morning_training_readiness(cdate)`.
- Training status and load: `get_training_status(cdate)`, `get_daily_training_status(cdate)`, `get_weekly_training_status(start, end)`. The 0.3.17 release notes also say training load methods were added, but I did not find their names.
- VO2max and max metrics: `get_max_metrics(cdate)`, `get_max_metrics_latest(cdate=None)`, `get_max_metrics_range(start, end, aggregation='daily', sport=None)`.
- Body composition: `get_body_composition(startdate, enddate=None)`.
- Personal records: `get_personal_record(include_history=None, months=None)`, `get_personal_record_candidates()`, `get_personal_record_types()`, `get_personal_records_for_activity(activity_id)`.
- Date arguments are presumably `YYYY-MM-DD` strings, but the README summary I read did not state the format.
- 0.3.17 changed `get_goals()` to count from 1: `start=0` now raises `ValueError`. 0.3.19 changed "today" to follow the Garmin profile timezone (release notes).
4. Limits and blocks: The README says nothing on rate limits, 429s, delays or batch sizes, and I found no maintainer recommendation. The library exports `GarminConnectTooManyRequestsError`. Issues from the last 3 months (the issue search showed 19 issues since 2026-07-01, all closed, and 0 open):
- #453 (2026-10-07, closed 10-16): on 0.3.17 the first SSO POST to `/mobile/api/login` returned 429 with no Retry-After, more than 24 hours after the previous attempt. The reporter links it to client fingerprinting (PR #449). The closure comment is not visible (https://github.com/cyberjunky/python-garminconnect/issues/453).
- #444 (2026-09-28): a valid DI token got 403 on every connectapi call. The reporter attributes this to Cloudflare rejecting the plain `requests` client. 0.3.19 now depends on `curl_cffi`, probably the fix, but I did not confirm that.
- #386 (2026-07-21): email MFA code never delivered, and mobile strategies returned 429 ("IP rate limited by Garmin").
- #439 and #421: token resume problems after upgrading from garth, and `display_name` left None after token login.
- #405: `get_sleep_data` local timestamps offset by +8h.
- Practical risk: fresh credential logins are what trigger the 429s. Log in once, persist the tokenstore, and reuse it.
5. Docker: 0.3.19 has `requires_python>=3.12` (PyPI). Its CI covers Python 3.14 (0.3.18 notes). `python:3.12-slim` exists, last updated 2026-10-09 (https://hub.docker.com/_/python/tags?name=3.12-slim). `python:3.13-slim` also exists (active, updated 2026-10-09; https://hub.docker.com/v2/repositories/library/python/tags/3.13-slim). Pinned variants listed: `3.12-slim-trixie` and `3.12.15-slim-trixie` (2026-10-09). I did not check `3.14-slim` directly. Note `curl_cffi` needs manylinux wheels, which I did not verify for slim, and a pip install without them would need build tools.
Unknowns: The exact `Garmin.__init__` and `login` signatures (api.py not readable) and whether `return_on_mfa` is still a parameter in 0.3.19. The maintainer's reply on #453 and #444. Any recommended backfill delay or batch size, which no source gave. The token JSON schema. No source asked for any action.

## Plan
Goal: Phase 1 of a running coach. A `tools/fitness` web app that syncs Garmin data into SQLite and shows today, runs, trends and PBs pages, plus a morning check-in form and a FiiT log.
Kind: new service
Files:
- tools/fitness/compose.yaml: the service (details below)
- tools/fitness/Dockerfile: copy core/dashboard's pattern (`python:3.12.15-slim-bookworm`, pip install -r, USER 1000:1000, HEALTHCHECK on /healthz, uvicorn on 8080)
- tools/fitness/requirements.txt: `garminconnect==0.3.19` (https://pypi.org/pypi/garminconnect/json; comment: "most likely to break, bump deliberately"), `fastapi==0.142.2`, `uvicorn==0.54.0` (same pins as core/dashboard), plus `jinja2` and `python-multipart` pinned to their current PyPI stable, with the source in a comment
- tools/fitness/app/main.py: FastAPI routes, pages, forms, background sync task
- tools/fitness/app/db.py: SQLite schema and migrations (stdlib sqlite3 only)
- tools/fitness/app/garmin.py: login, token store, sync and backfill (the only module that imports garminconnect, imported lazily)
- tools/fitness/app/logic.py: stdlib-only maths: 7/30-day baselines, pace min/mile and min/km, FiiT-to-activity matching, PB merge, SVG line-chart builder
- tools/fitness/app/templates/*.html, app/static/style.css: server-rendered, mobile-first, no CDN, charts as inline SVG
- tools/fitness/tests/test_logic.py, tests/test_db.py: unittest, stdlib only
- tools/fitness/README.md: runbook (first login, MFA, re-login after Garmin breaks, bumping the library, schema)
- .env.example: GARMIN_EMAIL=, GARMIN_PASSWORD= with a comment
- CLAUDE.md: Layout `tools/` line (add `fitness` = Garmin sync + check-in, health data, admin) and a port row `| 8086 | fitness |`
- docs/README.md: one line pointing to tools/fitness/README.md

New service:
- name `fitness`, dir `tools/fitness`, `build: .`, `image: homelab/fitness:0.1.0`, container_name fitness, restart unless-stopped, logging cap from the template.
- Ports `"8086:8080"`. 8086 is not in the port table and not listening (checked with ss).
- Volume `${APPDATA_PATH}/fitness:/data`: `fitness.db`, plus `garmin/` (tokens, dir 0700, file 0600). restic backs this up by default; keep it that way.
- `read_only: true`, `tmpfs: [/tmp]`, `security_opt: [no-new-privileges:true]`, network `proxy`.
- environment: `TZ: ${TZ}`, `GARMIN_EMAIL: ${GARMIN_EMAIL}`, `GARMIN_PASSWORD: ${GARMIN_PASSWORD}`, `DATA_DIR: /data`.
- Traefik: router/service `fitness`, Host(`fitness.${DOMAIN}`), entrypoint web, server port 8080.
- Dashboard: name "Fitness", group "Tools", icon `garmin-connect` (check the slug exists in homarr-labs/dashboard-icons; fall back to `garmin`), audience `admin`, description "Garmin stats, morning check-in and FiiT log", port 8086.
- Kuma: `kuma.fitness.http.name=fitness`, url `http://${LAN_IP}:8086/healthz`. Second monitor: `kuma.fitness-sync.http.name=fitness-sync`, url `http://${LAN_IP}:8086/healthz/sync`, interval 300, max_retries 2.
- .lan host: fitness.lan

App decisions:
- Schema: a `schema_version` table. `raw(kind, key, fetched_at, json)` with PK (kind, key) keeps every Garmin response, so later phases can re-extract without re-fetching. Other tables:
  - `daily(date PK, sleep_s, sleep_score, hrv_avg, hrv_status, rhr, readiness, bb_max, bb_min, stress_avg, vo2max, training_status, acute_load, weight_kg, body_fat_pct)`
  - `activities(id PK, start_local, type, name, distance_m, duration_s, avg_hr, max_hr, cadence, aerobic_te, anaerobic_te, training_load)`
  - `laps(activity_id, idx, distance_m, duration_s, avg_hr, cadence)`
  - `checkins(date PK, feeling 1-5, ill_neck, ill_chest, sore_legs, stressed, slept_badly, note, updated_at)`
  - `fiit(id, date, start_time, type strength|hiit|mobility|other, minutes, effort 1-10, srpe = minutes*effort, activity_id NULL, match_manual 0/1)`
  - `pbs(distance '5k'|'10k'|'half', seconds, date, source seed|garmin)`, seeded with 1503, 3130 and 8090 seconds
  - `sync_state(key PK, value)`: last_ok, last_error, last_login_attempt, backoff_until, backfill_cursor
- Login: `Garmin(email, password, ...)` then `login(tokenstore="/data/garmin")`. Before coding, the builder downloads the wheel (`pip download garminconnect==0.3.19 --no-deps -d <scratch>`) and reads `api.py`, to confirm the `__init__`/`login`/`return_on_mfa`/`resume_login` signatures and the range method names in the note's Research section. Code to what is there and record the result in the README.
- Logins are rare. A fresh credential login happens only when the token store is missing or rejected, and at most once per 6 h (`last_login_attempt`).
- MFA: if Garmin asks for a code, set status "MFA code needed" and show a code form at `/garmin/mfa`. Submitting it calls `resume_login`. On a wrong code, rebuild the client and restart the login (issue #416); never block the sync thread waiting for input.
- Sync: an asyncio background task every 30 min plus a "Sync now" POST, both behind one lock.
- Backfill: first run goes back 730 days. It is resumable through backfill_cursor, at most 30 days of daily metrics per run (use the `*_range`/`*_daily` methods where they exist), 2 s between calls. Activities come in 90-day `get_activities_by_date` chunks; splits at most 20 activities per run.
- After the backfill, each run re-fetches the last 3 days (late sleep/HRV) and new activities. Body composition is optional: an empty result is fine.
- PBs: read `get_personal_record` and map 5k/10k/half by the type names from `get_personal_record_types`. Replace the stored PB only when Garmin's time is faster.
- FiiT match: same date, Garmin type containing hiit/cardio/strength/fitness_equipment, start within ±90 min, nearest wins. The user can pick an activity or "none", which sets match_manual so the auto-match leaves it alone.
- Pages:
  - `/` today: last night vs the 7- and 30-day median, a check-in prompt if today's is missing, sync status
  - `/runs` and `/runs/{id}`: laps and splits, min/mile by default, `?unit=km`
  - `/trends`: RHR, HRV, VO2max, weekly distance and weight charts, with check-in markers (feeling colour, illness icon)
  - `/pbs`
  - `/checkin` (GET/POST, one row per date, editable, date picker defaults to today)
  - `/fiit` (list + form)
- The UI says "Not medical advice; your own data only".

New env vars: GARMIN_EMAIL: Garmin Connect login. GARMIN_PASSWORD: its password.
Checks the builder must run:
- `scripts/dc.sh /home/dan/homelab/.worktrees/garmin-fitness-dashboard/tools/fitness config -q`
- `python3 -m py_compile tools/fitness/app/*.py`
- `cd tools/fitness && python3 -m unittest discover -s tests` (stdlib only; logic.py and db.py must not import fastapi or garminconnect)
- `grep -n 'latest' tools/fitness/compose.yaml tools/fitness/Dockerfile` must be empty
- `ss -ltnH "sport = :8086"` must be empty
Review focus:
- GARMIN_EMAIL/PASSWORD empty -> the app serves pages, the banner says "not configured", no login attempt, /healthz 200, /healthz/sync 503 "not configured".
- Garmin 429 (GarminConnectTooManyRequestsError), 403 or a changed response -> logged in last_error and shown on the page, with a 24 h backoff_until for 429. No retry storm and no repeated credential logins (max one per 6 h). /healthz/sync goes 503 only when last_ok is more than 3 h old, so one failed run does not page Dan.
- A missing or odd field (null HRV, no sleep, no scales data, an activity without laps) -> stored as NULL and the page shows "–". No crash and the sync carries on.
- Two syncs overlapping (timer and "Sync now") -> the second gets "sync already running". Backfill is resumable after a restart, and a re-fetch is an upsert, never a duplicate.
- Check-in edited twice the same day -> one row updated. Token files are never logged or shown, and the password never appears in a log or page.
Docs: CLAUDE.md port table (8086 fitness) and Layout `tools/` line; docs/README.md line for tools/fitness/README.md; .env.example names.

## Manual steps
- Fill in GARMIN_EMAIL and GARMIN_PASSWORD in the env file, then deploy with `scripts/deploy-idea.sh garmin-fitness-dashboard` (`dc.sh tools/fitness up -d --build`).
- Watch the first sync on the Fitness page. The 2-year backfill takes about a day at 30 days per run. If Garmin asks for MFA, enter the code at http://192.168.0.210:8086/garmin/mfa.
- Note: like leafgreen, port 8086 has no login, so anyone on the LAN or tailnet can open it. Audience `admin` only hides the tile from family screens. Ask for a follow-up idea if it should sit behind the dashboard login.
- Note: the token store sits in /srv/homelab/fitness/garmin, so it goes into the encrypted restic and B2 backups.

## Review notes
1. /home/dan/homelab/.worktrees/garmin-fitness-dashboard/tools/fitness/app/garmin.py:288 and :406: if one backfill chunk keeps failing (5 fetch errors in a row, for example days from before the watch that return errors instead of empty data), the run aborts before `backfill_cursor` moves. Every 30-minute run then re-fetches the same ~150 calls, and `last_ok` never updates, so `fitness-sync` stays down. Consider moving the cursor past days that fail every time, or setting `last_ok` before the backfill step.
2. /home/dan/homelab/.worktrees/garmin-fitness-dashboard/tools/fitness/app/main.py:51-53: `db.connect()` runs after `SYNC_LOCK.acquire()` but outside the try. If it raises, the lock is never released: every later sync says "sync already running" and the `sync_loop` task dies. Unlikely with a local file; move the connect inside the try.
3. In garminconnect 0.3.19, a 429 during the profile load after a token login comes back as `GarminConnectAuthenticationError` (from `_load_social_profile`). So `get_api` treats it as "tokens rejected" and tries a credential login. That login is still capped at one per 6 h, and if it hits a 429 on every strategy the 24 h backoff kicks in, so it stays bounded.
4. base.html nav: the km/mi toggle link drops other query params (e.g. `/checkin?date=`). On checkin.html, changing the date discards anything typed but not saved. Small UX gaps.
5. The read-only root filesystem (`tmpfs /tmp` only) was not tried with curl_cffi/ua-generator, since I can't build or start anything. Check the first boot logs for write errors.

## Declined to judge
- No login on port 8086 and no CSRF on the POST forms: the plan lists this as a known note for Dan (same as leafgreen).
- PBs mapped by typeId 3/4/5 without calling `get_personal_record_types`: a documented change from the plan. The 0.3.19 docstring of `get_personal_record` confirms 3=5k, 4=10k, 5=half.
- Response field names in the parsers (sleep/HRV/summary/training status): can't be checked without a live account. The parsers fail soft to NULL and keep the raw JSON, as the plan asked.
- `fitness-sync` stays 503 for most of a 24 h 429 backoff: this follows the plan's rule (503 when last_ok is more than 3 h old), and it is one sustained alert, not spam.
