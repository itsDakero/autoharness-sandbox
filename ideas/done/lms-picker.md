# Last Man Standing picker: safest Championship team each round

Value: 4   (Dan plays LMS with friends in WhatsApp; this does the research and stops him forgetting a pick)
Effort: 2  (one odds source, a small page, three cron jobs)
Risk: 1    (new isolated service, read-only public API, own data dir)
Score: 8
Source: Dan 2026-10-25 (session with Claude)

## Problem
Dan plays Last Man Standing (£5 entry, winner takes the pot) on the Championship. Each round he picks
one team to win; a draw or loss, or no pick, puts him out; he can't pick the same team twice in a game.
He wants the research done for him: which of his remaining teams is most likely to win this round.

## Game rules (as Dan plays them)
- A round is a gameweek: a midweek block of fixtures is one round, the weekend block is the next.
- Championship only; when a round has no Championship games, the pool is League One + League Two.
- Deadline: about 30 minutes before the round's first kick-off.
- Win = through; draw or loss = out; no pick = out. Abandoned game: the score at the time counts.
- Everyone on the same team in a round: that team is voided and everyone re-picks.
- Everyone out in the same round: the pot rolls over to a new game (fresh £5, used teams reset).
- Postponed game: Dan decides by hand (usually through); the page only flags it.
- Dan going out doesn't end the game: the others play on until one is left, and Dan only plays again
  when a new game starts (or the pot rolls over because everyone went out in the same round, which
  puts him back in). The app can't see the WhatsApp chat, so Dan tells it with the "New game" button.

## Out state
- After "I'm out" (or a lost/drawn result), the page shows "Out since round N, waiting for the next
  game" with the "New game" button on top; no ranking, no pick buttons.
- While out: no Discord pick messages or deadline reminders. The odds pull and results jobs skip the
  API too (no credits spent). One Discord line a week (Monday) while out: "Still out of LMS; press New
  game on the page when the next one starts."

## Proposal
- New service `tools/lms/` on port 8093 (add to the CLAUDE.md ports table; 8092 is held for fpl), full
  template labels, admin audience, data in `${APPDATA_PATH}/lms/` (SQLite).
- Odds: The Odds API v4, key `ODDS_API_KEY` (the same key the FPL chain uses; add it to
  `.env.example` if it isn't there yet; Dan has added it and checked it 2026-10-25). League keys
  (checked with `/v4/sports`): `soccer_efl_champ`, `soccer_england_league1`,
  `soccer_england_league2`; never `soccer_england_efl_cup` (cup games don't count). Fixtures from `/events`
  (free); odds from `/odds` with `markets=h2h&regions=uk` (1 credit per league per call), only while
  a round is open, about twice a day; L1/L2 only when the round has no Championship games. Results from
  `/scores?daysFrom=3` after the round (2 credits). Show the remaining quota (response headers
  `x-requests-remaining`) on the page, since the FPL build shares the free 500/month.
- Rounds: group fixtures into a Tue-Thu or Fri-Mon block. Deadline = first kick-off - 30 min,
  editable per round on the page.
- Ranking: "safest this week" only. Remove the margin from each bookmaker's 1X2 (proportional is
  fine) and average P(win) across bookmakers. Ranked table: team, opponent, H/A, P(win), P(draw),
  best price, kick-off. Teams already used in the current game are greyed out and never recommended.
- Page: this round (ranked table; buttons "I picked X", "Voided, re-pick", "Postponed: through /
  re-pick / out", "I'm out"), the history of picks and results per game, used teams, and a "New game"
  button (rollover or fresh start: clears the used teams, keeps the old game in the history).
  Results are filled in from `/scores` and can be overridden by hand (abandoned games).
- Discord via `scripts/discord.sh`: the day before the deadline, the top 3 picks with P(win) and the
  deadline; 2 h before the deadline, a reminder only if no pick is recorded; after the round, through
  or out.
- Cron jobs through `scripts/cron-run.sh` (odds pull, alerts, results), added to `install-cron.sh`.
- Without the key: the page says to add `ODDS_API_KEY` and the jobs exit 0 without calling the API.

## Plan
Goal: tools/lms, a page and three cron jobs that rank the safest Championship pick each LMS round from Odds API odds, track used teams and results, and send Discord nudges.
Kind: new service
Files:
- tools/lms/compose.yaml: the service (below)
- tools/lms/Dockerfile: copy tools/wardrobe/Dockerfile (python:3.12.15-slim-bookworm, USER 1000:1000, uvicorn app.main:app on 8080, HEALTHCHECK on /healthz)
- tools/lms/requirements.txt: fastapi==0.142.2, uvicorn==0.54.0, jinja2==3.1.6, python-multipart==0.0.32 (same pins as tools/wardrobe). Use stdlib urllib for HTTP, no new packages
- tools/lms/app/{__init__,main,db,oddsapi,rounds,ranking,jobs}.py + templates/ + static/: the web app and the jobs
- tools/lms/tests/test_core.py: unittest for margin removal, the Tue-Thu/Fri-Mon grouping, the pool fallback, used-team exclusion
- tools/lms/README.md: first run, rules as built, data, credits, failures
- scripts/lms-job.sh: cron wrapper. `lms-job.sh <odds|alerts|results>` runs `scripts/dc.sh tools/lms exec -T lms timeout 240 python -m app.jobs <job>`. Non-empty stdout goes to `scripts/discord.sh` as the message. stderr goes to `logger -t lms-job`. Exits with the job's rc. `flock -n` on ~/.local/state/homelab/lms/lms.lock, so a second run exits 0 quietly
- scripts/install-cron.sh: add
  `0 7,19 * * * $R lms-odds 300 $REPO/scripts/lms-job.sh odds # homelab`
  `*/15 * * * * $R lms-alerts 300 $REPO/scripts/lms-job.sh alerts # homelab`
  `40 */2 * * * $R lms-results 300 $REPO/scripts/lms-job.sh results # homelab`
- core/uptime-kuma/compose.yaml: push monitors cron-lms-odds (token `${KUMA_CRON_PUSH_SECRET:-}lmsodds000000000`, interval 46800), cron-lms-alerts (`lmsalerts0000000`, 1800), cron-lms-results (`lmsresults000000`, 9000). All max_retries=0, in the same style as the existing cron-* blocks
- scripts/ops-actions.py: add `lms` (tools/lms) to REGISTRY
- .env.example: `ODDS_API_KEY=` with a comment ("tools/fpl + tools/lms: The Odds API key, free 500 credits/month shared; empty = pulls skipped"). Add it only if it isn't there. Main doesn't have it yet; branch idea/fpl-collector adds the same name
- CLAUDE.md, docs/README.md, docs/ops-actions.md: see Docs

New service: lms, tools/lms. Image homelab/lms:0.1.0 (`build: .`). The base python:3.12.15-slim-bookworm is already used and verified by wardrobe/fitness.
  Port 8093:8080. 8090 is the lowest free port, but Dan's note picks 8093 and holds 8092 for fpl, so take 8093.
  Volume ${APPDATA_PATH}/lms:/data (SQLite lms.db, WAL, busy_timeout 5000).
  Hardening like wardrobe: read_only, tmpfs /tmp, no-new-privileges. Logging cap. Network proxy.
  Environment: TZ, DATA_DIR=/data, ODDS_API_KEY=${ODDS_API_KEY:-}.
  Traefik: router/service lms, Host(`lms.${DOMAIN}`), entrypoint web, port 8080.
  Dashboard: name "Last Man Standing", group Tools, audience admin, description "Safest LMS pick each round from bookmaker odds", port 8093.
  Icon: `fotmob` if https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/fotmob.svg returns 200, else another football slug that exists. Name the slug and the check in the commit message.
  Kuma: kuma.lms.http.name=lms, url=http://${LAN_IP}:8093/healthz. .lan host lms.lan.

Behaviour (decisions the builder must follow):
- Odds API v4, base https://api.the-odds-api.com/v4/sports/<key>/:
  - Leagues: soccer_efl_champ, soccer_england_league1, soccer_england_league2. Never soccer_england_efl_cup.
  - `/events`: free, all three leagues, every odds run.
  - `/odds?regions=uk&markets=h2h&oddsFormat=decimal`: Championship only, unless the round has no Championship fixtures; then L1 and L2.
  - `/scores?daysFrom=3`: only for the picked team's league.
  - Store `x-requests-remaining`/`x-requests-used` and the time after every call, and show them on the page.
- Rounds: put each kick-off in Europe/London into a block. Tue/Wed/Thu belongs to the block starting that Tuesday; Fri/Sat/Sun/Mon to the block starting that Friday. Round key = the block start date.
  - Current round = the block of a pick whose result is still pending, else the earliest block with a kick-off later than now minus 4 h.
  - Deadline = first kick-off minus 30 min. The page can override it, stored per round.
- Ranking: for each bookmaker, implied p = (1/odds) / sum over 1X2. Average P(win) and P(draw) across bookmakers; best price = the highest decimal price.
  - Rank by P(win) descending. Teams used in the current game are greyed out, sorted last and never in the top 3.
  - A team that has no odds yet is listed with "no odds" and isn't ranked.
- Games and picks: a games table (id, started, out_round, status) and a picks table (game, round, team, league, event id, result: pending/through/out/void/postponed, manual flag).
  - Buttons:
    - "I picked X".
    - "Voided, re-pick": the voided team is not counted as used, and is struck out for that round only.
    - "Postponed: through / re-pick / out".
    - "I'm out".
    - "New game": new game row, used teams empty, the old game stays in the history.
    - Manual result override.
  - Out state is exactly as in the note's "## Out state": the "Out since round N" banner, the New game button only, no ranking or pick buttons.
- Jobs (python -m app.jobs <job>; stdout = Discord text only, logs on stderr):
  - All jobs: no ODDS_API_KEY → exit 0 without calling the API. Game out → odds and results exit 0 without calling the API.
  - odds: refresh events and odds for the current round.
  - alerts:
    - From deadline-24h: once per round, the top 3 with P(win) and the deadline. If the stored odds are older than 6 h, pull fresh odds first.
    - From deadline-2h: once, only if no pick is recorded.
    - After the deadline with no pick: once, "No pick recorded for round N; record it on the page". Never mark Dan out automatically for this.
    - While out: Mondays from 09:00 local, the note's line once per ISO week.
  - results: when the pick's kick-off was 2 h or more ago and its result is pending, call /scores. Completed → through or out, plus one Discord line.
  - Each Discord message gets a sent flag in the DB, set before printing (no repeats).

New env vars: ODDS_API_KEY: The Odds API key (shared with tools/fpl). Dan has it already.
Checks the builder must run:
- scripts/dc.sh <worktree>/tools/lms config -q
- scripts/dc.sh <worktree>/core/uptime-kuma config -q
- python3 -m py_compile on tools/lms/app/*.py and scripts/ops-actions.py
- cd tools/lms && python3 -m unittest discover -s tests
- bash -n scripts/lms-job.sh scripts/install-cron.sh
- scripts/install-cron.sh --check, which should show the 3 new lines as drift
- ss -ltnH "sport = :8093" is empty
Review focus:
- The API key is in the query string → it never appears in logs, exceptions, stdout or the page. Log only the league, the HTTP status and the error class.
- Odds API down, 401/429, or an empty or odd response (no bookmakers, an outcome name that doesn't match home/away) → the job exits 1 with one stderr line, keeps the last stored odds and the page says how old they are. No Discord message from a failed pull.
- Quota: last known x-requests-remaining < 40 → skip /odds and /scores, show a warning on the page and send one Discord line per month. This leaves room for FPL.
- Fixture postponed (gone from /events, or its kick-off moved outside the round's block) → flag it on the page with the three Postponed buttons plus one Discord line. Never auto-out.
- Cron jobs overlapping each other or a page click → the flock in the wrapper plus WAL/busy_timeout: no "database is locked" crash and no Discord message sent twice.
Docs:
- CLAUDE.md: port table `| 8093 | lms |`; Layout tools/ line "lms = Last Man Standing picker (Odds API), admin; see `tools/lms/README.md`"; scripts list `lms-job.sh <odds|alerts|results>` (cron: LMS odds, Discord nudges, results).
- docs/README.md: a line for tools/lms/README.md.
- docs/ops-actions.md: add lms to the registry line.

## Manual steps
1. ODDS_API_KEY is already set in .env (Dan, 2026-10-25). If idea/fpl-collector merges first, the .env.example line will conflict; keep one copy.
2. deploy-idea.sh lms-picker builds and starts lms and installs cron. Then run `scripts/dc.sh core/uptime-kuma up -d` so AutoKuma creates the 3 push monitors, if deploy didn't restart it.
3. Open http://192.168.0.210:8093/ and press "New game" to start the current game. Add picks already made this game as used teams with "I picked X" on their rounds, or tick them as used on the page.

## Review notes
1. tools/lms/compose.yaml:54: the icon is `sportarr`. I checked jsDelivr: `fotmob` returns 404 and `sportarr` returns 200. Sportarr is a general sports icon, not a football one, so it doesn't quite meet the plan's "another football slug". Put the slug and this check in the commit message, as the plan asks.
2. app/rounds.py current_round: this follows the plan's rule (earliest block with a kick-off later than now minus 4 h). The side effect is that a weekend round with a Monday game stays "current" until about Tue 00:00. So the midweek top-3 reaches Discord about 19 h before the deadline, not a full day.
3. app/jobs.py _fresh_odds: say the odds are older than 6 h, credits are under 40 and no odds have ever been stored. Then alerts returns rc 1 every 15 min, which shows as cron-lms-alerts down in Kuma. This is a rare first-run case.
4. templates/index.html: the three Postponed buttons only show when a pick is flagged (fixture gone or moved). Without a flag, Dan has to use the manual through/out/void buttons for a postponement the API missed. The note's "the page only flags it" allows this.
5. While out, the page still shows the "Add as used" form and the override buttons in History. The override buttons are useful for undoing a wrong "out". The form is a small departure from "New game button only".

## Declined to judge
- No CSRF protection or login on the POST buttons: the plan makes this an admin, LAN-only page with no login, the same as wardrobe.
- /pick accepts picks after the deadline: the plan sets no deadline lock, and Dan re-picks after a void.
- Per-round odds freshness (`odds_at` is global): /odds returns every upcoming event in the league, so a global timestamp is enough.
- A bad bookmaker line in an otherwise good response only gets logged (rc 0): the plan's "exits 1" reads as the case where nothing usable comes back, and that case does raise.
- /events calls when credits are near zero: the plan says /events is free and should run on every odds run.
