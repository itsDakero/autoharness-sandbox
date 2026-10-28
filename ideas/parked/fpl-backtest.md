# FPL model, stage 5: walk-forward backtest and tuning

Depends on: fpl-player-model (tests it)
Value: 3   (tells Dan whether his model beats FPL's ep_next and an odds-only model, and tunes its weights)
Effort: 3  (replay past gameweeks with deadline-time data, metrics, a results page)
Risk: 1    (offline, read-only on the collected data)
Score: 9
Source: Dan 2026-10-25 (design in `reports/FPL points prediction model.md`, "Homelab build" section)

## Problem
Without a fair test there's no way to know whether the model is any good, or which weights to change.

## Proposal
- Walk forward by gameweek using only data known at each deadline (stage 1 snapshots; vaastav's dataset
  for older seasons, ignoring its leaky `xP` column).
- Metrics: RMSE/MAE by return bucket (0, 1-2, 3-4, 5+ points; FPL Review's zeros RMSE 0.689 in the
  OpenFPL paper is the number to beat), log-loss and calibration for 60+ minutes, goal, assist, clean
  sheet and DefCon, rank correlation within position, captain hit rate.
- Baselines: last-5 average, FPL's `ep_next`, odds-only model.
- Season replay through the solver with each model's projections (points scored by the chosen squads).
- A Backtest tab on the FPL page; a short Discord summary after each weekly re-run.

## Parked 2026-10-26

## Why parked
The note covers at least three separate projects, and the data it assumes isn't there yet. The collector and the stage-4 model were both deployed today (2026-10-26). `/srv/homelab/fpl/tables/` has only `events`, `players` and `teams`, each with one date. There's no `player_history`, `live`, vaastav, `model/history/` or projections yet. So:

- **No deadline-time snapshots exist for any past gameweek.** The first gameweek that can be tested fairly with the live pipeline is GW10 of 2026/27. FPL's `ep_next` as a baseline is only available from then on, because vaastav's `xP` leaks post-match data and is excluded.
- **Deadline-time projections get deleted today.** `model/players.py` and the `fpl-ep` source keep only the newest 14 files (`KEEP = 14`), and `players` runs hourly. A fair live test therefore needs a new "freeze at the deadline" step that copies each source's last pre-deadline file before pruning removes it.
- **Testing older seasons needs a different engine.** Replaying 2023-24 to 2025-26 needs vaastav `merged_gw` plus the football-data closing-odds history (`model history`, run by hand, not done yet). It also needs `players._run_locked` refactored into a function that works "as of" a given date. That function currently reads only the latest tables, and the model has no availability flags or `penalties_order` for past seasons.
- **Replaying a season through the solver is a project of its own.** The solver reads Dan's squad and free transfers from the FPL API, so a replay needs a simulated squad state. It also needs one solve per gameweek for each model: 38 x 4 x up to 300 s is hours of CPU.

Proposed split, each a note with `Depends on:` the previous one:
- **5a, fpl-backtest-live** (Effort 2):
  - a `deadline-freeze` job copies the newest `model` and `fpl-ep` files from before each deadline to `/data/backtest/frozen/<season>/gw<N>/`, along with that gameweek's `ep_next` and last-5 averages from the snapshots at or before the deadline;
  - once the gameweek is finished and checked, a `score` job computes RMSE/MAE by bucket (0, 1-2, 3-4, 5+), log-loss and calibration for 60+ minutes, clean sheet and DefCon, rank correlation within each position, and captain hit rate;
  - it adds a Backtest tab and one Discord line per gameweek.
  - Fair from GW10 onwards.
- **5b, fpl-backtest-history** (Effort 4): refactor the player model to run "as of" a date, replay vaastav 2023-24 to 2025-26 with closing-odds score matrices, add the odds-only baseline, and grid-tune the decays, priors and BPS noise (`params.json` for the player model).
- **5c, fpl-backtest-solver** (Effort 3): replay a season through the solver from a GW1 squad picked with £100m and one free transfer a week, and compare points scored under each model's projections.

## Questions
1. Split it into 5a/5b/5c as above and build 5a first? (yes / no, and if no, which part to build first)
2. What should the "odds-only" baseline be? My default: the stage-4 simulation on the same market score matrices with every player's xG, xA and DefCon rates set to his position prior, keeping the minutes model. This measures what player-level data adds on top of the odds.
3. In 5b, should tuning write parameters that the live player model picks up automatically, as the team model's `params.json` does? Or should it only report them for you to apply by hand?
4. Can the Discord line be one per finished gameweek, on the Monday after `data_checked`, with model vs `ep_next` vs last-5 RMSE and captain hits? Or do you want it only when the model loses to a baseline?
