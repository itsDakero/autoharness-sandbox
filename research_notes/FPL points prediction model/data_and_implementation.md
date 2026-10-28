# FPL expected-points model: data sources, tooling and evaluation (October 2026)

Researched 2026-10-25. The FPL API field lists below were checked directly against the live API today. I fetched bootstrap-static, element-summary/1, event/1/live and fixtures?event=1 from this server; the current gameweek is GW8 and there are 11,178,209 managers. Those claims cite the endpoint URL itself.

## 1. Official FPL API: endpoints, fields, rate limits, historical archives

### Takeaway
The official FPL API needs no login for its read endpoints and is rich enough to carry a model. As of 2025/26 it serves Opta-derived xG, xA, xGI and xGC per player per match, plus defensive-contribution counts and their scoring (2 pts for DEF, MID and FWD). Historical archives are thinner than before: vaastav's dataset dropped weekly updates after 2024-25. A self-hosted pipeline should therefore snapshot the API itself every gameweek.

### Cited Findings
- **`/api/bootstrap-static/`** has these top-level keys: `chips, events, game_settings, game_config, phases, teams, total_players, element_stats, element_types, elements` — [bootstrap-static](https://fantasy.premierleague.com/api/bootstrap-static/)
  - Each player (`elements[]`) includes: `expected_goals, expected_assists, expected_goal_involvements, expected_goals_conceded` (plus `_per_90` versions), `defensive_contribution, defensive_contribution_per_90, clearances_blocks_interceptions, tackles, recoveries, chance_of_playing_this_round, chance_of_playing_next_round, status, news, news_added, ep_this, ep_next, form, now_cost, selected_by_percent, transfers_in_event, bps, ict_index, influence/creativity/threat, starts, starts_per_90, penalties_order, direct_freekicks_order, corners_and_indirect_freekicks_order, opta_code`. Newer fields are `price_change_projections` (a list of offset, projected_percent and likelihood), `scout_risks` and `scout_news_link` — [bootstrap-static](https://fantasy.premierleague.com/api/bootstrap-static/)
  - `game_config.scoring` holds the scoring rules in machine-readable form. Goals score GKP 10, DEF 6, MID 5, FWD 4. Clean sheets score GKP/DEF 4 and MID 1. Assists are 3, saves 1 and pen saves 5. `defensive_contribution` is {DEF 2, MID 2, FWD 2, GKP 0}. Manager (`mng_*`) keys exist but are 0 — [bootstrap-static](https://fantasy.premierleague.com/api/bootstrap-static/)
  - `events[]` fields include `deadline_time, finished, data_checked, is_current, is_next, chip_plays, most_captained, top_element, average_entry_score` — [bootstrap-static](https://fantasy.premierleague.com/api/bootstrap-static/)
  - Example of the injury flag format: `status: 'i', news: 'Back injury - Unknown return date', chance_of_playing_next_round: 0` — [bootstrap-static](https://fantasy.premierleague.com/api/bootstrap-static/)
- **`/api/element-summary/{id}/`** returns `fixtures, history, history_past`. Each `history` row is one match: `minutes, starts, goals_scored, assists, expected_goals, expected_assists, expected_goal_involvements, expected_goals_conceded, defensive_contribution, clearances_blocks_interceptions, tackles, recoveries, bps, bonus, saves, total_points, value, selected, transfers_in/out, was_home, opponent_team, kickoff_time, round, fixture`. Each `fixtures` row carries a `difficulty` (FDR) — [element-summary/1](https://fantasy.premierleague.com/api/element-summary/1/)
- **`/api/event/{gw}/live/`** returns `elements[]`. Each element has `stats` (the same per-match stat set, plus `in_dreamteam` and `played`) and `explain[]`, which breaks points down by identifier, e.g. `{'identifier':'minutes','points':2,'value':90}` — [event/1/live](https://fantasy.premierleague.com/api/event/1/live/)
- **`/api/fixtures/?event={gw}`** returns per fixture: `id, code, event, kickoff_time, team_h, team_a, team_h_difficulty, team_a_difficulty, team_h_score, team_a_score, started, finished, finished_provisional, minutes, pulse_id, stats`. The `stats` identifiers are goals_scored, assists, own_goals, penalties_saved/missed, yellow/red_cards, saves, bonus, bps, defensive_contribution — [fixtures](https://fantasy.premierleague.com/api/fixtures/?event=1)
- I tested no endpoints beyond these four. The community-known ones (`/api/entry/{id}/`, `/api/entry/{id}/history/`, `/api/entry/{id}/event/{gw}/picks/`, `/api/leagues-classic/{id}/standings/`, and `/api/my-team/{id}/`, which needs a login) are listed as unverified in the Gaps section. A community Elixir wrapper documents `get_event_live(event_id)`, which returns per-element live records — [hexdocs Fpl.Event](https://hexdocs.pm/fpl/Fpl.Event.html)
- **vaastav/Fantasy-Premier-League** covers 2016-17 onward, organised per season: `cleaned_players.csv`, `gws/gwN.csv`, `gws/merged_gw.csv`, `players/<name>/gws.csv` and `history.csv`, `players_raw.csv`. It also has an `understat.py` script. **Weekly updates stopped after 2024-25.** There are now 3 updates a season: at the start of the season, at the end of the January window, and at the end of the season. The README warns that the `xP` column comes from FPL's `ep_this` and may contain post-match info, so it should be shifted or excluded for ML (a leakage trap) — [vaastav GitHub](https://github.com/vaastav/Fantasy-Premier-League)

### Inferences
- `ep_next` is FPL's own baseline. Snapshot it before each deadline, because the field updates and its historical archive value may be leaky (see the vaastav warning above).
- The API holds no historical snapshots of `chance_of_playing`, `news` or prices. A backtest that wants "what was known at the deadline" needs your own snapshots, e.g. bootstrap-static saved hourly to Parquet. Start collecting now.
- Defensive contribution has been scored since 2025/26, so there are only about 1.25 seasons of DC-scored data. Training a DC-probability model on earlier seasons needs the raw CBI, tackles and recoveries counts. FPL only exposes those from 2025/26.
- No rate limits are published. Community practice is to cache and poll politely, e.g. bootstrap a few times a day and live every 1–2 minutes during matches only.

### Gaps
- I found no official documentation or published rate limits. Entry, picks and league endpoints were not tested in this session.
- I did not verify whether vaastav's 2025-26 folder contains the xG and DC columns.

## 2. xG and event data sources in 2026

### Takeaway
**FBref lost its Opta advanced stats on 20 January 2026, not in 2025.** xG, progressive passes and SCA are gone, and only basic stats remain. For EPL player xG the easiest legal-ish source is the FPL API itself, which is Opta-derived and per match. Understat (scraped) is the long-history alternative, from 2014. soccerdata v1.9.x wraps FBref, Understat, Sofascore, WhoScored, ESPN, ClubElo, SoFIFA and Match History (football-data.co.uk).

### Cited Findings
- On 20 Jan 2026 Sports Reference announced that advanced stats would be removed from FBref "effective immediately". Stats Perform (Opta) had terminated FBref's feed access, citing a violation of their agreement. Examples removed were xG, progressive passes and shot-creating actions. Basic info such as scores and golden-boot tables remains — [The IX](https://www.theixsports.com/the-ix-soccer/fbrefs-loss-advanced-stats-womens-soccer-data-accessibility/); also [Valora Analitik](https://www.valoraanalitik.com/comunidad-futbolera-pierde-plataformas-conocidas-estadisticas-datos-gratis/)
- I found no evidence that FBref's advanced data has returned as of October 2026 (search returned nothing) — [search: The IX, Valora](https://www.theixsports.com/the-ix-soccer/fbrefs-loss-advanced-stats-womens-soccer-data-accessibility/)
- soccerdata (docs version v1.9.2.dev) supports ClubElo, ESPN, FBref, Match History, Sofascore, SoFIFA, Understat and WhoScored. It also mentions FiveThirtyEight and Football-Data.co.uk. Install with `pip install soccerdata` — [soccerdata docs](https://soccerdata.readthedocs.io/en/latest/). An older PyPI page warns that changes to the scraped sites will break the package — [PyPI soccerdata 1.0.1](https://pypi.org/project/soccerdata/1.0.1)
- ScraperFC is another multi-source scraper, v3.4.0 (2025-08-11) — [PyPI ScraperFC](https://pypi.org/project/scraperfc)
- OpenFPL, a 2025 open-source model, trained on FPL API and Understat data via the vaastav dataset. It filled missing 2020-21 Understat values by kNN imputation — [OpenFPL arXiv](https://arxiv.org/html/2508.09992v1)
- The FPL API carries Opta xG/xA/xGI/xGC per player-match, plus `opta_code` for joining to Opta IDs — [element-summary](https://fantasy.premierleague.com/api/element-summary/1/)

### Inferences
- Recommended xG stack: FPL API for current-season per-match player xG and xGC (clean, official, and the same feed FPL itself uses), plus Understat for history and shot-level team xG (2014+).
- FotMob and Sofascore (Opta-sourced xG and shot maps) are optional enrichments, reached through soccerdata or unofficial JSON endpoints.
- StatsBomb open data is for research only. It has a few full seasons and tournaments, not continuous EPL, so it is no good for a live model.
- Legal/ToS: Understat, FotMob, Sofascore and WhoScored don't offer licensed public APIs. Scraping is a grey area: tolerable at low volume for personal use, but redistribution is risky. The FBref episode shows providers do act on misuse.
- Paid options only make sense if scrapers break. Opta/Stats Perform is enterprise-priced. Sportmonks and API-Football sell xG add-ons.

### Gaps
- I did not verify these in this session: Understat's current uptime, terms or anti-bot status; the `understatapi` package's state; Sportmonks and API-Football 2026 xG pricing; FotMob and Sofascore endpoint stability; and StatsBomb's current open-data EPL coverage. Each needs a fresh check before building.

## 3. Betting odds sources (UK user)

### Takeaway
Match odds (1X2, totals, handicap) are easy and cheap to get. **Player-level EPL props are the hard part.** The Odds API has anytime scorer, assists, shots, SoT and cards keys for EPL, but **only from US bookmakers**. Pinnacle closed its public API on 23 July 2025. A Betfair Exchange live key costs a one-off £499. football-data.co.uk remains the free source of historical match closing odds. Practical approach: derive team goal expectancy and clean-sheet probability from match odds (1X2 plus over/under 2.5), then distribute it to players using xG shares. Use player props only where available.

### Cited Findings
- **The Odds API pricing:** Starter is free (500 credits a month, most bookmakers). 20K credits cost $30 a month, 100K $59, 5M $119 and 15M $249, all with every bookmaker. All plans list "all sports, all betting markets". Historical snapshots go back to 2020 — [the-odds-api.com](https://the-odds-api.com/)
- **Odds API credit cost** = markets × regions per call. The featured `/odds` endpoint is cheaper than per-event queries. EPL featured markets are h2h, spreads and totals. Additional markets include `alternate_totals, double_chance, player_shots_on_target`. Historical featured markets go back to mid-2020, other markets to mid-2023, and they require a paid plan — [EPL odds page](https://the-odds-api.com/sports/epl-odds.html)
- **Odds API soccer prop keys:** `player_goal_scorer_anytime, player_first_goal_scorer, player_last_goal_scorer, player_assists, player_shots, player_shots_on_target` (plus alternates), `player_to_receive_card, player_to_receive_red_card`. These are available for EPL, Ligue 1, Bundesliga, Serie A, La Liga and MLS, but the page says *"Coverage is currently limited to US bookmakers."* Props come per event via `/events/{eventId}/odds` — [betting markets](https://the-odds-api.com/sports-odds-data/betting-markets.html)
- **Alternatives** carrying EPL anytime/first/last scorer props: SportsGameOdds (claims 85+ bookmakers) — [SportsGameOdds EPL](https://sportsgameodds.com/blog/premier-league-betting-markets-api). TheStatsAPI has an `anytime_goalscorer` key, mostly Bet365 Over-only prices — [TheStatsAPI player odds](https://www.thestatsapi.com/docs/api-reference/matches/player-odds). OddsPapi also covers EPL — [OddsPapi](https://oddspapi.io/blog/?p=3180)
- **Betfair Exchange API:** creating app keys gives a delayed key, which is active immediately and good for development, and a live key, which needs an application. Live-key activation for personal betting is a **one-off £499**, taken from a funded, KYC-verified account. Apply via developer.betfair.com → Exchange API → For My Personal Betting — [Betfair developer support](https://support.developer.betfair.com/hc/en-us/articles/115003864651-How-do-I-get-started)
- **Betfair historical data** (historicdata.betfair.com): the BASIC tier is free (last traded prices), with paid ADVANCED/PRO tiers. An official Excel workbook exists, and Python parsers include betfair_data and betfairutil — [Betfair historic-data-workbook](https://github.com/betfair/historic-data-workbook); [betfairutil](https://pypi.org/project/betfairutil); tier pricing per an aggregator, [apis.io](https://apis.io/plans/betfair/betfair-plans-pricing/)
- **Pinnacle** closed its public API on 23 July 2025. Third-party resellers (pinnapi, PinnOdds) now sell Pinnacle-sourced feeds — [odds-api.io blog](https://odds-api.io/blog/pinnacle-api-shutdown-alternatives); [DEV Community](https://dev.to/ryankr/pinnacle-killed-its-public-api-heres-how-to-get-pinnacle-odds-in-2026-with-code-39pe); [sportsapis.dev pinnapi](https://sportsapis.dev/apis/pinnapi)
- **football-data.co.uk:** a 2025/26 secondary source says it still provides pre-closing and closing odds from about 20 bookmakers for every season from 2000/01 to 2025/26 — [Networked Substack](https://networked.substack.com/p/a-view-from-the-pinnacle). I could not fetch notes.txt or the CSVs directly (HTTP 429).

### Inferences
- For a UK user the Odds API's player props are US-book prices (e.g. DraftKings, FanDuel) on EPL. They are usable as probability signals after removing the vig, but they are not UK prices.
- Betfair's free delayed key is likely enough to read exchange match odds and maybe goalscorer markets for modelling, without paying £499, because no transacting is needed. Check whether the delayed key's terms allow this.
- Typical lead time: match odds appear about a week or more ahead. Player props usually appear only 1–3 days before kickoff, so a multi-GW model must fall back to a team-strength model (Dixon-Coles or Elo via penaltyblog) beyond the next GW.
- Oddschecker and OddsPortal scraping is ToS-prohibited and fragile. Use it only for small personal backfills, if at all.

### Gaps
- I could not confirm the current football-data.co.uk column names, e.g. whether the Pinnacle `PSCH/PSCD/PSCA` columns are still populated after Pinnacle's API closure. Fetching was rate-limited.
- I did not verify Betfair historical PRO/ADVANCED prices or whether Betfair lists EPL player markets (anytime scorer, to-assist, shots) on the exchange.
- I found no official statement of the Odds API's exact US-book list for EPL props, or how far ahead they are posted.

## 4. Injury and team-news sources

### Takeaway
Only the FPL API offers a structured, free injury feed: `status`, `news`, `chance_of_playing_*` and `news_added`. Fantasy Football Scout, RotoWire, Premier Injuries and press-conference trackers have **no public APIs**. Community projects scrape RotoWire lineups, and some Apify actors resell aggregated injury and lineup data.

### Cited Findings
- FPL status/news/chance fields are listed above (e.g. 'i', 'Back injury - Unknown return date', 0). A new `scout_risks` list also exists — [bootstrap-static](https://fantasy.premierleague.com/api/bootstrap-static/)
- A RotoWire lineup scraper (in an FPL MCP server repo) labels players OUT, DOUBTFUL, EXPECTED or CONFIRMED — [rotowire_scraper.py](https://glama.ai/mcp/servers/@lewis-king/fpl-mcp-server/blob/dfdb791c6769d5584f7b4185fc0695b3643b5db8/src/fpl_server/rotowire_scraper.py)
- An Apify "Soccer Intelligence API" claims FPL injury status and predicted XIs at $1.50 per league. It has few users and a 0.0 rating — [Apify](https://apify.com/mea/live-football-data-api)
- Fantasy Football Scout has predicted line-up and injury pages, but I found no API documentation — [FFS profile pages](https://www.fantasyfootballscout.co.uk/profiles/bst)
- Press-conference and predicted-lineup roundups are published as articles, e.g. AllAboutFPL — [AllAboutFPL press conferences](https://allaboutfpl.com/category/fpl-press-conference-updates/)
- OpenFPL uses only the FPL availability tags (0/25/50/75/100%) as its match-status features — [OpenFPL arXiv](https://arxiv.org/html/2508.09992v1)

### Inferences
- Minutes prediction is the biggest error source. The paper notes that commercial tools such as FPL Review blend betting odds into expected-minutes projections — [OpenFPL arXiv](https://arxiv.org/html/2508.09992v1)
- For a personal model: FPL flags plus your own rolling start-rate model plus an optional manual override table edited in the dashboard. Scraping RotoWire is the only automated predicted-XI option, so check its ToS.

### Gaps
- I did not research Premier Injuries' site and terms, or whether official team sheets (about 75 min before kickoff) can be obtained via any free API.

## 5. Model evaluation and backtesting

### Takeaway
Use walk-forward evaluation by gameweek: train on everything before the deadline of GW t, predict GW t..t+2, and freeze the features as they were at the deadline. Report RMSE and MAE overall **and by return category**. Score event probabilities (goal, assist, CS, DC, 60+ mins) with log-loss/Brier and calibration plots. Then judge decisions by simulating a season with the optimiser. Baselines: last-5 average, FPL `ep_next`, and a bookmaker-only model. Reference numbers from OpenFPL (2024-25, GW32-38, 1-GW horizon): RMSE around 0.7–0.8 for zero-point players, 1.2–1.3 for blanks (≤2), about 1.5–1.6 for 3–4 pointers, and about 5.1–5.2 for hauls (≥5).

### Cited Findings
- OpenFPL design: development by 5-fold CV split **by team** on 2020-21 to 2023-24. Prospective test on 2024-25 GW32–38 using data available the day before each deadline. Horizons of 1, 2 and 3 GW. RMSE is the primary metric and MAE secondary. Categories are Zeros (0, didn't play), Blanks (≤2), Tickers (3–4) and Haulers (≥5) — [OpenFPL arXiv](https://arxiv.org/html/2508.09992v1)
- Results at 1 GW, RMSE (MAE): Zeros FPL Review 0.689 (0.237) vs OpenFPL 0.818 (0.427). Blanks 1.189 (0.597) vs 1.291 (0.749). Tickers 1.594 (1.227) vs 1.517 (1.127). Haulers 5.172 (4.381) vs 5.142 (4.317). Both cut RMSE by 5–34% versus a "Last 5" baseline — [OpenFPL arXiv](https://arxiv.org/html/2508.09992v1)
- The OpenFPL model is a per-position ensemble of XGBoost and Random Forest, taking the median of 50 models. It has about 200 features from rolling windows of 1/3/5/10/38 matches, and **no betting odds** — [OpenFPL arXiv](https://arxiv.org/html/2508.09992v1)
- The vaastav `xP` (ep_this) column may contain post-match info, so it should be shifted or excluded (a leakage example) — [vaastav GitHub](https://github.com/vaastav/Fantasy-Premier-League)
- A community comparison of prediction sites for GW1 2025 exists — [FPL Watchmen Substack](https://fplwatchmen.substack.com/p/fpl-2025-gw1-analysis-of-prediction)

### Inferences
- Leakage checklist:
  - Use as-of-deadline snapshots of flags, prices and odds. Closing odds are only legitimate if the predictions are made at the deadline, not after.
  - Exclude same-GW `ep_this`, `bps` and `bonus`.
  - Don't let team-level xG include the target match.
  - Fit any scaler or encoder inside each fold.
  - Split by time, not randomly. Team-split CV as in OpenFPL tests generalisation, but a pure walk-forward is closer to live use.
- Decision-level evaluation: replay the season with the same optimiser and rules (FTs, hits, chips) under each model, then compare total points and the implied overall rank against the official percentiles from `events[].average_entry_score` and `highest_score`. Also measure captaincy hit rate and top-k precision, e.g. Spearman ρ within position, because ranking matters more than absolute error.
- Very low RMSE on Zeros mostly reflects the minutes model, so report it separately.
- Hauls are dominated by noise (RMSE about 5 even for the best). Gains realistically come from minutes and calibration.

### Gaps
- I found no published accuracy numbers for FPL's own `ep_next`, or for a bookmaker-only model, on a common test set. These have to be measured in your own backtest.
- OpenFPL's test window is small (7 GWs) and self-reported, with no independent replication found.

## 6. Tech stack, architecture and reusable open-source repos

### Takeaway
A small set of Python containers fits the homelab:
- Ingest: a cron-driven collector for the FPL API, odds (Odds API free/20K tier, or the Betfair delayed key) and Understat via soccerdata.
- Storage: Parquet snapshots plus a DuckDB or SQLite (or Postgres) warehouse.
- Model: penaltyblog or a Dixon-Coles team model, plus LightGBM or a numpyro hierarchical player model.
- Optimise: PuLP or HiGHS MILP for transfers and captaincy.
- Serve: a FastAPI or Streamlit dashboard.

AIrsenal (MIT, Dockerised, v2 released Sep 2026) and OpenFPL (open models) are the most reusable bases.

### Cited Findings
- **AIrsenal** (Alan Turing Institute, MIT):
  - It has a team-level scoreline model and a player-level goal-involvement model, plus heuristics.
  - `airsenal db update` pulls the FPL API (results, fixtures, players, injuries).
  - `airsenal optimize transfers` and `airsenal optimize squad` plan over a multi-GW horizon (3 by default), chips included.
  - It ships a Dockerfile with a data volume, and jax is a dependency.
  - An "AIrsenal v2 Released" notice is dated 25 Sep 2026. The PyPI package is marked work-in-progress, so install from source.
  - [AIrsenal GitHub](https://github.com/alan-turing-institute/AIrsenal)
- **OpenFPL** model and inference code — [github.com/daniegr/OpenFPL](https://github.com/daniegr/OpenFPL) (via [arXiv](https://arxiv.org/html/2508.09992v1))
- **soccerdata** for Understat, Sofascore, ClubElo and Match History ingestion — [soccerdata docs](https://soccerdata.readthedocs.io/en/latest/)
- **Betfair parsers:** betfair_data and betfairutil — [awesome.ecosyste.ms betfair_data](https://awesome.ecosyste.ms/projects/github.com%2Ftarb%2Fbetfair_data); [betfairutil PyPI](https://pypi.org/project/betfairutil)
- FPL scoring rules are available programmatically from `game_config.scoring`, so the points function can be data-driven rather than hard-coded — [bootstrap-static](https://fantasy.premierleague.com/api/bootstrap-static/)

### Inferences
- Suggested architecture (fits the repo rules: one compose per service under `tools/`, pinned images, Kuma healthcheck, cron via `cron-run.sh`):
  1. **`fpl-ingest`** (cron):
     - bootstrap-static every 1–3 h, archived as dated Parquet so flags and prices are kept as of each time.
     - fixtures and element-summary after each GW.
     - event live during matches.
     - Odds API h2h/totals daily, with props on match-eve.
     - Understat weekly.
  2. **Storage:** raw JSON/Parquet in `${APPDATA_PATH}/fpl/raw/`, with DuckDB for analytics. SQLite or Postgres is only needed if the dashboard writes much.
  3. **Model:**
     - Team model: penaltyblog's Dixon-Coles/Bivariate Poisson fitted on goals/xG, blended with de-vigged market 1X2 and O/U for λ_home and λ_away. This gives CS probability and team goals.
     - Player model: minutes (P(start), P(60+)) from flags and rolling starts. Goal and assist shares from rolling xG/xA shares, using Bayesian shrinkage in numpyro or PyMC, or LightGBM. Anytime-scorer props, when present, act as a calibration anchor.
     - DC model: Poisson or negative-binomial on CBI + tackles (+ recoveries for MID/FWD), giving P(over threshold).
     - Bonus via a BPS approximation.
     - Expected points = Σ P(event) × points from `game_config.scoring`.
  4. **Optimiser:** PuLP with the CBC or HiGHS solver (`highspy`) MILP. Constraints are budget, 3-per-team, formation, FTs/hits and a horizon of 3–6 GW. OR-Tools CP-SAT is an alternative.
  5. **Dashboard:** FastAPI + HTMX or Streamlit, on a new port from the table.
- Bayesian (numpyro on CPU) is fast enough for about 700 players weekly. The GTX 970 is not useful for JAX (no modern CUDA support), so plan for CPU.

### Gaps
- I did not verify in this session the current versions, licences or maintenance of penaltyblog, fpl-optimization (sertalpbilal), the `fpl` PyPI package, highspy or PuLP. Check them before pinning.
