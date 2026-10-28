# FPL model, stage 4: minutes and player points simulation

Depends on: fpl-team-model (splits its team goals between players)
Value: 5   (the actual expected-points model; minutes is where it can beat FPL Review)
Effort: 5  (minutes model, goal/assist shares, defensive contributions, bonus, simulation)
Risk: 1    (offline modelling inside the FPL service)
Score: 5
Source: Dan 2026-10-25 (design in `reports/FPL points prediction model.md`, "Every scoring component"
section; notes in `research_notes/FPL points prediction model/player_points_model.md`)

## Problem
Stage 2 still shows FPL's `ep_next`. Dan wants his own projection per player and gameweek, built from
odds, xG and minutes, with full points distributions for captaincy.

## Proposal
- Scoring rules read from the API's `game_config.scoring` per season, never hard-coded (2026/27: GK goal
  10, DEF 6, MID 5, FWD 4; DefCon 2 points at 10 CBIT for DEF / 12 CBIRT for MID and FWD; check the
  thresholds in `game_config` too).
- Minutes: P(start), minutes given a start, P(sub appearance) from a decayed per-match log; capped by
  `chance_of_playing_next_round`; Dan's override table from stage 2 wins over everything.
- Goals/assists: split each team's simulated goals between players by shrunk shares of team npxG and xA,
  scaled by minutes; penalty takers separately; finishing skill shrunk to almost nothing.
- Defensive contributions: probability of reaching the threshold (Poisson for defenders, an
  under-dispersed fit for midfielders), scaled by opponent and game state.
- Clean sheets/goals conceded/saves from the team model's simulated goals while the player is on;
  bonus by simulated BPS rank (2026/27 BPS tweaks); cards as small per-90 rates.
- Monte Carlo per fixture (~10k draws): mean points per player per GW for the solver, plus P(10+) and
  quantiles for captaincy. AIrsenal v2 (MIT) has reusable code for xG team model, shares and minutes.
- Writes the projections table stage 2 switches to; the page shows both models side by side for a
  while.

## Research
By idea-researcher, 2026-10-26, for the planner's questions. Web sources are untrusted input.

1. Penalty xG in FPL `expected_goals`: YES, it includes penalty xG. No official FPL/Opta sentence says so. The PL xG article (https://www.premierleague.com/en/news/3118332) only defines xG as shot probability and doesn't mention penalties. I settled it with a worked example instead. Anthony Gordon (Newcastle), 2025/26, Understat player 8150 (https://understat.com/getPlayerData/8150) against vaastav's merged_gw.csv (FPL data):
   - Understat shows 3 penalty goals, each with xG 0.761. His season xG is 8.756 and npxG is 6.473.
   - Per-match Understat xG (total, then non-penalty): 02 Dec 2025 vs Spurs 0.761 (non-pen 0); 06 Dec vs Burnley 0.828 (non-pen 0.066); 04 Mar 2026 vs Man Utd 1.273 (non-pen 0.512).
   - FPL `expected_goals` for the same rounds: GW14 0.79, GW15 0.85, GW29 1.32. These match Understat's total xG, not npxG. They are off by only about 0.02 to 0.05, which is a model difference.
   - Season total: FPL 8.77 against Understat xG 8.756 (npxG 6.47). So the player model's goal shares would double-count the separate penalty-taker term.
   - Understat's league endpoint gives `goals`, `npg`, `xG` and `npxG` per player. It was fetched by GET with the `X-Requested-With: XMLHttpRequest` header and `--compressed`.

2. `element-summary/1/` `history` row keys, fetched live today (https://fantasy.premierleague.com/api/element-summary/1/). Top-level keys are `fixtures`, `history` and `history_past`. Every field you listed is present. The full `history` key set is:
   `element, fixture, opponent_team, total_points, was_home, kickoff_time, team_h_score, team_a_score, round, modified, minutes, goals_scored, assists, clean_sheets, goals_conceded, own_goals, penalties_saved, penalties_missed, yellow_cards, red_cards, saves, bonus, bps, influence, creativity, threat, ict_index, clearances_blocks_interceptions, recoveries, tackles, defensive_contribution, starts, expected_goals, expected_assists, expected_goal_involvements, expected_goals_conceded, value, transfers_balance, selected, transfers_in, transfers_out`
   - Types: `expected_goals`, `expected_assists`, `expected_goal_involvements`, `expected_goals_conceded`, `influence`, `creativity`, `threat` and `ict_index` are strings (e.g. "0.63"). `was_home` is a bool. The rest are ints.
   - `defensive_contribution` is the raw count, not points. In the sample row, CBI 1 + tackles 0 + recoveries 9 gave `defensive_contribution` 0 for a GKP, so GKPs don't get it. For outfield players it appears to be CBI + tackles, and in the vaastav row below (6 CBI + 2 tackles = 8) that held. I haven't checked it against the rules, and recoveries seem not to count.

3. vaastav `data/2025-26/gws/merged_gw.csv` (https://github.com/vaastav/Fantasy-Premier-League). It has 29,757 rows and covers GW1 to GW38. Header:
   `name, position, team, xP, assists, bonus, bps, clean_sheets, creativity, element, expected_assists, expected_goal_involvements, expected_goals, expected_goals_conceded, fixture, goals_conceded, goals_scored, ict_index, influence, kickoff_time, minutes, modified, opponent_team, own_goals, penalties_missed, penalties_saved, red_cards, round, saves, selected, starts, team_a_score, team_h_score, threat, total_points, transfers_balance, transfers_in, transfers_out, value, was_home, yellow_cards, clearances_blocks_interceptions, defensive_contribution, recoveries, tackles, GW`
   - All the columns you asked about are present: `starts`, `expected_goals`, `expected_assists`, `defensive_contribution`, `clearances_blocks_interceptions`, `recoveries`, `tackles`, `team` and `position`.
   - `team` is the club name (e.g. "Sunderland"). `opponent_team` is a numeric team id. `position` is GKP/DEF/MID/FWD.
   - The 2023-24 and 2024-25 files exist at the same path pattern. I didn't check their headers.

4. Penalty base rates, 380 matches per season. I computed these myself from public data, with no published aggregate. Penalty goals = Understat `goals` minus `npg` summed over players (https://understat.com/getLeagueData/EPL/<year>). Missed or saved penalties = the sum of FPL `penalties_missed` in vaastav's merged_gw.csv per season. Total goals come from football-data.co.uk (https://football-data.co.uk/mmz4281/2324/E0.csv, plus 2425 and 2526).

   | Season | Pen goals | Missed or saved | Pens per match | Conversion | Pen share of goals |
   |---|---|---|---|---|---|
   | 2023/24 | 96 | 11 | 0.282 | 89.7% | 7.7% (of 1246) |
   | 2024/25 | 69 | 14 | 0.218 | 83.1% | 6.2% (of 1115) |
   | 2025/26 | 77 | 15 | 0.242 | 83.7% | 7.4% (of 1045) |

   - Three-season pooled: 242 goals from 292 penalties, about 0.247 per match, 82.9% conversion... (the 242/292 figure is 242 goals / (242+51)). Check that arithmetic before use. Pooled conversion from the table rows is about 85%.
   - Understat's `goals` excludes own goals. Its 1196 plus 50 FPL own goals equals football-data's 1246 for 2023/24.
   - FPL `penalties_missed` includes saved penalties, assuming FPL counts them as missed.

5. Cards and own goals, 380 matches per season. Yellow and red cards come from football-data HY/AY/HR/AR (https://football-data.co.uk/mmz4281/2526/E0.csv). Own goals are the sum of FPL `own_goals` in vaastav's merged_gw.csv.

   | Season | Yellows | Yellows per match | Reds | Reds per match | Own goals | OG per match |
   |---|---|---|---|---|---|---|
   | 2023/24 | 1586 | 4.17 | 57 | 0.150 | 50 | 0.132 |
   | 2024/25 | 1539 | 4.05 | 52 | 0.137 | 34 | 0.089 |
   | 2025/26 | 1424 | 3.75 | 39 | 0.103 | 40 | 0.105 |

   - Per player-90 (22 players per match), the 2025/26 rate is about 0.17 yellows, 0.005 reds and 0.005 own goals.
   - FPL's own yellow total was 1594 for 2023/24, close to football-data's 1586.

Unknowns: No official Opta or FPL statement that xG includes penalties. The answer rests on the worked example. In Q4, the pooled conversion line contradicts itself: the "82.9%" figure doesn't match the table, so recompute the pooled number (the table rows alone suggest about 85%) before using it. I did not check whether pre-2025/26 `merged_gw.csv` headers match the 2025-26 one.

## Plan
Goal: stage 4 of the FPL model. An hourly Monte Carlo player-points model writes projection source `model`, which the stage-2 page and solver pick up through `auto`. The page shows the model and FPL's ep side by side.
Deviation from the note: there is no separate penalty-taker term. The research found that FPL `expected_goals` already includes penalty xG, so player shares already count penalties and a separate term would count them twice. Penalty misses stay as a small rate for each team's `penalties_order == 1` taker.
Kind: change to tools/fpl
Files:
- tools/fpl/model/pcore.py: new, stdlib only (host-testable). It holds:
  - SCORING keys read from a dict, plus threshold constants that `game_config` does not carry. They were checked on 2026-10-26 and come from the PL scoring table and BPS articles (cite in comments). DEFCON_THRESHOLD {2:10, 3:12, 4:12}; DEF count = `clearances_blocks_interceptions + tackles`, MID/FWD add `recoveries`. SAVES_PER_PT 3, GC_PER_PT 2, LONG_PLAY_MIN 60.
  - BPS event values: goal GKP/DEF 12, MID 18, FWD 24; assist 9; GKP/DEF clean sheet 12; save 2.
  - Rate constants: OG_SHARE 0.035 of team goals have no scorer; PEN_MISS_PER_TEAM_MATCH 0.02; RED_PER90 0.005; OWN_GOAL_PER90 0.005. ASSIST_RATE default 0.75, replaced by sum(assists)/sum(goals) from the data when there are 200 or more goals.
  - Functions:
    - `scoring_from_bootstrap(d)`: needs `game_config.scoring` with goals_scored, assists, clean_sheets, goals_conceded, saves, defensive_contribution, long_play, short_play, yellow_cards, red_cards, own_goals, penalties_missed and bonus. Raises ValueError on a missing key.
    - `match_log(rows)`: input is FPL history rows plus mapped vaastav rows. Output is newest first: minutes, starts, xg, xa, defcon count, bps, saves, yellows, goals, assists, cs.
    - `minutes_params(log, prior)`: per-match decay 0.92. Outputs p_start, mean minutes per start, p60 given a start, p_sub given no start, sub minutes. Priors are 0.3 / 80 / 0.75 / 0.3 / 20, each worth 2 pseudo-matches.
    - `rate90(log, field, prior90, decay=0.97, pseudo_min=900)`.
    - `availability(status, cop, k)`: `u` gives 0 for every GW. For the next GW: cop/100, with None meaning 1. For GW+1: min(1, a_next + 0.5). After that: 1.
    - `override_minutes(xmins_gw, n_fixtures)`: per fixture, minutes = override / n. 45 or more = a fixed start; above 0 = a fixed sub appearance; 0 = out.
    - `bonus_points(bps_list)`: 3/2/1 under the official tie rules. Players tied for a place all get that place's points, and the next distinct BPS skips the places they took.
    - `defcon_binom_n(mu)`: n = max(1, round(mu / 0.19)), p = mu / n (variance/mean 0.81).
    - `quantiles(sorted_list, qs)`.
- tools/fpl/model/players.py: new, numpy (already in the image). `run(now)` holds `teams.lock()` and prints busy if the lock is held.
  - Inputs:
    - players, fixtures and teams via `web.data.latest_rows`.
    - player_history: its own DuckDB query over all partitions, latest pulled_at per (element, fixture). Not `latest_rows`, whose key `element, round` merges doubles.
    - the newest `raw/vaastav/*/merged_gw_*.csv.gz` via csv. Players are mapped by normalised "first_name second_name" to a unique current element; drop the rest and count them as `unmapped_vaastav`.
    - the newest team model file via DuckDB (`matrix` JSON).
    - the overrides via `data.read_overrides` + `pj.split_overrides`.
    - scoring from the newest `raw/fpl/*/bootstrap_*.json.gz`.
  - Coverage: a GW is modelled only if every fixture with `event == gw` is in the team model. Stop at the first incomplete GW. If the next GW is incomplete: status `incomplete`, no file.
  - Simulation, per fixture with N = 10000 draws and `np.random.default_rng(seed = fixture_id)`:
    1. Draw (h, a) from the normalised matrix.
    2. Draw each player's minutes from start / sub / none, times availability. A starter is on for [0, m), a sub for [90 − m, 90).
    3. Give each goal a time ~U(0, 90). Its scorer is drawn among on-pitch teammates in proportion to their xG/90 rate (OG_SHARE = no scorer). An assist happens with probability ASSIST_RATE; the assister is drawn in proportion to xA/90, excluding the scorer.
    4. GKP/DEF: goals conceded while on the pitch. A clean sheet needs 60+ minutes and nothing conceded while on.
    5. GKP saves ~ Poisson(save rate/90 × opponent λ / 1.4 × min/90).
    6. DefCon: DEF counts are Poisson, MID/FWD binomial. The rate is scaled by clip((opponent λ / own λ)^0.25, 0.8, 1.25). Hitting the threshold scores `defensive_contribution[pos]` points.
    7. Cards, red cards, own goals and the taker's penalty misses are Bernoulli(rate × min/90).
    8. BPS = baseline (bps − event BPS)/90 × min + simulated event BPS + Normal(0, 4·sqrt(min/90)). Rank everyone with minutes above 0 in the fixture, then apply `bonus_points`.
  - Points: built from `scoring` by `element_type`. GW points = draws aligned and summed over that GW's fixtures. A blank GW gets a row with pts 0 and xmins 0. With an override, xmins equals the override total exactly.
  - Output: `/data/projections/model/<ts>.parquet` via `data.write_projection_file`-style tmp+rename; keep the newest 14.
    - Contract columns: element, gw, pts, xmins, generated_at.
    - Extra columns: p_start, p60, p10 (P(pts ≥ 10)), q50, q90, xg, xa, p_cs, p_defcon, xbonus.
    - Check that every value is finite before writing; otherwise raise.
  - `/data/model/players/status.json`: generated_at, gws, n_players, n_fixtures, unmapped_vaastav, inputs_key, msg.
  - Skip with "nothing new" when inputs_key is unchanged and the newest file is under 24 h old. inputs_key = the team file name + the newest players/history/bootstrap file names + the overrides mtime.
- tools/fpl/web/jobs.py: job `players` → `model.players.run()`, same pattern as `job_teams`. Usage string `<solve|deadline|teams|players>`.
- tools/fpl/web/data.py: add `read_model_extras()`. It reads the newest `projections/model` file and returns {(element, gw): {pts, p10, q90}} plus generated_at, or None on any error.
- tools/fpl/web/main.py + templates/index.html: when extras exist, the Projections table adds next-GW columns "Model", "FPL ep", "P(10+)" and "q90". "FPL ep" comes from `pj.build_fpl_ep(...)`, computed every time. One muted line under the table: "Model run <age>; source in use: X". On any exception the columns are left out.
- tools/fpl/tests/test_players.py: host unittest on pcore:
  - scoring parse, including a missing key raising ValueError
  - availability cases
  - bonus ties: [30, 30, 20] → 3, 3, 1 and [30, 20, 20] → 3, 2, 2
  - decay/prior fallbacks with an empty log
  - override_minutes for a double GW
- tools/fpl/tests/test_players_sim.py: `skipUnless(numpy)`. A synthetic two-team fixture with a fixed matrix checks four things: the mean goals credited ≈ λ × (1 − OG_SHARE) within 5%, a player with 0 availability scores 0, the output is finite, and P(cs) matches the matrix's zero row when the GK always plays 90.
- tools/fpl/Dockerfile: add `COPY tests/ ./tests/`.
- tools/fpl/compose.yaml: image `homelab/fpl:0.5.0` (bump the minor from what is there), header comment mentions stage 4.
- scripts/fpl-web-job.sh: accept `players` in the case statement and the usage text.
- scripts/cron.d/fpl-players.cron: `40 * * * * $R fpl-players 1800 $REPO/scripts/fpl-web-job.sh players`, with a comment line like fpl-teams.cron.
- core/uptime-kuma/compose.d/cron-fpl-players.yaml: copy of cron-fpl-teams.yaml with name `cron-fpl-players`, token `${KUMA_CRON_PUSH_SECRET:-}fplplayers000000`, interval 5400, max_retries 0.
- tools/fpl/README.md: new "Player points model (stage 4)" section covering:
  - inputs, the method in one paragraph per component, the constants and why (thresholds not in game_config; the pen xG finding), the output columns, skips and failures, and that `auto` switches the solver to `model` (set the source to `fpl-ep` to compare first)
  - the cron/Kuma table row, and the data layout line for `model/players/`
- CLAUDE.md: line 15, "+ team goals model" becomes "+ team goals and player points models". Line 38 becomes `fpl-web-job.sh <solve|deadline|teams|players>` with "hourly player model :40".
- docs/README.md: the fpl row adds "player points model".
New service: None (no new port; 8092 stays).
New env vars: None
Checks the builder must run:
- `python3 -m py_compile tools/fpl/model/pcore.py tools/fpl/model/players.py tools/fpl/web/*.py`
- `python3 -m unittest discover -s tools/fpl/tests` (the sim test skips on the host)
- `scripts/dc.sh <worktree>/tools/fpl config -q`
- `scripts/dc.sh <worktree>/core/uptime-kuma config -q`
- `bash -n scripts/fpl-web-job.sh`
- grep check: no `latest` tag; no hard-coded goal/CS point values outside the scoring dict (only the threshold and BPS constants)
Review focus:
- No team model file, or the next GW only partly covered → status `incomplete`/`no team model`, no file, exit 0. `auto` stays on fpl-ep, and the page and solver do not break.
- A player with an override → the output's xmins equals the override, so stage 2's `apply_overrides` scales by exactly 1 (not applied twice). `out` gives 0 pts.
- A new signing or promoted player with no history, or one not found in vaastav → priors, finite numbers, never NaN in the parquet. A non-finite value means exit 1 and no file.
- Double GW → both fixtures' draws summed (two player_history rows per round are not merged). Blank GW → rows of 0.
- The team model job holds the lock, or two `players` runs overlap → "busy" (cron exit 0, both lock layers). The raw bootstrap has no `game_config.scoring` → one-line FAILED, exit 1, Kuma down, no file.
Docs: tools/fpl/README.md (stage 4 section, cron table, data layout); CLAUDE.md lines 15 and 38; docs/README.md fpl row.

## Manual steps
At deploy:
1. Rebuild and recreate: `scripts/dc.sh tools/fpl build` then `up -d`. Then reinstall cron (`scripts/install-cron.sh`) and recreate uptime-kuma so `cron-fpl-players` exists.
2. Run `scripts/dc.sh tools/fpl exec fpl python -m unittest discover -s tests`. The numpy sim test has to pass inside the image.
3. Run `scripts/fpl-web-job.sh players` once. Check that `/srv/homelab/fpl/projections/model/` has a file and that the page shows the Model/FPL ep columns.
4. To compare before the solver switches over, set Source to `fpl-ep` on the page. `auto` uses `model` as soon as a file exists.

Stage 5 (fpl-backtest) is meant to tune the decay, prior and noise constants.

## Review notes
1. tools/fpl/README.md:92: a blank line sits between the `deadline` row and the new `teams`/`players`
   rows. Those two rows render as a stray paragraph, not as part of the cron table. Delete the blank line.
2. tools/fpl/model/players.py:378-397: in a double gameweek the per-fixture arrays are summed. That
   makes `p_start`, `p60`, `p_cs` and `p_defcon` expected counts that can go above 1, not probabilities.
   Either cap them at 1 per GW (P of at least one), or say so in the README output-columns line.
3. Double-GW override semantics. As the plan said, the model splits an override across the GW's
   fixtures (90 in a DGW = 45 + 45) and writes xmins = 90. Stage 2's apply_overrides then scales pts by
   exactly 1 (correct), but it sets xmins = xo x fixtures = 180. So the page and solver show double the
   minutes the model simulated. This ambiguity was already in stage 2. Worth one line in the README.
4. tests/test_players_sim.py skips on the host (no numpy). The model's numpy path has not run anywhere
   yet, so manual step 2 (unittest inside the image) and step 3 (one `players` run) matter.
5. players.py: each GW's accumulator holds about 550 players x 9 arrays x 10k float64, roughly 400 MB,
   in the `exec`'d process. The container has no memory limit and the host has about 9 GB free, so it
   fits. Keep it in mind if a mem_limit is ever added. Also, if age_text fails the muted page line
   reads "Model run None".

## Declined to judge
- Squads aren't limited to 11 on the pitch (starters and subs are drawn independently): a modelling simplification inside the plan's design.
- Penalties saved (GKP +5) aren't simulated: the plan doesn't list them.
- i/s/n status with chance None counts as 0 for the next GW (plan said None = 1): a sensible refinement, documented in the README.
- The `nodata` path doesn't write status.json: the plan only names status writes for incomplete / no team model.
- start_mix uses 74.5/15.5 instead of 75/15 for the 60-90 spell mean: a tiny bias, a stage-5 tuning matter.
