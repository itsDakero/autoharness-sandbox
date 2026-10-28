# FPL model, stage 3: team goals model from betting odds and xG

Depends on: fpl-dashboard (shows its output; reads the collector's odds and xG)
Value: 4   (the team layer every player projection is built on)
Effort: 3  (de-vig + Dixon-Coles fits with penaltyblog; a projections table per fixture)
Risk: 1    (offline modelling inside the FPL service)
Score: 12
Source: Dan 2026-10-25 (design in `reports/FPL points prediction model.md`, "Team goals" section;
notes in `research_notes/FPL points prediction model/team_odds_xg.md`)

## Problem
Player points depend on how many goals each team is expected to score and concede in each fixture.
FPL's `ep_next` doesn't expose that, and the stage 2 page has no fixture-level view.

## Proposal
- For fixtures with odds: remove the bookmaker margin (power or Shin method, `penaltyblog`
  `calculate_implied`), then solve each fixture's home/away expected goals so a Dixon-Coles score matrix
  matches the 1X2 and over/under 2.5 prices. Clean-sheet probability = the zero row/column.
- For later gameweeks (up to 8 ahead): attack/defence/home ratings fitted to the market-implied goals of
  recent fixtures, plus a second Dixon-Coles fit on non-penalty xG (from the FPL API's Opta xG and
  Understat) with time decay; blend the two in log space. Weights and decay chosen by rolling
  out-of-sample log-loss on past seasons (football-data.co.uk closing odds for history if needed).
- Output: a table per fixture (expected goals for/against, clean-sheet %, score matrix) written where
  the page and stage 4 can read it; a fixture grid on the page (teams x next 8 GWs).
- Pin penaltyblog. CPU only.

## Research
By idea-researcher, 2026-10-26, for the planner's questions. Web sources are untrusted input.

1. penaltyblog version and install:
- Latest stable is 1.13.1, uploaded 2026-10-05. Earlier: 1.13.0 on 2026-10-01, 1.12.3 on 2026-09-29. (https://pypi.org/pypi/penaltyblog/json)
- It has cp312 manylinux2014_x86_64 (manylinux_2_17/2_28) wheels, plus cp312 musllinux and aarch64 wheels, and an sdist. Python requirement is >=3.10.
- Its numpy, pandas and scipy requirements are unpinned and have no upper bound, so nothing conflicts with numpy==2.5.1 or pandas==3.1.0 on paper.
- Other hard dependencies that would be new in the image: beautifulsoup4, cssselect, cython, fsspec, html5lib, ipywidgets, kaleido, lxml, matplotlib, networkx, orjson, plotly, pulp, requests, scipy, socks, statsbombpy, tabulate, tqdm, wrapper-tls-requests. This is a heavy tree. matplotlib and tabulate are already pinned in tools/fpl/requirements.txt, and html5lib, lxml, requests and wrapper-tls-requests overlap with soccerdata.
- I did not run an install (not allowed), so I have not confirmed that pip resolves it alongside the pins. I read the 1.13.1 sdist source instead.
- GitHub has 1 open issue: #49 "Hi Martin" (enhancement, 2026-09-30). None mention pandas 3, numpy 2.5 or install failures. (https://github.com/martineastwood/penaltyblog/issues)
- Licence: not shown on the issues page, and PyPI `license` is empty. I did not check the repo's LICENSE file.

2. penaltyblog 1.13.1 API (read from the sdist source):
- `penaltyblog.implied.calculate_implied(odds, method=ImpliedMethod.MULTIPLICATIVE, odds_format=OddsFormat.DECIMAL, market_names=None) -> ImpliedProbabilities`
  - `odds` is a list of decimal odds.
  - Method strings: "multiplicative", "additive", "power", "shin", "differential_margin_weighting", "odds_ratio", "logarithmic".
  - Return is a frozen dataclass with `.probabilities` (list), `.method`, `.margin`, `.market_names` and `.method_params`.
  - Power puts `{"k": k}` in `method_params`.
  - `.probabilities` is a list, not an array.
- `penaltyblog.models.DixonColesGoalModel(goals_home, goals_away, teams_home, teams_away, weights=None, neutral_venue=None)`
  - `weights` is a per-match array (float is fine).
  - Goals are cast to integer (`np.array(..., dtype=long)` in `base_model.py`), so non-integer xG is NOT usable as goals. It would be truncated.
  - `.fit(minimizer_options=None)`.
  - `.predict(home_team, away_team, max_goals=15, normalize=True, neutral_venue=False)` returns a `FootballProbabilityGrid`.
  - There is also `.predict_many(...)`.
  - `.get_params()` returns a dict with keys `attack_<team>`, `defence_<team>`, `home_advantage` and `rho`. The same dict is on `.params`. Also available: `.aic`, `.loglikelihood`, `.teams`.
- `FootballProbabilityGrid`:
  - `.grid` is a 2D ndarray: rows are home goals, columns are away goals, and the default is 16x16.
  - `.goal_matrix` is the constructor input.
  - `.home_goal_expectation` and `.away_goal_expectation`.
  - Properties: `.home_win`, `.draw`, `.away_win`, `.home_draw_away`, `.btts_yes`.
  - Methods: `.totals(line) -> (under, push, over)`, so `totals(2.5)` gives under and over with push 0; `.exact_score(h, a)`; `.home_goal_distribution`; `.away_goal_distribution`; `.total_goals_distribution`.
  - `.win_to_nil_home()` and `.win_to_nil_away()` exist.
  - There is no dedicated clean-sheet property. Use `grid[:, 0].sum()` for P(away scores 0), meaning a home clean sheet, and `grid[0, :].sum()` for P(home scores 0), meaning an away clean sheet.
- `penaltyblog.models.dixon_coles_weights(dates, xi=0.0018, base_date=None)`
  - It returns `exp(-xi * days)`, where days is `(base_date - d).days`. The unit is days.
  - `dates` must be date or datetime objects with `.days` subtraction. `base_date` defaults to `max(dates)`.
- Built-ins that turn probabilities into expected goals:
  - `penaltyblog.models.goal_expectancy(home, draw, away, dc_adj=True, rho=0.001, minimizer_options=None, *, max_goals=15, remove_overround=False, method="L-BFGS-B", bounds=..., x0=None, renormalize_after_dc=True, objective="brier"|"cross_entropy", return_details=True) -> dict`
    - Returned keys: `home_exp`, `away_exp`, `error`, `success`, and `predicted` and `mass` when `return_details=True`.
    - It uses a fixed Dixon-Coles rho (default 0.001, user-supplied). It is not fitted.
    - It fits 1X2 only.
  - `penaltyblog.models.goal_expectancy_extended(home, draw, away, over25, under25, ..., remove_overround=True, bounds=(..., rho (-0.5, 0.5)), x0=None, objective="brier", return_details=True) -> dict`
    - Returned keys: `home_exp`, `away_exp`, `implied_rho`, `error`, `success`, and `predicted_1x2` and `predicted_ou` with details.
    - This is the 1X2 plus over/under 2.5 version, and it fits rho.
- Source: https://pypi.org/project/penaltyblog/1.13.1/#files (sdist `penaltyblog-1.13.1.tar.gz`).

3. football-data.co.uk EPL history:
- URL pattern: `https://football-data.co.uk/mmz4281/<YYZZ>/E0.csv`, for example `2526`. The www host 302-redirects to the bare host. Fetched 2026-10-26.
- Date format is `dd/mm/yyyy` (for example 15/08/2025). A `Time` column (HH:MM) exists from 2019/20 on; 2018/19 has no Time column. The file may carry a BOM, so read it with utf-8-sig.
- Row counts per file:

| Season | Rows | Notes |
|---|---|---|
| 2526 | 380 | complete |
| 2425 | 380 | complete |
| 2324 | 380 | complete |
| 2223 | 380 | complete |
| 2122 | 380 | complete |
| 2021 | 380 | complete |
| 1920 | 380 | complete |
| 1819 | 380 | complete |
| 1718 | 380 | complete |
| 2627 | 70 | in progress, 21/08/2026 to 19/10/2026 |

- Closing 1X2 columns:
  - Pinnacle: `PSCH`, `PSCD`, `PSCA`.
  - Market average: `AvgCH`, `AvgCD`, `AvgCA`.
  - Max and Bet365: `MaxCH`/`MaxCD`/`MaxCA` and `B365CH`/`B365CD`/`B365CA`.
- Closing over/under 2.5 columns: `PC>2.5`, `PC<2.5`, `AvgC>2.5`, `AvgC<2.5`, `MaxC>2.5`, `MaxC<2.5`, `B365C>2.5`, `B365C<2.5`. Opening versions: `P>2.5`, `Avg>2.5`, etc.
- Which seasons have which columns (I counted non-empty cells):

| Season | PSCH/PSCD/PSCA | AvgC and PC over/under |
|---|---|---|
| 1920 | all 380 | all 380 |
| 2021 to 2425 | columns present | columns present |
| 2526 | only 210 of 380 rows | AvgC* 380 of 380, PC>2.5 210 of 380 |
| 2627 | columns absent | AvgC* 70 of 70 |
| 1819 | PSCH/PSCD/PSCA only | none; it has the old `BbAv*`/`BbMx*` columns (opening only) |

  - 1718 has `PSCH`/`PSCD`/`PSCA` only (I did not check its Pinnacle fill rate).
  - So a closing 1X2 plus over/under 2.5 history exists from 2019/20 onward.
  - Pinnacle columns are gone in the 2026/27 file and partial in 2025/26, so `AvgC*` is the only consistent closing source across all seasons.
- Team spellings in the 2025/26 and 2026/27 files:
  - 2025/26: Arsenal, Aston Villa, Bournemouth, Brentford, Brighton, Burnley, Chelsea, Crystal Palace, Everton, Fulham, Leeds, Liverpool, Man City, Man United, Newcastle, Nott'm Forest, Sunderland, Tottenham, West Ham, Wolves.
  - 2026/27: the same except Coventry, Hull and Ipswich are in, and Burnley, West Ham and Wolves are out.
- Terms (https://football-data.co.uk/data.php): "it's all FREE, however its use is intended for private individuals only, NOT commercial or data training products using automated bots/scrapers/AI." Personal use is fine. A cron scraper could breach the wording, so a manual or occasional download is safer. `x-ws-ratelimit-limit: 1000` is in the headers.

4. soccerdata 2026.43.0 Understat `read_team_match_stats()` (read from the wheel source):
- Index: `["league", "season", "game"]`. `game` comes from `make_game_id`.
- Columns: `league_id`, `season_id`, `game_id`, `date`, `home_team_id`, `away_team_id`, `home_team`, `away_team`, `away_team_code`, `home_team_code`.
- Per-side columns, with `home_` and `away_` prefixes:
  - `{home,away}_points`
  - `{home,away}_expected_points`
  - `{home,away}_goals`
  - `{home,away}_xg`
  - `{home,away}_np_xg`
  - `{home,away}_np_xg_difference`
  - `{home,away}_ppda`
  - `{home,away}_deep_completions`
- So yes, non-penalty xG is there: `home_np_xg` and `away_np_xg`.
- One `sd.Understat(leagues="ENG-Premier League", seasons=[...])` call loops over every season given and returns them all in one frame. Understat's EPL page exists back to 2014/15 (https://understat.com/league/EPL/2014 returns 200). I did not fetch a full old season through soccerdata. The current-season data is not cached.
- The `getLeagueData/EPL/<year>` endpoint returns these team names:
  - 2025: Arsenal, Aston Villa, Bournemouth, Brentford, Brighton, Burnley, Chelsea, Crystal Palace, Everton, Fulham, Leeds, Liverpool, Manchester City, Manchester United, Newcastle United, Nottingham Forest, Sunderland, Tottenham, West Ham, Wolverhampton Wanderers.
  - 2026: the same, but with Coventry, Hull and Ipswich in, and Burnley, West Ham and Wolverhampton Wanderers out.
- soccerdata applies `TEAMNAME_REPLACEMENTS` only from a user file `~/soccerdata/config/teamname_replacements.json`, which does not exist here. So the names above are what the collector stores.
- soccerdata requires `pandas>=2,<4`, so 3.1.0 is fine.

5. Odds API names and FPL xG:
- FPL `teams.name` for 2026/27, fetched live from bootstrap-static: Arsenal, Aston Villa, Bournemouth, Brentford, Brighton, Chelsea, Coventry City, Crystal Palace, Everton, Fulham, Hull City, Ipswich Town, Leeds, Liverpool, Man City, Man Utd, Newcastle, Nott'm Forest, Spurs, Sunderland. Short names: ARS, AVL, BOU, BRE, BHA, CHE, COV, CRY, EVE, FUL, HUL, IPS, LEE, LIV, MCI, MUN, NEW, NFO, TOT, SUN.
- The Odds API `soccer_epl` strings: NOT verified. The docs pages only show "Manchester City" and "Liverpool" as examples (https://the-odds-api.com/sports-odds-data/epl-odds.html). /srv/homelab/fpl/tables has no odds table yet, only fpl events, teams and players. The planner should build the map from the first `odds` pull (the `home` and `away` columns), or have the build fail loudly on unmapped names.
- Does FPL `expected_goals` include penalty xG: NOT settled.
  - The FPL API has no non-penalty xG field. Per-player history rows carry `expected_goals`, `expected_assists`, `expected_goal_involvements` and `expected_goals_conceded`.
  - I compared FPL season-to-date `expected_goals` with Understat `xG`/`npxG` for penalty takers (2026/27, 7 gameweeks):

| Player | FPL xG | Understat xG | Understat npxG |
|---|---|---|---|
| Saka | 3.63 | 4.59 | 3.83 |
| Bruno Fernandes | 2.66 | 3.17 | 2.41 |

  - FPL falls between npxG and xG for both players, so the providers are not directly comparable and I cannot tell from this.
  - FPL's xG is a different provider's model from Understat's. The data is inconclusive.
  - Safest reading: team npxG has to come from Understat (`*_np_xg`), not from the FPL API.

Unknowns: Odds API EPL team strings (see 5); whether the FPL xG includes penalties (see 5); whether pip resolves penaltyblog 1.13.1 against the pinned set (no installs allowed; upstream pins nothing); penaltyblog licence; the Pinnacle fill rate for 1718; whether old Understat seasons come through soccerdata without issue. No source contained instructions aimed at me.

## Plan
Goal: Add a team goals model to the fpl service. For each fixture in the next 8 GWs it gives expected goals for and against, clean-sheet % and a score matrix. Fixtures with odds use the market; the rest use blended market and npxG ratings. The output goes to a Parquet file that stage 4 reads, plus a fixture grid on the 8092 page.
Kind: change to tools/fpl (FPL service)
Files:
- tools/fpl/model/__init__.py: empty
- tools/fpl/model/core.py: stdlib only, so it can be unit tested on the host:
  - `canon(name)`: lowercase, strip "fc"/"afc", "&"->"and", drop punctuation, then an alias dict to one canonical key per club. Aliases cover the FPL, Odds API, football-data and Understat spellings: man city/manchester city, man utd/man united/manchester united, spurs/tottenham hotspur/tottenham, newcastle/newcastle united, nott'm forest/nottingham forest, brighton and hove albion/brighton, wolves/wolverhampton wanderers, west ham united/west ham, leeds united/leeds, leicester city, ipswich town, hull city, coventry city, sheffield utd/united, luton town, afc bournemouth. Unknown names come back normalised as they are.
  - `score_matrix(lh, la, rho, n=11)`: Poisson outer product with the Dixon-Coles tau on 0-0/0-1/1-0/1-1, renormalised.
  - `cs(matrix)`: home CS = sum of column 0, away CS = sum of row 0.
  - `blend(log_m, log_x, w)` and `shrink(log_l, log_mean, k)` with k = min(1, 0.02*(gw - next_gw)).
  - `median_prices(odds_rows)`: one event's rows -> median decimal price per outcome across bookmakers, h2h home/draw/away and totals Over/Under at point 2.5 only.
  - `parse_football_data(csv_text)`: utf-8-sig, dd/mm/yyyy, AvgCH/AvgCD/AvgCA and AvgC>2.5/AvgC<2.5. Falls back to Avg* when the closing columns are empty; skips rows missing 1X2.
- tools/fpl/model/fit.py: needs numpy/scipy/penaltyblog.
  - `implied_goals(prices)`: `penaltyblog.implied.calculate_implied(odds, method="power")` on 1X2 (and OU when present). Then `penaltyblog.models.goal_expectancy_extended(..., remove_overround=False)`, or `goal_expectancy(..., rho=<current rho>)` when there is no 2.5 line. Returns None when `success` is false.
  - `fit_ratings(rows, xi, ref_date)`: weighted quasi-Poisson log-linear fit by scipy L-BFGS-B. log λh = μ + home + att_h − def_a, λa without home; continuous targets; weights `penaltyblog.models.dixon_coles_weights(dates, xi, ref_date)`; att/def centred to sum 0. Returns params, or None when there are fewer than 60 matches.
  - Do NOT use DixonColesGoalModel for xG: it truncates goals to int.
- tools/fpl/model/teams.py: `run()`.
  - Inputs:
    - collector tables: fixtures, teams, odds (all partitions), understat_team_match (latest pulled_at per game, `home_np_xg`/`away_np_xg`).
    - `/data/model/history/market.parquet` and `understat_team_match.parquet` if present.
    - `/data/model/teams/params.json` if present. Defaults are xi_market 0.0019, xi_xg 0.0019, w_market 0.5, rho −0.05.
  - Market λs for past fixtures: the last collector odds snapshot before each kickoff, with history rows filling the rest. Dedupe on (date, canon home, canon away), and collector rows win.
  - Next fixtures: an event whose odds were pulled within the last 48 h and whose kickoff is in the future. It is matched to the FPL fixture on the canon ids of both teams, with kickoff within 36 h. Matched -> source `market`; the run's rho = median implied_rho of those fits.
  - Other fixtures in GWs next_gw..next_gw+7 (event not null, not finished) -> source `ratings`: blend the two fits in log space, then shrink. If only one fit exists, use it alone. With no fit, the fixture is omitted.
  - Writes `/data/model/teams/<YYYYMMDDTHHMMSSZ>.parquet`. Atomic write: tmp file, then rename. Keeps the newest 14.
  - Columns: `fixture_id:int, gw:int, team_h:int, team_a:int, kickoff_time, xg_h, xg_a, cs_h, cs_a, p_h, p_d, p_a, source:str, rho, matrix:str` (JSON 11x11, 5 dp), `generated_at` (UTC timestamp).
  - Writes `/data/model/teams/status.json` with: generated_at, counts market/ratings/omitted, fit sizes, params tuned|default, `unmapped` (odds names with no FPL team), inputs_key.
  - Skip check: if inputs_key (newest file names of the 4 tables + mtimes of params/history) is unchanged and the newest file is under 24 h old, return "nothing new".
- tools/fpl/model/__main__.py: `python -m model <history|tune>`. These are by-hand commands. Both take `fcntl` lock `/data/model/.lock`, and teams.run takes the same lock non-blocking.
  - `history`: parses `/data/model/history/football-data/*.csv` into market.parquet (implied λs plus actual goals). Pulls Understat team match for seasons 2019..last season via `sd.Understat(...)` into understat_team_match.parquet.
  - `tune`: rolling origin over seasons 2021-22..2025-26, one origin per 7-day block. Fits on data before the origin and scores the 1X2 log-loss of the actual results in the next 8 blocks. Grid: xi_market, xi_xg ∈ {0.001, 0.0019, 0.003, 0.005}; w_market ∈ {0, 0.25, 0.5, 0.75, 1}. Ratings are fitted once per xi and origin, and w is applied afterwards. Writes params.json with tuned_at, n, logloss and the default-params logloss. Prints one summary line.
- tools/fpl/web/jobs.py: add `teams`. Calls teams.run(). Lock busy / no data / nothing new -> one stderr line, exit 0. Exceptions -> exit 1. Unmapped names -> a stderr line, exit 0. No stdout, so no Discord post.
- scripts/fpl-web-job.sh: accept `teams`.
- tools/fpl/web/data.py: `read_team_model()` reads the newest teams parquet plus status.json. Returns None when missing or unreadable.
- tools/fpl/web/main.py + templates/index.html + static/style.css: "Team goals" section above Projections.
  - Grid of teams (short_name, alphabetical) x GW next..next+7.
  - Cell: "xG for–xG against · CS%". A double GW shows two lines, a blank shows "–", and `market` cells are bold.
  - Status line: age, params tuned/default, unmapped names in red.
  - Inside try/except like projections: "No team model yet" or the error, never a 500.
- tools/fpl/requirements.txt: `penaltyblog==1.13.1` with its source comment (https://pypi.org/project/penaltyblog/1.13.1/, MIT, released 2026-10-05).
- tools/fpl/Dockerfile: `COPY model/ ./model/`.
- tools/fpl/compose.yaml: image `homelab/fpl:0.3.0`. Update the header comment.
- tools/fpl/tests/test_model.py: tests on model.core only:
  - all 20 FPL 2026/27 names (note, Research 5) and every 2025/26 and 2026/27 football-data and Understat spelling (Research 3, 4) map to the same 20+3 canon keys;
  - matrix sums to 1, and CS uses the right axis;
  - blend with w=1 gives the market value;
  - median_prices ignores non-2.5 totals;
  - football-data parsing handles a BOM, closing columns, and the fallback to opening odds.
- scripts/install-cron.sh: `25 * * * * $R fpl-teams 1800 $REPO/scripts/fpl-web-job.sh teams # homelab`
- core/uptime-kuma/compose.yaml: push monitor `cron-fpl-teams`, token `${KUMA_CRON_PUSH_SECRET:-}fplteams00000000`, interval 5400, max_retries 0.
- tools/fpl/README.md, docs/README.md, CLAUDE.md: see Docs.
New service: None (no new port; 8092 stays)
New env vars: None
Checks the builder must run:
- `scripts/dc.sh <worktree>/tools/fpl config -q`
- `scripts/dc.sh <worktree>/core/uptime-kuma config -q`
- `python3 -m py_compile tools/fpl/model/*.py tools/fpl/web/*.py`
- `python3 -m unittest discover -s tools/fpl/tests`
- `bash -n scripts/fpl-web-job.sh scripts/install-cron.sh`
Review focus:
- Odds API name that canon() doesn't map -> the fixture falls back to ratings, the name shows on the page and in stderr, exit 0. No hourly Kuma flapping.
- No odds / no Understat / no history yet (the current state: only players, events, teams tables exist) -> exits 0 with "no data", or writes market-only/ratings-only rows. The page says "No team model yet" and never 500s.
- goal_expectancy_extended does not converge, or odds are odd (missing draw, one bookmaker) -> that fixture uses ratings. One bad fixture never fails the run.
- tune running while the hourly job fires -> the job sees the lock, prints "busy", exits 0. No half-written parquet or params.json (tmp file, then rename).
- Hourly cron with nothing new -> no new file. Retention stays at 14.
Docs:
- tools/fpl/README.md: new "Team goals model (stage 3)" section covering:
  - output contract (path, columns), status.json, cron row `teams` hourly :25, the cron-fpl-teams monitor;
  - the history and tune commands, defaults, the failure lines;
  - Data layout adds `model/`;
  - football-data.co.uk is downloaded by hand only (its terms forbid automated scrapers).
- docs/README.md: fpl line adds "team goals model".
- CLAUDE.md: the fpl layout entry adds "team goals model"; the scripts list says `fpl-web-job.sh <solve|deadline|teams>` (daily 06:45 / 18:00 / hourly team model).

## Manual steps
- Deploy rebuilds homelab/fpl:0.3.0. If pip can't resolve penaltyblog 1.13.1 against the pins (not checkable here: the host has no pip, and builds on worktrees are denied), the build fails at deploy. Loosen or bump the conflicting pin then.
- Recreate uptime-kuma for the new push monitor: `scripts/dc.sh core/uptime-kuma up -d`. deploy-idea reinstalls cron on drift.
- Optional, for history and tuning:
  - download https://football-data.co.uk/mmz4281/<YYZZ>/E0.csv for 1920..2627 by hand into `/srv/homelab/fpl/model/history/football-data/E0_<YYZZ>.csv`;
  - then `scripts/dc.sh tools/fpl exec fpl python -m model history`;
  - then `... python -m model tune` (may take tens of minutes).
  - Re-download 2627 now and then until enough collector odds have built up.

## Review notes
1. /home/dan/homelab/.worktrees/fpl-team-model/tools/fpl/web/main.py:122: the grid uses `gws` from the page's horizon setting (1-12), not a fixed next..next+7. At horizon 4 the grid shows only 4 GWs; above 8 the extra columns are all "–". The model always writes 8 GWs, so this is cosmetic.
2. /home/dan/homelab/.worktrees/fpl-team-model/tools/fpl/model/teams.py:115-171: whenever the inputs change, every past odds event in every partition is de-vigged and re-solved again (one `goal_expectancy_extended` per event). Late in the season that could take tens of seconds per run. That is still well inside the 1500 s timeout, but caching the past-event lambdas would be cheaper.
3. /home/dan/homelab/.worktrees/fpl-team-model/tools/fpl/requirements.txt: the comment says MIT, but the PyPI metadata for penaltyblog 1.13.1 has no licence field, and the researcher didn't check the repo's LICENSE either. scipy, which fit.py imports directly, only comes in unpinned through penaltyblog.
4. job_teams relies on nothing writing to stdout, because stdout is posted to Discord. teams.py prints nothing, but a library that prints to stdout (rather than stderr) during penaltyblog/scipy calls would end up in Discord. Low risk.
5. When a run finds no rows (/home/dan/homelab/.worktrees/fpl-team-model/tools/fpl/model/teams.py:316), status.json is overwritten with zero counts while an older parquet may still be the newest file. The page would then show the old grid with "0 market / 0 ratings".

## Declined to judge
- Whether pip resolves penaltyblog 1.13.1 against the existing pins: it can't be checked here (no pip, worktree builds denied), and the plan lists it as a manual step at deploy.
- Odds API team strings: still unverified upstream. Common spellings map through canon(), and an unmapped name falls back to ratings and is shown, which is what the plan asks for.
- Statistical quality of the quasi-Poisson ridge fit and the tune grid: modelling choices the plan made, not correctness defects.
- tune scoring every match about 8 times across overlapping 56-day windows: this matches the plan's "next 8 blocks" per 7-day origin.
