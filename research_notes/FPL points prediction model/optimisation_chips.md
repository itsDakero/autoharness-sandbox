# FPL decision optimisation: transfers, chips, captaincy on top of an xP model (2026/27)

Research date: 2026-10-25 (mid 2026/27). Primary code source: the open-source solver formerly at
github.com/sertalpbilal/FPL-Optimization-Tools, which now points to solioanalytics/open-fpl-solver
(cloned shallow; last commit 15 Sep 2026). The formulation notes below are read directly from its `dev/solver.py`
and `data/comprehensive_settings.json`.

## 1. Current FPL rules relevant to strategy (2026/27)

### Takeaway
The 2026/27 rules match 2025/26 in every way that matters for optimisation: two sets of four chips (WC, FH, BB, TC), one set per half, used by the GW19 deadline with no carry-over; one chip per GW; up to 5 banked FTs. The real changes are no AFCON FT top-up, BPS tweaks, live ranks, later lockdown, and an official nightly price-change predictor. Assistant Manager has been gone since 2025/26.

### Cited Findings
- **Chips:** two sets, eight in total, each with one Wildcard, Free Hit, Triple Captain and Bench Boost. "The first set of chips must be played before the Gameweek 19 deadline passes at 13:30 GMT on Saturday 2 January." Chips "cannot be carried over into the second half of 2026/27." — [PL: All you need to know about changes for 2026/27](https://www.premierleague.com/en/news/4679873/all-you-need-to-know-about-changes-to-fpl-for-202627); [PL: What's happening with FPL chips in 2026/27](https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627)
  - Conflict: one third-party guide gives the GW19 deadline as 18:30 UTC on Fri 1 Jan 2027. The official PL date (Sat 2 Jan, 13:30) is the one to trust. — [fplpulse](https://www.fplpulse.com/blog/fpl-chips-explained)
- **Chip restrictions:** "Only one chip can be played in a single Gameweek." Free Hit cannot be played in GW1. If you use the first Free Hit in GW19 you can't play the second in GW20. A Wildcard makes all of that GW's transfers free, including ones already made. — [PL chips 2026/27](https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627)
- **Two chip sets started in 2025/26.** Assistant Manager was removed that season. The 2025/26 first-half deadline was GW19, 18:30 GMT, Tue 30 Dec. — [PL: changes for 2025/26](https://www.premierleague.com/en/news/4362211)
- **Assistant Manager history:** introduced for 2024/25 as a "mystery chip" revealed in Jan 2025, lasting 3 GWs; discontinued for 2025/26. All Out Attack was dropped in 2017. — [Wikipedia: Fantasy Premier League](https://en.wikipedia.org/wiki/Fantasy_Premier_League)
- **Free transfers:** "you can still roll up to five". — [PL 2026/27 changes](https://www.premierleague.com/en/news/4679873/all-you-need-to-know-about-changes-to-fpl-for-202627)
  - 1 FT per GW; the bank was expanded before 2024/25 so up to 4 can be carried (max 5 in a GW). Each extra transfer costs −4. — [Wikipedia](https://en.wikipedia.org/wiki/Fantasy_Premier_League)
- **AFCON top-up:** none in 2026/27. AFCON is in June/July 2027, so the December bonus FTs of past seasons don't apply. — [FFScout: 5 rule changes](https://www.fantasyfootballscout.co.uk/2026/07/20/fpl-2026-27-5-rule-changes-new-features-announced); [PL](https://www.premierleague.com/en/news/4679873/all-you-need-to-know-about-changes-to-fpl-for-202627)
- **Squad and budget:** 15 players, £100m, max 3 per club, XI needs 1 GK and at least 3 DEF. — [Wikipedia](https://en.wikipedia.org/wiki/Fantasy_Premier_League). The 2026/27 PL change article doesn't mention the budget, which implies it is unchanged. The solver hard-codes `SQUAD_SIZE = 15`, `LINEUP_SIZE = 11`, `MAX_PLAYERS_PER_TEAM = 3` and reads position counts and formation min/max from the FPL API `element_types`. — [open-fpl-solver solver.py](https://github.com/sertalpbilal/FPL-Optimization-Tools)
- **Other 2026/27 changes:**
  - Live ranks and live mini-leagues.
  - Projected bonus shown after 20 minutes.
  - Lockdown moved to 09:00 UK the day after a GW's last match (previously 1 h after the final whistle).
  - BPS: no BPS loss when tackled; CBI scores 1 BPS per 3 (was per 2); GK saves from outside the box no longer count, other saves score 2 BPS, and a "big chance" save scores +1.
  - DefCon points unchanged.
  - 11 players reclassified to new positions.
  - Percentage ranks added.
  — [FFScout](https://www.fantasyfootballscout.co.uk/2026/07/20/fpl-2026-27-5-rule-changes-new-features-announced); [PL](https://www.premierleague.com/en/news/4679873/all-you-need-to-know-about-changes-to-fpl-for-202627)
- **Price changes (2026/27):** an official Price Change Predictor flags likely risers and fallers each night. Changes apply at 00:00 UK time (previously ~01:30 GMT / 02:30 BST). — [PL](https://www.premierleague.com/en/news/4679873/all-you-need-to-know-about-changes-to-fpl-for-202627); [FFScout: how price changes work](https://www.fantasyfootballscout.co.uk/2026/07/20/how-do-fpl-price-changes-work)
- **Selling price:** you keep half of any rise, rounded down to £0.1m (bought £15.5m, now £15.9m, sells £15.7m), and take any fall in full. — [FFScout](https://www.fantasyfootballscout.co.uk/2026/07/20/how-do-fpl-price-changes-work)
  - One PL-hosted article wording says "rounded up", which conflicts. The solver's own code computes `selling_price = purchase_price + diff // 2` (floor) when the price has risen, and current price otherwise, which supports rounding down. — [PL price change article](https://www.premierleague.com/en/news/2858775); [solver.py](https://github.com/sertalpbilal/FPL-Optimization-Tools)

### Inferences
- For a model, the 2026/27 state is:
  - per-half chip budget {WC:1, FH:1, BB:1, TC:1}, with a hard boundary at the GW19 deadline (a chip-limit constraint per half)
  - at most one chip per GW
  - FT state in [1,5], +1 per GW
  - hit = −4
  - no December FT top-up this season
- The BPS changes slightly shift bonus expectation from CBI-heavy defenders towards GKs, FBs and attackers. That belongs in the xP model, not the optimiser.

### Gaps
- No official 2026/27 help page was fetched (the FPL site is JS-rendered). Budget, squad counts and the −4 hit come from Wikipedia plus "no change announced"; they were not directly confirmed for 2026/27.
- The exact rounding of selling price in the official rules: sources conflict, though code and FFScout say round down.
- Whether Free Hit transfers count towards price changes was not confirmed.

## 2. Mathematical optimisation (MILP) for squad and multi-GW transfers

### Takeaway
The de facto standard is a deterministic multi-period MILP. It uses binary squad, lineup, captain, vice-captain and bench-slot variables per player per GW, transfer flow constraints, an integer FT state in [1,5], and per-GW chip binaries. The objective sums decayed weekly xP minus hits, plus a value for banked FTs and money in the bank. It is solved with HiGHS (open source). FPL Review also offers a non-linear heuristic "Transfer Solver" alongside its HiGHS-based "Linear Optimiser".

### Cited Findings (formulation, read from open-fpl-solver `dev/solver.py`)
- **Tooling:** pandas for data and HiGHS via `highspy` for the solve. The default `"solver": "highs"`, `secs: 600`, `gap: 0`. There is a Colab/browser version. Projections come in as CSV (`solio.csv`, `review` for FPL Review, or `mixed` with `data_weights`). — [repo README](https://github.com/sertalpbilal/FPL-Optimization-Tools)
- **Sets:** players p, GWs w in the horizon (default `horizon: 8`), positions t, teams, bench order o ∈ {0 (sub GK), 1, 2, 3}.
- **Variables:**
  - binaries `squad[p,w]`, `squad_fh[p,w]`, `lineup[p,w]`, `captain[p,w]`, `vicecap[p,w]`, `bench[p,w,o]`, `transfer_in/out[p,w]`
  - `use_wc[w]`, `use_fh[w]`, `use_bb[w]`, `use_tc[p,w]`
  - continuous `in_the_bank[w] ≥ 0`
  - integer `ft[w] ∈ [0,5]` and `penalized_transfers[w] ≥ 0`
  - one-hot `fts_state[w,s]`, s ∈ {0..5}
- **Key constraints:**
  - Squad flow: `squad[p,w] = squad[p,w-1] + in[p,w] − out[p,w]`.
  - Budget: `itb[w] = itb[w-1] + sold[w] − bought[w]`, with sell prices for owned players.
  - Squad: 15 per GW, with position counts. Lineup = 11 + 4·use_bb[w]. Formation min/max per position, max relaxed by BB.
  - Squad selection: one sub GK and one player per outfield bench slot unless BB. Captain = 1, vice = 1, both in the lineup, and they must differ. At most 3 per club.
  - Free Hit: a separate 15-man `squad_fh` built against `sell value of squad[w-1] + itb`. The permanent squad gets no transfers in a FH week.
  - FT dynamics: `raw = ft[w] − transfers[w] + 1 − use_wc[w] − use_fh[w]`, then clamped to [1,5] with big-M indicator binaries. WC and FH keep the FT count unchanged (matching the current rule that FTs are preserved over WC/FH).
  - Hits: `penalized[w] ≥ transfers[w] − ft[w] − 15·use_wc[w]`.
  - Chips: `use_wc + use_fh + use_bb + use_tc_gw ≤ 1` per GW, with `chip_limits` per chip over the horizon. `use_tc[p,w] ≤ captain[p,w]`.
- **Objective** (decay form):
  - `max Σ_w decay_base^(w−next_gw) · [ Σ_p xP[p,w]·(lineup + captain + vcap_weight·vicecap + use_tc + Σ_o bench_weight[o]·bench[p,w,o]) − hit_cost·penalized[w] + ft_gain[w] − ft_use_penalty[w] + itb_value·itb[w] − opposing_penalty[w] ]`
  - `objective: "regular"` drops the decay.
- **Defaults** (`comprehensive_settings.json`):

  | Setting | Default |
  |---|---|
  | `horizon` | 8 |
  | `decay_base` | 0.9 (code fallback 0.84) |
  | `ft_value` | 1.5 |
  | `ft_value_list` | {"2": 2, "3": 1.6, "4": 1.3, "5": 1.1} |
  | `bench_weights` | {0 (GK): 0.03, 1: 0.21, 2: 0.06, 3: 0.002} |
  | `vcap_weight` | 0.1 |
  | `ft_use_penalty` | 0.2 |
  | `itb_value` | 0.08 per £1m |
  | `hit_cost` | 4 |
  | `weekly_hit_limit` | 0 |
  | `no_transfer_last_gws` | 2 |
  | `xmin_lb` | 300 expected minutes over the horizon |
  | `ev_per_price_cutoff` | 30th percentile, keeping the top 5% EV regardless |

  `ft_value_list` is the marginal value of rolling from n−1 to n FTs; the code builds cumulative state values from it. `no_transfer_last_gws: 2` stops end-of-horizon "free" moves that are never paid back. `report_decay_base: [0.85, 1.0, 1.017]` reports the plan under alternative decays. — [repo data/README.md + comprehensive_settings.json](https://github.com/sertalpbilal/FPL-Optimization-Tools)
- **Further options:**
  - `max_defenders_per_team` (3)
  - `double_defense_pick`
  - `no_opposing_play` (hard or penalty 0.5)
  - `price_changes` (simulate ±£0.1m)
  - `transfer_itb_buffer`
  - `booked_transfers`
  - `force_ft_state_lb/ub`
  - `no_gk_rotation_after`
  - `num_iterations` with `iteration_criteria` (`this_gw_transfer_in_out`, `chip_gws`, `this_gw_lineup`…), which yields k-best alternative plans by adding exclusion cuts
  — [data/README.md](https://github.com/sertalpbilal/FPL-Optimization-Tools)
- **FPL Review solvers:**
  - **Transfer Solver:** a "Chess engine-style" heuristic search with "full probability-based calculations recognising non-linear complexities". It models autosubs from xMins and availability probabilities and handles same-team GKs, but "cannot guarantee total mathematical optimality".
  - **Linear Optimiser:** MILP on HiGHS, "linearised with fixed sub & vice-captain contributions", "guarantees optimal solution within the linear framework".
  - FPL Review recommends running both as cross-checks. — [FPL Review docs: solver comparison](https://docs.fplreview.com/the-model/solvers/solver-comparison/)
- **FPL Review FT value:** ~1.5 is "generally recommended for more coherent planning". 0.0 reproduces the old Transfer Suggestor. An FT value > 0 makes the solver flag only key moves. Projections update hourly. — [FPL Review FAQ](https://docs.fplreview.com/getting-started/faq/)
- **Academic:**
  - Matthews, Ramchurn & Chalkiadakis (AAAI 2012) model FPL as a belief-state MDP with Bayesian Q-learning. Team selection is a multi-dimensional knapsack solved by IP. The agent reached roughly the top percentile of ~2.5M human players. — [AAAI](https://ojs.aaai.org/index.php/AAAI/article/view/8259/8118); [Southampton eprints](https://eprints.soton.ac.uk/340382)
  - Ramezani & Dinh (arXiv 2505.02170, 2025) give deterministic and robust MILPs for XI, bench and captain with budget, formation and club limits, tested on 2023/24. It focuses on lineup selection, with multi-week transfers as future work. — [arXiv 2505.02170](https://arxiv.org/html/2505.02170v3)
  - Santoro (Bologna MSc, 2025) combines ML forecasts with MIP selection and weekly transfers, and beats greedy and heuristic baselines. — [thesis PDF](https://amslaurea.unibo.it/35674/1/Tesi_Lorenzo_Santoro.pdf)

### Inferences
- **Horizon and decay:**
  - Horizon and decay trade off: decay 0.9 over 8 GWs makes GW8 worth ~0.48 of GW1. This reflects growing uncertainty in projections and the option value of reacting to news.
  - Typical practice is 4–8 GWs (Elite XI "at least 4 weeks out", see §6).
  - A decay > 1 (1.017, reported) is used as a sanity check that the plan isn't purely short-termist.
- **FT values:** the value of a banked FT (~1.5–2 pts for 1→2, falling to ~1.1 for 4→5) is a heuristic stand-in for post-horizon option value. Since 2024/25 banking to 5 makes this state variable matter more. These defaults are tuning choices, not derived values.
- **Bench weights:** these should ideally come from the xP model's minutes distribution (P(starter misses) × P(sub plays)). A fixed weight is the main linearisation error, and FPL Review's non-linear solver exists to address it.
- **Solver choice:** HiGHS is the open default and fast enough (seconds to minutes for an 8-GW horizon after pruning). CBC is older and slower. Gurobi is faster on large chip-enumeration runs but commercial. I found no FPL-specific benchmark.

### Gaps
- Solio Analytics' and FPL Review's proprietary internals (exact decay defaults, how bench and vice weights are derived) are not public beyond the docs above.
- Bonomo et al. FPL paper: not located in this pass (not verified).
- No published head-to-head HiGHS/CBC/Gurobi timing on FPL instances.

## 3. Chip timing (WC, FH, BB, TC) and BGW/DGW

### Takeaway
Solvers treat chips as per-GW binaries with a count limit. In practice users either fix chip weeks (`use_wc: [15]`) or allow a set (`allowed_chip_gws`) and let the MILP choose, then compare objective values across chip-week combinations (`iteration_criteria: "chip_gws"`). With two chip sets and a hard GW19 cut-off, first-half chips can't be saved for the classic spring BGW/DGW, and the 2026/27 first half is expected to have no blanks or doubles.

### Cited Findings
- Solver chip controls:
  - `use_wc/use_fh/use_bb/use_tc` (fixed weeks)
  - `chip_limits` (max counts)
  - `allowed_chip_gws`, `forced_chip_gws`, `no_chip_gws`
  - `iteration_criteria: "chip_gws"`, which generates alternative chip-week plans
  — [open-fpl-solver data/README.md](https://github.com/sertalpbilal/FPL-Optimization-Tools)
- Chip value inside the objective:
  - BB adds 4 bench players to the lineup sum (lineup = 15).
  - TC adds one more xP of the captain (`use_tc[p,w] ≤ captain`).
  - FH builds a one-week `squad_fh` that is optimal for that GW, constrained by current squad value + ITB.
  - WC makes transfers free for that GW: the hit constraint is relaxed by 15·use_wc, and FTs are kept.
  — [solver.py](https://github.com/sertalpbilal/FPL-Optimization-Tools)
- Fixture uncertainty for BGW/DGW: `simulations.py` with "binary files" moves xP from an original GW into a possible rescheduled GW per team with probabilities (e.g. 60/30/10% scenarios). The solver then runs over sampled scenarios. — [binary_fixtures.md](https://github.com/sertalpbilal/FPL-Optimization-Tools)
- First-half 2026/27 calendar: "no blanks or doubles expected by the Gameweek 19 deadline". A surprise winter double is the reason to hold FH. — [FF Hub chip guide 2026/27](https://www.fantasyfootballhub.co.uk/articles/fpl-chip-strategy-guide)
- 2026/27 first-half suggestions from the FF Hub guide (opinion, Aug 2026):
  - WC in GW6 or GW7 (after the international break), or hold to GW17.
  - TC on Haaland GW7 v Ipswich (H) or GW16 v Hull (H), Bruno Fernandes GW14 v Coventry (H), or Saka GW10 v Hull (H) or GW19 v Ipswich (H).
  - FH in GW12, 14 or 16 when your squad lacks the top projected scorers.
  - BB soon after the WC, while the 15 are fit.
  — [FF Hub](https://www.fantasyfootballhub.co.uk/articles/fpl-chip-strategy-guide)
- Other views:
  - WC around GW5–6 for a fixture swing. — [AllAboutFPL](https://allaboutfpl.com/2026/08/2026-27-fpl-chip-strategy-guide-first-half-of-the-season/)
  - BB only when all 15 have strong fixtures. — [Ingenuity Fantasy](https://ingenuityfantasy.com/?p=10792)
  - BB in GW2 rather than GW1, to react to news. — [footballdream](https://www.footballdream.in/blog/fpl-gameweek-1-bench-boost-chip-strategy-2026-27)
  - Elite XI managers advise saving chips for late-season DGWs rather than single GWs. — [FF Fix: 5 tips](https://fantasyfootballfix.com/blog-index/fpl-5-tips-to-get-best-finish)

### Inferences
- **Valuing a chip:** compare the objective with the chip fixed in week w against the objective with no chip. This gives an opportunity cost per week. With one per half, the chip's value = max over eligible weeks of the marginal gain − the option value of holding (which collapses towards GW19 for set 1).
- **Typical marginal gains:**
  - TC ≈ captain xP, highest in a DGW for a premium.
  - BB ≈ Σ bench xP, highest in a DGW or right after a WC.
  - FH ≈ xP(best one-week XI) − xP(current XI), highest in BGWs or chaotic weeks.
  - WC ≈ multi-GW gain from a free rebuild, highest before fixture swings or when the squad needs many transfers.
- **First half 2026/27** (no BGW/DGW): chip value comes from fixture swings and single-GW mismatches, so solver enumeration over GW ranges is more useful than DGW heuristics. Pairing WC→BB, plus FH for weeks your squad is weakest, is the standard pattern.
- **"Use it or lose it":** this matters for set 1, so the solver should force all four chips in the remaining GWs before GW19 (`forced_chip_gws` / chip limits with an end-of-half horizon).

### Gaps
- No quantitative study found of average chip returns (points) by timing for 2025/26 (the first two-set season).
- The second-half 2026/27 BGW/DGW calendar (FA Cup and European rescheduling) is unknown as of Oct 2026.

## 4. Captaincy: EV vs distribution, EO, rank strategy

### Takeaway
A solver picks the captain by max xP (plus a small vice weight). Rank-aware play adds effective ownership: points relative to the field are (1·[owned/captained multiplier] − EO) × points. So a high-EO captain is the "shield" pick, and differentials pay off only when chasing.

### Cited Findings
- **EO definition:** EO = % starting + % captaining (+ triple-captaining). With EO < 100% a player's points help your rank if you own them. With EO > 100%, their points can hurt you unless you captain them. EO is zero-sum, so a high-EO captain soaks up EO elsewhere. Low-EO non-captained players are "lower-risk differentials". — [FFScout: what is EO](https://www.fantasyfootballscout.co.uk/2021/03/24/what-is-effective-ownership-and-why-is-it-so-widely-talked-about-in-fpl/); [FFScout: high EO](https://www.fantasyfootballscout.co.uk/2021/11/24/should-we-be-concerned-about-high-effective-ownership-in-fpl/)
- **Top-10k concentration:** in one GW report Haaland's captaincy share was 78% in the top 10k versus 58.4% overall. Not captaining him "could be a significant risk". Top managers "remain overwhelmingly risk-averse". (Season not clear: treat as older-season example.) — [FF Fix GW24 report](https://www.fantasyfootballfix.com/blog-index/gameweek-24-deadline-report-haaland-leads/); [FF Fix GW26](https://www.fantasyfootballfix.com/blog-index/gameweek-26-deadline-report-haaland-dominates/)
- **What separates finishes:** the difference between a top 10k and a top 50k finish "is often a couple of big captaincy calls going your way". — [FFScout masterclass 2021](https://www.fantasyfootballscout.co.uk/2021/08/01/tips-on-how-to-target-a-top-10k-fpl-overall-rank?hc_page=7)
- **Solver captain term:** `captain + vcap_weight(0.1)·vicecap`, purely EV-based. — [solver.py](https://github.com/sertalpbilal/FPL-Optimization-Tools)

### Inferences
- **Rank-aware objective:** maximise E[your pts − Σ_p EO_p·pts_p] when protecting rank, or P(beat target) when chasing. With the same means, a chaser should prefer a higher-variance, low-EO captain, and a leader should match the template. A Monte Carlo over player point distributions (from the xP model) can estimate P(rank gain) per captain option.
- Captain EV for a DGW player roughly doubles, which is why TC goes in DGWs. Variance also rises, which favours a chaser.

### Gaps
- I found no rigorous public study quantifying the rank value of template vs differential captaincy.

## 5. Price changes and team value

### Takeaway
Prices move £0.1m at a time, at most once a day, capped at ±£0.3m per GW, driven by net transfers. You keep only half of any rise (rounded down), so team value is worth less than its headline number. 2026/27 adds an official nightly predictor, which shrinks the edge from "beating" rises.

### Cited Findings
- **Mechanics:**
  - Changes of £0.1m, at most once a day, at most £0.3m in a GW.
  - Prices fixed until GW1 kickoff.
  - Driven by mass buying and selling.
  - Wildcard transfers don't count towards price movement. So buy likely risers on a WC before the deadline.
  — [FFScout 2026/27](https://www.fantasyfootballscout.co.uk/2026/07/20/how-do-fpl-price-changes-work); [PL](https://www.premierleague.com/en/news/2858775)
- **Official predictor:** the 2026/27 predictor flags players "likely" or "very likely" to change each night. Changes happen at 00:00 UK. — [PL 2026/27](https://www.premierleague.com/en/news/4679873/all-you-need-to-know-about-changes-to-fpl-for-202627)
- **Solver handling:**
  - Sell price = purchase + floor(gain/2).
  - `price_changes` simulates rises and falls.
  - `itb_value` 0.08 pts per £1m.
  - `itb_loss_per_transfer` and `transfer_itb_buffer` add budget robustness.
  — [solver.py, settings](https://github.com/sertalpbilal/FPL-Optimization-Tools)

### Inferences
- **Value of TV:** small. +£0.1m sell value is worth roughly `itb_value` (0.08 pts per £1m, so ~0.008 pts per £0.1m) in the default objective. Its real value is enabling a specific later upgrade, which the multi-period model already captures by planning that upgrade inside the horizon.
- **Moves made for price:** making a planned transfer early to beat a rise is worth it only if the plan is robust to the next news cycle. Moving early loses information, such as injury news.

### Gaps
- The exact algorithm (net-transfer thresholds relative to ownership, flags, and whether Free Hit transfers count) is not public. Third-party predictors reverse-engineer it.

## 6. Risk/uncertainty, and what elite managers do

### Takeaway
Solvers are deterministic on mean xP. Robustness comes from noise-perturbed re-solves (sensitivity analysis), scenario files for fixture uncertainty, k-best alternatives, and minutes filters. FPL Review's non-linear solver models autosubs probabilistically. Evidence on elite managers shows top-10k finishes are largely luck (~6.5% repeat rate), so process quality must be judged on EV, not rank.

### Cited Findings
- **Randomisation:** `randomized: true` adds noise `xP·(92 − xMins)/134·N(0,1)·strength` per player-GW. So low-minutes players get more noise, and the noise scales with their xP.
  - `run/sensitivity.py` aggregates many randomised solves into buy/sell frequencies, scoring iteration ranks 10/9/8.
  - `run/simulations.py` handles fixture-scenario binaries.
  - `run_parallel.py` runs solves in parallel.
  — [repo run/ + solver.py](https://github.com/sertalpbilal/FPL-Optimization-Tools)
- **Pool filtering:** `xmin_lb: 300` drops players under 300 expected minutes over the horizon. `no_gk_rotation_after` / `max_defenders_per_team` handle structure. — [settings](https://github.com/sertalpbilal/FPL-Optimization-Tools)
- **Autosubs:** the MILP uses fixed bench weights for autosubs. FPL Review's Transfer Solver uses full probabilities, which "matters most when rotation risk is significant". — [FPL Review](https://docs.fplreview.com/the-model/solvers/solver-comparison/)
- **Robust MILP:** robust formulations for XI selection under projection uncertainty. — [Ramezani & Dinh, arXiv 2505.02170](https://arxiv.org/html/2505.02170v3)
- **Top-10k repeat rate:** of 9,123 2019/20 top-10k managers who also played 2018/19, 594 (~6.5%) were also top 10k in 2018/19, and 63 of those were also top 10k in 2017/18. Managers with 4+ consecutive top-10k finishes repeat ~30% of the time.
  - Simulated tiers give a P(top 10k) of ~55% for the top 100 managers, ~35% for the next 1k, and ~17.5% for the next 10k.
  - The article concludes FPL is "largely chance-based". Dated 3 Feb 2021 (older seasons).
  — [FPL Review: Top 10k](https://docs.fplreview.com/articles/top-10k/)
- **Elite XI:** a group with 80 top-10k finishes between them say:
  - plan at least 4 GWs ahead but stay flexible to injuries, trends and fixture swings
  - save chips for late DGWs
  — [FF Fix 5 tips](https://fantasyfootballfix.com/blog-index/fpl-5-tips-to-get-best-finish)
- **Repeat top-10k managers' early GWs:** FourFourTwo studied ~500 such managers' first two GWs. Detail not retrieved. — [FourFourTwo](https://www.fourfourtwo.com/us/news/fpl-tips-what-you-can-learn-about-captains-and-transfers-from-elite-fpl-bosses-1600882745000)
- **Bots vs humans:** the AAAI 2012 bot reached roughly the top percentile against ~2.5M humans. — [Southampton eprints](https://eprints.soton.ac.uk/340382)

### Inferences
- **Recommended pipeline for a homelab model:**
  1. xP and xMins per player-GW, with a distribution.
  2. Prune the pool.
  3. Run the MILP (HiGHS) over 6–8 GWs, decay ~0.85–0.9, FT values as above, bench weights derived from xMins.
  4. Make 50–200 randomised re-solves and pick the moves that appear most often (sensitivity).
  5. Enumerate chip weeks within each half, with the set-1 chips forced before GW19.
  6. Make the captain choice by EV, with an optional EO and variance adjustment based on rank goals.
- **Minutes uncertainty** is the dominant noise. Weighting noise by (92 − xMins), as the repo does, is a cheap proxy for it.

### Gaps
- No rigorous public study of solver-driven vs human managers in recent seasons. Community anecdotes suggest solver users dominate the top ranks, but I found nothing citable.
- No elite-manager data on hit frequency or chip timing for 2025/26.
