# FPL model, stage 1: snapshot collector for FPL, odds and xG data

Value: 4   (the history the FPL model needs can't be fetched later: deadline-time flags, prices and odds aren't archived anywhere)
Effort: 2  (scheduled pulls into dated Parquet files; no model, no web page yet)
Risk: 1    (new isolated service, read-only public APIs, own data dir)
Score: 16
Source: Dan 2026-10-25 (session with Claude; design in `reports/FPL points prediction model.md`,
notes in `research_notes/FPL points prediction model/data_and_implementation.md`)

## Problem
Dan wants his own FPL expected-points model (FPL Review style, plus betting odds, xG, chips; five stages,
2-5 wait in `ideas/waiting/`). The model needs a per-gameweek history of what was known at each deadline:
injury flags, `chance_of_playing_*`, prices, FPL's `ep_next`, and match odds. The FPL API only serves the
present and vaastav's archive now updates three times a season (and its `xP` leaks post-match data), so
every week not collected is lost.

## Proposal
- New service `tools/fpl/` (this stage: the collector only; stage 2 adds the web page). Python, pinned
  image, logging cap, healthcheck as in `templates/compose.yaml`. Data in `${APPDATA_PATH}/fpl/`.
  No web UI yet, so no published port, Traefik or dashboard tile in this stage (stage 2 takes port 8092).
  The planner picks the run model (long-running scheduler in the container vs `scripts/cron-run.sh` jobs
  running the container), whichever fits the repo's existing scheduled jobs best.
- Pulls (each one its own job with a Kuma push monitor, via the cron-run pattern if cron):
  - FPL `bootstrap-static` every 2 h; `fixtures` daily; after each gameweek finishes, `event/<gw>/live`
    and `element-summary/<id>` for all players. Polite: a User-Agent, small delay between player calls.
  - The Odds API (`soccer_epl`, markets `h2h` and `totals`, UK region), once a day plus once ~2 h before
    each gameweek deadline (deadline from `bootstrap-static`). Free tier: 500 credits a month; log the
    `x-requests-remaining` header and stop pulling below a floor. Key from the env file
    (`ODDS_API_KEY`, add it to `.env.example`); with no key, skip the odds pull and log it once per run.
    Dan signs up and adds the key by hand.
  - Understat EPL player and team match xG weekly, via `soccerdata` (pin the version).
- Storage: raw JSON responses gzipped by source/date, plus tidy Parquet tables per source and pull time
  (players, fixtures, live, odds). A short README in `tools/fpl/` lists the tables and columns, and how to
  query them with DuckDB.
- Discord line via `scripts/discord.sh` only when a pull fails repeatedly (not on every run).
- Backfill once: last season's history from each player's `element-summary` (`history_past`) and the
  current season's `history`, so stage 4 has something to train on from day one.
- Restic: the data dir is small; keep it in the nightly backup (check `scripts/backup-excludes.txt`).
- CLAUDE.md: add `fpl` to the `tools/` line.

## Plan
Goal: FPL model, stage 1. A collector that saves dated FPL, Odds API and Understat snapshots under ${APPDATA_PATH}/fpl/, run by cron (no web UI yet).
Kind: new service (tools/fpl, no port) + script/cron
Run model: a long-running idle container `fpl`. Host cron runs each pull as `cron-run.sh` -> `scripts/fpl-job.sh` -> `dc.sh tools/fpl exec -T fpl ...`. This matches every existing scheduled job (syslog plus a Kuma push monitor per job). deploy-idea's `up -d --build` builds and starts the container. Stage 2 replaces the idle command with the web app on 8092.
Files:
- tools/fpl/Dockerfile: FROM python:3.12.15-slim-bookworm (same base as fitness). PYTHONDONTWRITEBYTECODE/PYTHONUNBUFFERED, WORKDIR /srv, pip install -r requirements.txt, COPY collector/ ./collector/, USER 1000:1000, CMD ["python","-m","collector","idle"].
- tools/fpl/requirements.txt: soccerdata==2026.43.0 (https://pypi.org/pypi/soccerdata/json, released 2026-10-19; needs pandas>=2,<4), plus pandas, pyarrow and requests pinned to the current PyPI stable, each with a "# Current PyPI stable on <date>: https://pypi.org/pypi/<pkg>/json" comment like tools/fitness/requirements.txt.
- tools/fpl/compose.yaml: the service (below).
- tools/fpl/collector/__main__.py: CLI `python -m collector <idle|bootstrap|fixtures|odds|odds-deadline|gameweek|understat>`. `idle` sleeps forever. Each job takes a non-blocking fcntl lock /data/state/<job>.lock (held: print "already running", exit 0). It prints one summary line and exits 0 on success, 1 on failure (the message on the last line).
- tools/fpl/collector/fpl_api.py, odds.py, understat.py, store.py: one module per source plus the storage helpers. HTTP via requests with User-Agent "homelab-fpl-collector/0.1 (personal use)", 30 s timeout and 0.5 s between element-summary calls.
- tools/fpl/README.md: jobs and schedule; data layout; the tables and their key columns; DuckDB query examples (e.g. `SELECT * FROM read_parquet('/srv/homelab/fpl/tables/players/*/*.parquet')`); how to add the odds key; failure behaviour; that history_past is season totals only (per-GW last season = the vaastav CSV).
- scripts/fpl-job.sh: `fpl-job.sh <job> <fail-threshold> <limit-secs>`. Runs `$REPO/scripts/dc.sh tools/fpl exec -T fpl timeout <limit> python -m collector <job>`, so the process inside the container is killed too. Keeps a consecutive-failure count in ~/.local/state/homelab/fpl/<job>.fails.
  - rc 0: reset the count, exit 0.
  - Failure below the threshold: print "failure N/T: <last line>", exit 0.
  - Count reaches the threshold: one `scripts/discord.sh "FPL collector: <job> failed N times in a row: <last line>"`, exit 1.
  - Count above the threshold: exit 1 with no new Discord post.
  - Log tag: `logger -t fpl-job`.
- scripts/install-cron.sh: 6 ENTRIES lines (cron-run timeout = limit + 120):
    0 */2 * * * $R fpl-bootstrap 720 $REPO/scripts/fpl-job.sh bootstrap 3 600 # homelab
    30 6 * * * $R fpl-fixtures 720 $REPO/scripts/fpl-job.sh fixtures 2 600 # homelab
    0 7 * * * $R fpl-odds 720 $REPO/scripts/fpl-job.sh odds 2 600 # homelab
    15 * * * * $R fpl-odds-deadline 720 $REPO/scripts/fpl-job.sh odds-deadline 3 600 # homelab
    0 5 * * * $R fpl-gameweek 5520 $REPO/scripts/fpl-job.sh gameweek 2 5400 # homelab
    0 4 * * 1 $R fpl-understat 3720 $REPO/scripts/fpl-job.sh understat 1 3600 # homelab
- core/uptime-kuma/compose.yaml: 4 labels per job (name, push_token, interval, max_retries=0), following the existing cron-* block:
    - cron-fpl-bootstrap: token ${KUMA_CRON_PUSH_SECRET:-}fplbootstrap0000, interval 9000
    - cron-fpl-fixtures: fplfixtures00000, interval 93600
    - cron-fpl-odds: fplodds000000000, interval 93600
    - cron-fpl-odds-deadline: fploddsdeadline0, interval 5400
    - cron-fpl-gameweek: fplgameweek00000, interval 93600
    - cron-fpl-understat: fplunderstat0000, interval 691200
- .env.example: `ODDS_API_KEY=` with a comment (free key from the-odds-api.com; empty = odds pulls skipped).
- CLAUDE.md: add `fpl` (FPL data collector, stage 1, no port; see tools/fpl/README.md) to the tools/ line, and add `fpl-job.sh` to the scripts list.
- docs/README.md: a line for tools/fpl/README.md.

New service: fpl
- category dir: tools/fpl; image homelab/fpl:0.1.0 (build: .), from python:3.12.15-slim-bookworm
- host port: none (stage 2 takes 8092); no Traefik labels; no homelab.* tile (the note says no tile this stage)
- restart unless-stopped; logging cap 10m x 3; security_opt no-new-privileges:true; not read_only (soccerdata/seleniumbase write caches)
- healthcheck: ["CMD","python","-c","import os,sys; sys.exit(0 if os.access('/data/state', os.W_OK) else 1)"], interval 60s, timeout 10s, retries 3, start_period 30s. `idle` creates /data/state at start.
- volumes: ${APPDATA_PATH}/fpl:/data
- environment: TZ: ${TZ}; DATA_DIR: /data; SOCCERDATA_DIR: /data/soccerdata; HOME: /data/home; ODDS_API_KEY: ${ODDS_API_KEY:-}
- network: its own `fpl` network (name: fpl), internet only, like tools/hermes
- Kuma: container-running monitor through the socket proxy, as in hermes: kuma.fpl.docker.name=fpl, docker_container=fpl, docker_host_name=socket-proxy, interval=60
- .lan host: none

Data layout (store.py; every write goes to a tmp file then os.replace):
- raw: /data/raw/<source>/<YYYY-MM-DD>/<name>_<HHMMSS>Z.json.gz (sources fpl, odds, vaastav; Understat uses soccerdata's own cache dir)
- tables: /data/tables/<table>/date=<YYYY-MM-DD>/<YYYYMMDDTHHMMSSZ>.parquet. Every row has `pulled_at` (UTC) and `season` (e.g. "2026-27", taken from the first event's deadline year).
  - players: bootstrap elements, plus next_gw
  - events
  - teams
  - fixtures
  - live: gw, element, plus the stats
  - player_history: element-summary history
  - player_history_past
  - odds: one row per match x bookmaker x market x outcome, with commence_time, home, away, point, price, last_update
  - understat_player_match
  - understat_team_match
- state: /data/state/state.json, read and written under /data/state/state.lock (flock). Fields: collected_gws, deadline_odds_gws, odds_remaining, odds_remaining_at, backfill_done.

Jobs:
- bootstrap: GET /api/bootstrap-static/; raw + players/events/teams.
- fixtures: GET /api/fixtures/; raw + fixtures.
- odds: GET https://api.the-odds-api.com/v4/sports/soccer_epl/odds?regions=uk&markets=h2h,totals&oddsFormat=decimal&apiKey=…
  - Never print the URL or the key.
  - Before calling: no key -> print "odds: no ODDS_API_KEY, skipped" once, exit 0. Stored odds_remaining < 50 in the current UTC month -> "odds: below floor (N left), skipped", exit 0.
  - After calling: save x-requests-remaining and x-requests-used, and print them.
- odds-deadline: GET bootstrap-static, take the next event with deadline_time > now. If the deadline is 1-3 h away and that gw isn't in deadline_odds_gws, run the odds pull and record the gw; otherwise print "nothing due", exit 0.
- gameweek: GET bootstrap-static and find events with finished && data_checked that aren't in collected_gws.
  - For each one: GET /api/event/<gw>/live/ -> raw + live.
  - If any were new: GET /api/element-summary/<id>/ for every element -> raw (one gz file per run, holding a dict of id -> body) + player_history + player_history_past. Then record the gws.
  - While backfill_done is false: also GET https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/<last season, e.g. 2025-26>/gws/merged_gw.csv into raw/vaastav (gzipped, as-is; README warns its xP column leaks post-match data). Then set backfill_done. The first run after deploy is therefore the backfill.
- understat: soccerdata.Understat(leagues="ENG-Premier League", seasons=<current season start year>); read_player_match_stats() and read_team_match_stats() -> tables.

New env vars: ODDS_API_KEY: The Odds API key (free tier, 500 credits/month); empty = odds pulls skipped

Checks the builder must run:
- scripts/dc.sh .worktrees/fpl-collector/tools/fpl config -q
- scripts/dc.sh .worktrees/fpl-collector/core/uptime-kuma config -q
- python3 -m py_compile on tools/fpl/collector/*.py
- bash -n scripts/fpl-job.sh scripts/install-cron.sh
- CRON_LIST=/dev/null scripts/install-cron.sh --check: should list the 6 new fpl lines as missing (exit 1 expected)
- check each Kuma push_token suffix = job name without hyphens, padded with 0 to 16 characters

Review focus:
- FPL API down, slow or returning HTML/empty JSON (pre-season reset, empty events) -> the job exits 1 with a one-line reason and writes nothing partial. bootstrap/odds-deadline/gameweek with no upcoming or finished events -> "nothing due", exit 0.
- Odds API: no key -> skip and exit 0. 401/429 -> failure (counts towards the Discord threshold). Remaining below 50 -> stop pulling until the month changes. An empty [] response -> no table written, logged, exit 0. The key never appears in logs or raw files.
- A pull failing on every run -> exactly one Discord line when the threshold is reached and none after it, the count reset on success, and the Kuma monitor up below the threshold and down from it (no alert spam from a 2-hourly job).
- Two jobs overlapping (odds and odds-deadline, or a long gameweek run against the next day's run) -> per-job lock plus locked state.json, and atomic file writes, so state is never corrupted. An exec killed at the timeout leaves no half-written parquet (tmp + rename).
- Understat/soccerdata breaking (site change, blocked) -> a failure line, exit 1 (Discord on the first failure, since it runs weekly). The other jobs are unaffected.

Docs: CLAUDE.md tools/ line + scripts list (fpl-job.sh); docs/README.md line for tools/fpl/README.md; no port-table change (8092 is reserved for stage 2 in the note, not the table). Restic: /srv/homelab/fpl is already a backup source and nothing in backup-excludes.txt matches it, so nothing changes there. Raw bootstrap gz is about 250 KB x 12 a day, roughly 1 GB a season; the README says so. The note has no rule-breaking instructions.

## Manual steps
- Sign up at the-odds-api.com (free) and put ODDS_API_KEY in the env file (it can be added later; the odds jobs skip until it is set).
- Deploy with scripts/deploy-idea.sh fpl-collector. It builds tools/fpl, redeploys core/uptime-kuma for the 6 push monitors and reinstalls cron. Then `scripts/install-cron.sh --check` should print "cron: in sync".
- Optional: start the backfill now with `scripts/fpl-job.sh gameweek 2 5400` instead of waiting for 05:00.

## Review notes
1. /home/dan/homelab/.worktrees/fpl-collector/tools/fpl/collector/__main__.py:48-51: `job_odds` fetches FPL `bootstrap-static` only to work out the season string. If FPL is down or mid-update at 07:00, that day's odds snapshot is lost, even though the Odds API is up, and odds can't be fetched again later. A fallback to `store.season_str(utcnow().year)` (adjusted for months before August) when bootstrap fails would keep the snapshot.
2. /home/dan/homelab/.worktrees/fpl-collector/tools/fpl/collector/fpl_api.py:207-212: the gameweek job makes about 800 `element-summary` calls with no retry, so one transient 5xx or 429 fails the whole run and nothing is written. It retries the next day and Discord only fires after 2 days in a row, so there is no spam or data loss (live and history stay available all season). One or two retries per call with a backoff would make the backfill and weekly run sturdier.
3. /home/dan/homelab/.worktrees/fpl-collector/tools/fpl/collector/store.py:187-189: `read_state()` goes through `state()`, so every read also rewrites state.json. It is atomic and under the lock, so it is safe, just unnecessary writes.
4. The Understat path wasn't run (I started nothing). I read the soccerdata 2026.43.0 wheel: Understat uses requests, not seleniumbase, and skips the cache for the current season, so weekly pulls get fresh data. The first real run still needs a look in syslog (`journalctl -t cron-fpl-understat`).
5. /home/dan/homelab/.worktrees/fpl-collector/tools/fpl/collector/odds.py:17: the floor resets on the UTC calendar month. If the free tier resets on the sign-up date instead, pulls could resume a little early and fail with 401 until the credits reset. That costs a few failures that count toward the Discord threshold, nothing more.

## Declined to judge
- Disk growth of raw bootstrap gz (about 1 GB a season) in restic and B2: the plan and README accept and document it.
- No retry or backoff on FPL calls in general: the plan only asks for a User-Agent and a delay.
- Odds credit budget (about 62 a month daily plus about 10 for deadlines, against 500): fine at the planned schedule; nothing more to judge.
- vaastav CSV content quality and the `xP` leak: the plan stores it raw only, and the README warns about it.
- Whether `data_checked` timing matches FPL's real-world lag: an API behaviour outside this build.
