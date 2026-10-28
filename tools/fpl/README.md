# FPL collector (stage 1 of the FPL model)

Saves dated snapshots of what was known at each gameweek deadline: FPL flags, prices, `ep_next`, match odds,
Understat xG. The FPL API only serves the present, so a week not collected is lost. Stage 2 adds a page on
port 8092 (below). The container runs the web app; host cron runs each pull and job inside it.

## Jobs

Cron (`scripts/install-cron.sh`) -> `scripts/cron-run.sh fpl-<job>` -> `scripts/fpl-job.sh <job> <threshold> <secs>`
-> `docker compose exec fpl python -m collector <job>`. Each job has a Kuma push monitor `cron-fpl-<job>`.

| Job | Schedule | What |
|---|---|---|
| `bootstrap` | every 2 h | `bootstrap-static`: players, events, teams |
| `fixtures` | daily 06:30 | `fixtures` |
| `odds` | daily 07:00 | The Odds API, `soccer_epl`, h2h + totals, UK |
| `odds-deadline` | hourly :15 | the odds pull again 1-3 h before the next deadline (once per gameweek) |
| `gameweek` | daily 05:00 | for each finished + data_checked gameweek: `event/<gw>/live`, then `element-summary` for every player |
| `understat` | Mondays 04:00 | Understat EPL player + team match xG via `soccerdata` |

`gameweek` does the one-time backfill on its first run: every player's `element-summary` (`history` = this
season so far, `history_past` = last seasons' totals) plus last season's vaastav `merged_gw.csv` (raw, as is: its
`xP` column leaks post-match data, do not train on it). `history_past` is season totals only; per-gameweek data
for last season comes from the vaastav CSV. To start it now: `scripts/fpl-job.sh gameweek 2 5400`.

## Odds API key

Free key at the-odds-api.com (500 credits a month). Put `ODDS_API_KEY=...` in the env file and recreate the
container (`scripts/dc.sh tools/fpl up -d`). Empty = the odds jobs print "no ODDS_API_KEY, skipped" and exit 0.
Each pull stores `x-requests-remaining`; below 50 left, pulls stop until the next UTC month. The key never goes
to logs or raw files.

## Page (port 8092, `http://192.168.0.210:8092/`, `fpl.lan`)

One server-rendered page, no login (admin tile on the dashboard). Top to bottom: next gameweek + deadline and the
projection source in use (with the file's age), the solver plan (the settings it ran with, the last failure if
any), the "Run solver now" button, the settings form, my squad, minutes overrides, the top 40 projections.
With no collector data yet the page says "No data yet"; with an empty `FPL_TEAM_ID` the squad and solver say so.
`FPL_TEAM_ID` (env file) is the number in the FPL "Points" page URL; the squad comes from the public
`entry/<id>/` endpoints (10 s timeout, 15 min cache in `/data/web/entry.json`; on a failure the cached squad is
shown with its age).

## Projections contract

Built-in source `fpl-ep`: FPL's `ep_next` for the next gameweek, spread over later gameweeks by own-side fixture
difficulty (FDR 1-5 scale 1.25 / 1.1 / 1.0 / 0.85 / 0.7); blanks are 0, doubles add up. Minutes = fixtures x the
mean of the last 5 `player_history` minutes (45 with none), times `chance_of_playing_next_round` for the next
gameweek. Each solve writes it to `/data/projections/fpl-ep/<YYYYMMDDTHHMMSSZ>.parquet` (newest 14 kept).

Stages 3-4 (the real model) write their own file the same way:
`/data/projections/<source>/<YYYYMMDDTHHMMSSZ>.parquet` with columns `element:int, gw:int, pts:float,
xmins:float, generated_at:timestamp UTC`. The setting `projection_source` is `auto` (default: the newest file of
any source other than `fpl-ep` that is at most 8 days old and covers the next gameweek, else `fpl-ep`) or a source
name (newest file of that source, any age; if it has none the page says so and uses `fpl-ep`).

## Minutes overrides

`/data/overrides/minutes.csv` (`element,gw,xmins,note,updated_at`), edited on the page (player picked by name,
gameweek, minutes or `out`). They apply to every source before the solver CSV is built: 0 minutes -> 0 points;
otherwise points x min(override / projected minutes, 1.5); from a projected 0: form x fixtures x override / 90.
Rows for unknown players, past gameweeks or beyond the horizon are ignored and greyed on the page; a malformed
row is ignored too (and dropped the next time a row is added or deleted). Stages 3-4 should read this file.

## Solver

Solio's open-fpl-solver (Apache-2.0, HiGHS), pinned to commit `ec65f5e2b2be34441cb4b2a9efafea1ec0fe3b79`
(Dockerfile, extracted to `/opt/solver`, `PYTHONPATH=/opt/solver`). Each run builds `/opt/solver/data/homelab.csv`
(solio format) from the projections, writes `/data/solver/settings.json` (datasource `homelab`, `team_data` "id",
horizon, secs, decay_base, ft_value, chips), runs `python solve.py --config ...` in `/opt/solver/run`, reads the
result CSV into `/data/solver/latest.json` and deletes the CSVs. Page settings: horizon 8, secs 300, decay 0.9,
FT value 1.5, plan chips on, source auto.

- **Python 3.12 note.** The solver's pyproject says `>=3.14`; the image stays on 3.12 because the code only uses
  older syntax (read, not run). The first "Run solver now" is the test: if it fails with a syntax or import
  error, bump the image to `python:3.14-slim` (check wheels exist for the pins in `requirements.txt`).
- **Chip halves (2026/27 has two sets).** Chips left are read from the entry history per half (GW1-19, GW20-38).
  With "plan chips" on, a chip unused in a half may only be used in that half's gameweeks inside the horizon
  (`allowed_chip_gws`). The solver caps an allowed chip at one use over the whole horizon, so a chip unused in
  both halves is planned at most once per run. With it off, all chip limits are 0.
- **Squad and free transfers** come from the solver's own reading of the public transfer history. It does not see
  transfers already made this gameweek: run it before making them.

## Cron (page jobs)

`scripts/fpl-web-job.sh <solve|deadline|teams|players>` -> `docker compose exec fpl python -m web.jobs <job>`; Kuma push
monitors `cron-fpl-solve`, `cron-fpl-deadline`, `cron-fpl-teams` and `cron-fpl-players` (see the team and player models below).

| Job | Schedule | What |
|---|---|---|
| `solve` | daily 06:45 | the solver run, same as the button; nothing on stdout |
| `deadline` | daily 18:00 | next deadline within 36 h and not yet announced: a fresh solve when the plan is over 12 h old or failed, then one Discord line (moves, captain, chip, source) |

| `teams` | hourly :25 | the team goals model (below) |
| `players` | hourly :40 | the player points model (below); `cron-fpl-players`, Kuma interval 5400 |

A line is sent at most once per gameweek (`/data/web/state.json`, `sent_gw`). If the solve failed, the line says
so instead of giving moves.

## Team goals model (stage 3)

Per fixture in the next 8 gameweeks: expected goals for and against, clean-sheet chance and the score matrix.
`python -m web.jobs teams` (cron `fpl-teams`, hourly :25, `scripts/fpl-web-job.sh teams`, Kuma push monitor
`cron-fpl-teams`) runs `model/teams.py`. CPU only, `penaltyblog` pinned.

- **Fixtures with odds** (pulled within 48 h, kickoff ahead, teams matched to the FPL fixture within 36 h): median
  price across bookmakers, power-method de-vig, then home/away expected goals solved so a Dixon-Coles score matrix
  matches 1X2 and over/under 2.5 (`source` = `market`). Without a 2.5 line only 1X2 is used, with the run's rho.
- **Other fixtures** (`ratings`): two quasi-Poisson attack/defence/home fits with time decay, one on the market
  lambdas of past fixtures, one on non-penalty xG from Understat; blended in log space (`w_market`), shrunk toward
  the league mean by 2% per gameweek ahead. With only one fit, that one alone; with none, the fixture is left out.
  (FPL's own xG is not used: it is unclear whether it includes penalties.)
- **Output** `/data/model/teams/<YYYYMMDDTHHMMSSZ>.parquet` (newest 14 kept; tmp file, then rename). Columns:
  `fixture_id, gw, team_h, team_a, kickoff_time, xg_h, xg_a, cs_h, cs_a, p_h, p_d, p_a, source, rho, matrix`
  (JSON 11x11, `matrix[home goals][away goals]`, 5 dp), `generated_at`. Stage 4 reads the newest file.
  `status.json` beside it: generated_at, counts market/ratings/omitted, fit sizes, params tuned|default, `unmapped`
  (odds team names with no FPL team), inputs_key. The page shows the grid (teams x 8 gameweeks) above Projections.
- **Skips**: unchanged inputs and a file under 24 h old -> "nothing new", no file. The job also logs (syslog,
  `journalctl -t fpl-web-job`) and exits 0 for: model busy (tune or history holds `/data/model/.lock`), no data
  yet (page: "No team model yet"), unmapped Odds API names (those fixtures use ratings; the names show on the
  page in red). A fixture whose odds do not fit falls back to ratings. Only an exception exits 1.
- **By hand** (optional; defaults `xi_market` 0.0019, `xi_xg` 0.0019, `w_market` 0.5, `rho` -0.05):
  1. Download `https://football-data.co.uk/mmz4281/<YYZZ>/E0.csv` for 1920..2627 into
     `/srv/homelab/fpl/model/history/football-data/E0_<YYZZ>.csv`. Download by hand only: the site's terms forbid
     automated scrapers. Re-download the current season now and then until the collector's odds have built up.
  2. `scripts/dc.sh tools/fpl exec fpl python -m model history` -> `model/history/market.parquet` (closing-odds
     lambdas + results) and `understat_team_match.parquet` (2019 to last season, via soccerdata).
  3. `... python -m model tune` (tens of minutes): rolling origin, one per 7 days from 2021-08, scores the 1X2
     log-loss of the next 8 weeks over a grid of the two decays and `w_market`; writes `model/teams/params.json`
     and prints one summary line. Both commands print `busy` and exit 0 when the lock is held.

## Player points model (stage 4)

Expected points per player and gameweek, with full distributions, on top of the team model's score matrices.
`python -m web.jobs players` (cron `fpl-players`, hourly :40, `scripts/fpl-web-job.sh players`, Kuma push monitor
`cron-fpl-players`) runs `model/players.py` (numpy; pure parts in `model/pcore.py`, host-tested).

- **Inputs**: players, fixtures, events (collector tables); `player_history` read over all partitions but only the
  current season's rows (`season` of the newest events; ids reset each season), the latest
  pull per (element, fixture), so a double gameweek keeps both rows; last season's vaastav `merged_gw` (newest
  `raw/vaastav/*/merged_gw_*.csv.gz`, mapped by normalised "first second" name to a unique current player; the
  rest are dropped and counted as `unmapped_vaastav`, which includes players who left the league); the newest team
  model file (`matrix`); the minutes overrides; the scoring rules from the newest raw bootstrap.
- **Scoring** comes from `game_config.scoring` (per season, per position; a missing key is a failure). Not in
  `game_config`, so constants in `pcore.py` (checked 2026-10-26 against the PL scoring and BPS pages): defensive
  contribution thresholds DEF 10, MID/FWD 12 (DEF count = clearances/blocks/interceptions + tackles; MID/FWD add
  recoveries), 1 save point per 3 saves, goals conceded per 2, long play from 60 minutes, BPS event values.
- **Minutes**: a decayed (0.92 per match) log gives P(start), mean minutes per start, P(60+ | start), P(sub
  appearance | no start) and sub minutes, with priors worth 2 matches each. Availability: `u` = 0; next gameweek
  `chance_of_playing_next_round`/100 (none = 1; none on an i/s/n flag = 0); the one after min(1, next + 0.5); later 1.
  Dan's overrides win: minutes = override / fixtures per fixture, 45+ a fixed start, below that a fixed sub spell,
  `out` = 0; the output `xmins` is exactly the override, so stage 2's `apply_overrides` scales by 1.
- **Goals and assists**: each simulated team goal gets a minute and goes to an on-pitch teammate in proportion to
  his decayed xG per 90 (FPL `expected_goals`; shrunk to a position prior by 900 minutes, so finishing skill barely
  counts). 3.5% of goals have no scorer (own goals). An assist happens with chance 0.75 (the data's ratio once
  there are 200 goals) and goes to a teammate by xA per 90. **No separate penalty term:** FPL `expected_goals`
  already includes penalty xG (worked example in the idea note: Gordon's 2025/26 penalties), so a taker's share
  already counts them. Penalty misses are a small rate (0.02 per team match) for the `penalties_order == 1` taker.
- **Defence**: goals conceded and clean sheets (60+ minutes, nothing conceded while on) from the same simulated
  goals; saves Poisson(rate x opponent expected goals / 1.4); defensive contributions Poisson for defenders,
  binomial (variance 0.81 x mean) for MID/FWD, rate scaled by clip((opp/own expected goals)^0.25, 0.8, 1.25).
- **Bonus**: BPS = baseline per 90 (his bps minus goal/assist/clean-sheet/save events) x minutes + simulated
  events + Normal(0, 4 sqrt(min/90)); ranked among everyone who played, 3/2/1 with the official ties.
  Yellow 0.17, red 0.005 and own goal 0.005 per 90.
- **Run**: 10,000 draws per fixture (seed = fixture id), draws summed over a gameweek's fixtures (doubles), a
  blank gameweek is a row of 0. Gameweeks are modelled from the next one while every unfinished fixture of the
  gameweek is in the team model (at most 8).
- **Output** `/data/projections/model/<ts>.parquet` (newest 14 kept; tmp file, then rename): the contract columns
  `element, gw, pts, xmins, generated_at` plus `p_start, p60, p10` (P(pts >= 10)), `q50, q90, xg, xa, p_cs,
  p_defcon, xbonus`. `/data/model/players/status.json`: generated_at, gws, n_players, n_fixtures,
  unmapped_vaastav, inputs_key, msg. Every value is checked finite before writing.
- **Page**: with a model file, the Projections table adds "Model", "FPL ep" (computed every time), "P(10+)" and
  "q90" for the next gameweek, and a line with the run's age and the source in use.
- **`auto` switches the solver to `model`** as soon as a file under 8 days old covers the next gameweek. To compare
  first, set Source to `fpl-ep` on the page.
- **Skips and failures**: no team model file ("no team model") or the next gameweek not fully covered
  ("incomplete"): no file, exit 0, `auto` stays on `fpl-ep`. Unchanged inputs and a file under 24 h old: "nothing
  new". Model lock held (team model, tune, history, or another players run): "busy", exit 0 (the shell wrapper
  also takes its own flock). No `game_config.scoring` in the raw bootstrap, a non-finite value, or any other
  exception: one `players FAILED:` line, exit 1 (Kuma down), no file. Messages go to syslog
  (`journalctl -t fpl-web-job`).
- Tests: `tests/test_players.py` (pure, runs anywhere) and `tests/test_players_sim.py` (numpy; skipped on the
  host): `scripts/dc.sh tools/fpl exec fpl python -m unittest discover -s tests`.
- Stage 5 (backtest) is meant to tune the decays, priors and noise constants.

## Failures (page and jobs)

- No collector data / empty `FPL_TEAM_ID`: the page says so; `solve` and `deadline` log "no data" / "no FPL_TEAM_ID"
  to syslog (`journalctl -t fpl-web-job`) and exit 0.
- The solver fails (import error, FPL API down, infeasible, timeout): `solve` logs one line and exits 1 (Kuma
  down). `latest.json` keeps the previous plan; the page shows it with its age plus the failure line.
- Two solves at once (button and cron): the second says "already running" (cron exit 0); the page shows "running
  since" while the lock is held.
- A bad override row or projection file never takes the page or the solve down.

## Failure behaviour

- A failing job prints one line (`<job>: FAILED: <reason>`) and exits 1; nothing partial is written (files are
  written to a tmp name, then renamed; `gameweek` fetches everything before it writes anything).
- `fpl-job.sh` counts consecutive failures per job (`~/.local/state/homelab/fpl/<job>.fails`). Below the
  threshold it exits 0 (Kuma stays up); at the threshold one Discord line and exit 1 (Kuma down); above it
  exit 1 and no new post. A success resets the count. Thresholds: bootstrap 3, fixtures 2, odds 2,
  odds-deadline 3, gameweek 2, understat 1 (weekly).
- No events / nothing to collect (pre-season) prints `nothing due` and exits 0.
- Two runs of one job: the second prints `already running`. `state.json` is read and written under a lock.

## Data layout (`/srv/homelab/fpl/`, in the nightly restic backup)

```
raw/<source>/<YYYY-MM-DD>/<name>_<HHMMSS>Z.json.gz     sources: fpl, odds, vaastav (csv.gz)
tables/<table>/date=<YYYY-MM-DD>/<YYYYMMDDTHHMMSSZ>.parquet
state/state.json                                        collected_gws, deadline_odds_gws, odds_remaining, backfill_done
soccerdata/                                             Understat's own cache
projections/<source>/<ts>.parquet                       projection files (contract above)
overrides/minutes.csv                                   minutes overrides
solver/ (settings.json, latest.json), web/ (settings, state, entry cache)
model/teams/<ts>.parquet, status.json, params.json         team goals model (stage 3), .lock; model/history/ (by hand)
model/players/status.json                                  player points model (stage 4); its files go to projections/model/
```

Raw bootstrap is about 250 KB x 12 a day, roughly 1 GB a season. Every table row has `pulled_at` (UTC) and
`season` (e.g. `2026-27`). Dict/list fields are stored as JSON text.

| Table | Key columns |
|---|---|
| `players` | `id`, `team`, `element_type`, `now_cost`, `status`, `chance_of_playing_next_round`, `news`, `ep_next`, `form`, `next_gw` (all bootstrap `elements` columns) |
| `events` | `id`, `deadline_time`, `finished`, `data_checked`, `is_next` |
| `teams` | `id`, `name`, `short_name`, strengths |
| `fixtures` | `id`, `event`, `team_h`, `team_a`, `kickoff_time`, `team_h_difficulty`, `team_a_difficulty` |
| `live` | `gw`, `element`, then the stats (`minutes`, `goals_scored`, `total_points`, ...) |
| `player_history` | `element`, `round`, `fixture`, `total_points`, `minutes`, `value`, ... (this season) |
| `player_history_past` | `element`, `season_name`, `total_points`, `minutes`, ... (season totals) |
| `odds` | `event_id`, `commence_time`, `home`, `away`, `bookmaker`, `market`, `outcome`, `point`, `price`, `last_update` |
| `understat_player_match`, `understat_team_match` | soccerdata columns, index reset to columns |

Snapshots repeat, so take the latest `pulled_at` per key (or the one at a deadline) when querying.

## DuckDB

```sql
-- price and flags of one player over time
SELECT pulled_at, web_name, now_cost, status, chance_of_playing_next_round, ep_next
FROM read_parquet('/srv/homelab/fpl/tables/players/*/*.parquet')
WHERE web_name = 'Haaland' ORDER BY pulled_at;

-- latest odds for the next matches, h2h only
SELECT home, away, bookmaker, outcome, price
FROM read_parquet('/srv/homelab/fpl/tables/odds/*/*.parquet')
WHERE market = 'h2h' AND pulled_at = (SELECT max(pulled_at) FROM read_parquet('/srv/homelab/fpl/tables/odds/*/*.parquet'));
```
