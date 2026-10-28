# Existing FPL expected-points prediction models (survey, as of Oct 2026)

## How does FPL Review's Massive Data model produce its projections?

### Takeaway
FPL Review is a one-person operation. It started on de-margined bookmaker odds plus editable expected minutes (xMins), then moved to the proprietary "Massive Data" ML model, which mixes performance data (xG-type), market odds and tactical context. The model outputs per-event-weighted EV up to 14 GWs ahead. The public sources describe the method only qualitatively. The one independent benchmark (OpenFPL, 2025) puts it at or near the top, and it is strongest at predicting low or zero returns, which is plausibly down to its minutes modelling.

### Cited Findings
- FPL Review launched in 2018/19 as a personal project, and one person has developed and run it since. The original site used bookmaker-odds projections with editable xMins. The Massive Data Model came in 2020 and has been iterated every year since. The solver went single-period (2019/20), then multi-period (2022/23), then sensitivity analysis and chip timing (2023/24), then linear optimisation (2024/25). The page makes no quantitative accuracy claims. — [About FPL Review](https://docs.fplreview.com/getting-started/about-fplreview/)
- Massive Data "combines traditional statistical methods and machine learning with feature-rich datasets". Inputs are historical performance, market odds and tactical analysis. Context covered: team strength and style, player roles, tactical changes, temporary factors (penalty duty, rotation) and data recency. Output is EV: the expected points from goals, assists, CS, cards, bonus etc., each weighted by its probability, up to 14 GWs ahead. Market data, news, xMins and simulations refresh hourly. Performance data is processed overnight. Press-conference news is validated before each deadline. The model is re-evaluated every year. — [Massive Data Model docs](https://docs.fplreview.com/the-model/projections/massive-data-model/)
- Versions: the "Massive Data v2" launch was announced in April 2021 — [FPL Review on X](https://x.com/fplreview/status/1380475978175111169). A search summary says the 25/26 planner was upgraded to Massive Data v4 and that the docs call it live for 26/27. I could not verify this on a primary page — [docs.fplreview.com](https://docs.fplreview.com/). The free model is separate and simpler. It has a shorter horizon (5 GWs pre-GW1, then 4) and lower xMins resolution — [FPL Review on X, Aug 2025](https://x.com/fplreview/status/1952735100887601457); [Free Model docs](https://docs.fplreview.com/the-model/projections/free-model/)
- The 2020 article "Massive Data: A goalscoring model more predictive than bookmakers' odds" uses an ML model fed performance data over several time frames, and it also predicts FPL assists. It falls back to spread-market odds when a player has fewer than 5 full matches. It can see further ahead than odds, which only cover one GW. Test set: 2,021 player-matches from 2019/20 GW9–26 (outfield, 90-minute players only). R² against actual goals: Massive Data 0.129, Spread markets 0.114, Bookmakers 0.112, xG over the last 5 matches 0.098, a basic position+fixture model 0.096, goals over the last 5 matches −0.010. Against xG: 0.353 / 0.331 / 0.321 / 0.288 / 0.283 / 0.081. Recent goals over 450 minutes predicted worse than the basic model. Recent xG becomes useful only after about 20+ games. Goalscorer markets carry about a 45% margin. These are the author's own results, not independently verified. — [FPL Review article, 2020-02-27](https://docs.fplreview.com/articles/massive-data/)
- xMins is the average minutes over 1,000 simulations. It accounts for rotation, injury risk, tactics and news. Users can edit it, and by default it decays over future GWs. Projections are re-run at the deadline "to discourage over-fitting for the Season Review ranks". EV is not proportional to xMins. This comes from a kinsta mirror of the docs. — [xMins (mirror)](https://fplr-docs-6ktts.kinsta.page/the-model/projections/xmins/)

### Inferences
- The architecture appears to be per-event: event probabilities, xMins and a simulation layer, then EV through the scoring rules. It does not look like a direct points regression. The docs list per-event weighting and "background simulations". **Speculation**: the exact learners and features are not published.
- The 2020 R² figures show the realistic ceiling for single-match goal prediction: about 0.13 R² against actual goals, even for the best model.

### Gaps
- I found no podcast transcripts or X threads detailing features, learners or how promoted teams and new signings are handled.
- I could not confirm the v3/v4 changelog on a primary source.

## How do other commercial tools work (FFH, FF Scout, Solio, LiveFPL, FPLForm, Opta, etc.)?

### Takeaway
Fantasy Football Hub (FFH) uses an Opta-fed longitudinal multilevel regression of component outcomes. Solio (Sertalp Cay's company) is explicitly market-based, using sharp odds, with editable G/90, A/90 and minutes. Most other tools publish no methodology. One small-sample GW1 comparison exists, plus self-graded accuracy pages from newer entrants.

### Cited Findings
- **FFH (Fantasy Football Hub)**: founder Will Thomas built a "longitudinal multilevel regression model" on Opta data. It predicts goals, assists, clean sheets and minutes, and combines them into points. About 40k paying subscribers, about 200k registered users, ARR above £2.5m (as of Sept 2024). The article gives no accuracy numbers. — [The Next Web, Sept 2024](https://thenextweb.com/news/ai-is-killing-fantasy-football-fpl)
- **Fantasy Football Fix**: its "ChatFPL" is an LLM wrapper (Claude 3.5 Sonnet for Pro, GPT-4o-mini for Lite) over live data APIs, not a projection model in itself. — [The Next Web](https://thenextweb.com/news/ai-is-killing-fantasy-football-fpl)
- **Solio Analytics**: launched 5 Aug 2025. Sertalp Cay is co-founder. "RobT" has been the Lead Projections Analyst since Oct 2024. It has a multi-year Stats Perform/Opta data deal for 2026/27. Its projections are a "market-based projection model". — [Solio newsletter](https://solioanalytics.beehiiv.com/p/robt-moose-and-a-complete-beta-test-almost); [Jake Thom review](https://jakethom95.substack.com/p/exploring-solio-analytics-fpls-newest)
- Solio "taps into 'sharp' market odds" for expected goals and CS probability. It also factors in the probability of reaching the DEFCON (defensive contribution) threshold. G/90 and A/90 can be edited as a 12-GW average or per fixture. Minutes are an input. It outputs a range per player (e.g. Salah 3–16 for GW1) and has an EO-based "Relative" mode. — [Jake Thom review](https://jakethom95.substack.com/p/exploring-solio-analytics-fpls-newest)
- **Generic odds-to-points method** (older community articles): use 1/2/3-goal scorer odds plus appearance points and assumed bonus, add team CS odds, and strip the overround. Anytime-scorer odds assume a start, so uncertain starters must be discounted. — [FF Scout 2018](https://www.fantasyfootballscout.co.uk/2018/11/09/shouting-the-odds-who-the-bookies-back-in-gameweek-12/); [AllAboutFPL GW21 2023](https://allaboutfpl.com/2023/01/fpl-gw21-odds-preview-goals-clean-sheets-predicted-points/)
- **Opta/Stats Perform** sells fantasy projections that combine "historical data, live stats and AI models" (vendor description, no detail). — [Stats Perform fantasy FAQ](https://www.statsperform.com/faqs/stats-perform-faqs-fantasy/)
- **Onside** (a new tool, 2026/27) publishes graded, timestamped predictions. It claims an MAE of 1.57 pts/player/GW against 1.86 for FPL's own `ep_next` on the same players. Baselines: last-4 form 2.32, season mean 2.24. The page has internal inconsistencies: per-GW averages of about 2.5 against the 1.57 headline, conflicting win counts, and a legacy v1 MAE of 1.208 that beats the current model. The gameweek log scores only 60+ minute players. Treat it as marketing. — [Onside accuracy](https://onsidearena.com/accuracy)
- FPLXI's comparison page claims that FFH publishes no per-GW accuracy record (a rival's claim). — [FPLXI vs FFH](https://fplxi.com/vs/fantasy-football-hub)

### Inferences
- The market approach (Solio, early FPL Review) and the stats/ML approach (FFH, Massive Data) are the two main families. The best-regarded models blend both.

### Gaps
- I found no public methodology for FF Scout's members' projections, LiveFPL, FPLForm, FPL Data/fploptimized, or the "Kiwi"/Mathematical FPL models.

## Open-source projects (AIrsenal, OpenFPL, Sertalp Cay, vaastav, others)

### Takeaway
AIrsenal is the most complete open per-component probabilistic model: xG team ratings with Conway-Maxwell-Poisson, a Dirichlet split of team goals to players, a minutes model, and shrunk averages for bonus, saves and DEFCON. OpenFPL is the strongest benchmarked open model: per-position XGBoost+RF ensembles regressing points directly. vaastav's dataset is the standard historical source, but weekly updates have stopped.

### Cited Findings
- **AIrsenal** (Alan Turing Institute): v2 was released on 25 Sept 2026, a refactor with a new CLI; v1 databases must be rebuilt. It has a team-level scoreline model, a player-level goal-involvement model, and heuristics. Optimisation covers multi-GW transfers and all chips. — [AIrsenal GitHub](https://github.com/alan-turing-institute/AIrsenal)
- AIrsenal internals:
  - Team model: the default `xg` team model rates attack and defence from past xG and converts the ratings to goal-count probabilities with a Conway-Maxwell-Poisson distribution. The alternatives are Dixon-Coles models (`extended`, `neutral`) from the `bpl` package, fitted to actual goals. The xG models need data from 2022/23 onwards.
  - Player model: it splits team goals among players by fitting a Dirichlet distribution to xG/xA shares (`conjugate` fits actual goals and assists instead). It enumerates every split of team goals into goals, assists and non-involvement, and weights each by its probability.
  - Minutes: an empirical distribution of recent minutes. Players with P(play) ≤50% are given 0.
  - Clean sheets: CS points need ≥60 expected minutes, using P(concede 0).
  - Other components: bonus, cards, saves and defensive contributions use past averages shrunk towards the position mean.
  
  — [AIrsenal how-it-works.md](https://raw.githubusercontent.com/alan-turing-institute/AIrsenal/main/docs/how-it-works.md)
- **OpenFPL** (Daniel Groos, arXiv 2508.09992, Jul/Aug 2025):
  - Data: FPL API + Understat only, training seasons 2020-21 to 2023-24. Code at github.com/daniegr/OpenFPL.
  - Model: one ensemble per position (GK, DEF, MID, FWD, and AM for the assistant-manager chip), each of XGBoost + Random Forest, 50 models, taking the median.
  - Features: 122–206 per position, built from player, team and opponent rolling averages over 1/3/5/10/38 matches plus FPL availability %. The target is normalised next-match points, with entropy-based sample weights.
  - Evaluation: prospective, on 2024-25 GW32–38.
  
  — [OpenFPL arXiv](https://arxiv.org/html/2508.09992v1)
- OpenFPL results at 1 GW ahead, RMSE (MAE), with the FPL Review Massive Data model as the commercial benchmark:

  | Return category | Last-5 baseline | FPL Review | OpenFPL |
  |---|---|---|---|
  | Zeros | 0.791 (0.270) | 0.689 (0.237) | 0.818 (0.427) |
  | Blanks ≤2 | 1.400 | 1.189 | 1.291 |
  | Tickers 3–4 | 2.136 | 1.594 | 1.517 |
  | Haulers ≥5 | 5.613 (4.709) | 5.172 (4.381) | 5.142 (4.317) |

  The same pattern holds at 2 and 3 GWs ahead. Both models cut RMSE by about 5–34% against the baseline. The authors attribute FPL Review's edge on zeros to its expected-minutes projections. The paper cites Valouxis (2023) for FPL Review's earlier superiority over other services. — [OpenFPL arXiv](https://arxiv.org/html/2508.09992v1)
- **vaastav/Fantasy-Premier-League**:
  - Contents: per-GW CSVs (`gws/`, `merged_gws.csv`) and per-player histories from 2016-17 onwards. An `understat.py` script is included.
  - Leakage warning: the `xP` column (`ep_this`) may be post-match, so use shift(1).
  - Updates: weekly updates stopped after 2024-25. It now updates only three times a season.
  
  — [vaastav repo](https://github.com/vaastav/Fantasy-Premier-League)
- **Sertalp Cay**: the open optimisation repo is cited as "FPL-Optimization-Tools". He co-hosts the FPL Optimized podcast with Bas Belfi. — [search results; OpenFPL refs](https://arxiv.org/pdf/2508.09992); [FPL Optimized](https://fpl-optimized.beehiiv.com/p/welcome)
- **Lionel** (PyPI) has a Bayesian hierarchical points model (HierarchicalPointsModel) plus a squad optimiser. — [lionel on PyPI](https://pypi.org/project/lionel/)
- **fpl-xi**: a scikit-learn HistGradientBoosting points regressor plus a Poisson goals model plus an integer program. — [BruceOnyango/fpl-xi](https://github.com/BruceOnyango/fpl-xi)
- **Another repo** reports Spearman correlations of about 0.27 for both gradient boosting and ridge. They are effectively tied. — [teemukolu predictor](https://github.com/teemukolu/Fantasy-Premier-League-Points-Predictor)

### Inferences
- In the OpenFPL comparison, a direct-points ML regression on public data matched a commercial model on returns but lost on zeros. A per-component model with an explicit minutes model, like AIrsenal's, is the natural way to fix that weakness.

### Gaps
- I did not verify the contents of the FPL-Optimization-Tools repo or whether Cay has published open projections (as of 2026).
- I found no AIrsenal accuracy or rank figures.

## Academic literature

### Takeaway
Few papers benchmark against strong baselines. The notable ones are Matthews et al. 2012 (Bayesian RL, top ~1% of about 2.5M managers), OpenFPL 2025, and assorted deep-learning papers that report only MSE, with no comparison against commercial tools.

### Cited Findings
- **Matthews, Ramchurn & Chalkiadakis (AAAI 2012)** frame team formation as Bayesian reinforcement learning with beliefs over player characteristics. Their agent reached about the top percentile among roughly 2.5M human players. — [Southampton eprints](https://eprints.soton.ac.uk/340382); [AAAI](https://ojs.aaai.org/index.php/AAAI/article/view/8259/8118)
- **CNN/LSTM paper (IJCSS vol. 24(1), 2025)**: a CNN's MSE fell from 6.27 to 5.63 after adding news-sentiment features. — [IJCSS 2025](https://reference-global.com/download/article/10.2478/ijcss-2025-0008.pdf); [ResearchGate](https://www.researchgate.net/publication/391850138_PREDICTING_FANTASY_PREMIER_LEAGUE_POINTS_USING_CONVOLUTIONAL_NEURAL_NETWORK_AND_LONG_SHORT_TERM_MEMORY)
- **"2PM-Transformer" (SciTePress 2026)**: MSE 9.31 against 9.89 for a vanilla Transformer and 9.80 for an LSTM, on 2021/22 and 2023/24 data. — [SciTePress](https://www.scitepress.org/Papers/2026/143580/143580.pdf)
- **Ramezani & Dinh (arXiv 2505.02170, v3 Jan 2026)** use MILP team selection with average, EWMA, ARIMA and Monte Carlo estimators. ARIMA with a rolling window was the most consistent out of sample in 2023/24. — [arXiv](https://arxiv.org/abs/2505.02170)
- **Older work**: an ARIMA/RNN hybrid plus LP (arXiv 1909.12938) — [arXiv](https://arxiv.org/pdf/1909.12938); multi-stream data analytics including news (arXiv 1912.07441) — [arXiv](https://arxiv.org/pdf/1912.07441); "Using ML Models to Predict Points in FPL" (2022) — [ResearchGate](https://www.researchgate.net/publication/364322490_Using_ML_Models_to_Predict_Points_in_Fantasy_Premier_League)
- **Whitaker et al. (JRSS-C 2021)**: a Bayesian player-ability model (variational inference) extending Baio & Blangiardo. It is a related building block, not an FPL points model. — [UCL Discovery](https://discovery-pp.ucl.ac.uk/id/eprint/10110616)

### Inferences
- MSE figures of 5.6–9.8 imply an RMSE of about 2.4–3.1 pts per player-GW, depending on whether non-playing zeros are included. The figures are not comparable across papers because their samples and filters differ.

### Gaps
- I did not retrieve the Bangdiwala et al. and Gupta papers or their numbers, nor the Valouxis (2023) comparison cited by OpenFPL.

## Accuracy benchmarks and realistic ceiling

### Takeaway
There are no rigorous season-long public head-to-heads between the major services. OpenFPL (7 GWs) and a single-GW blog comparison are the main evidence. Errors are dominated by haulers (RMSE about 5 for ≥5-point returns, against about 1.5 for 3–4 points), so the realistic ceiling is low. Gains come mostly from minutes and from getting return probabilities right, not from predicting hauls.

### Cited Findings
- **OpenFPL vs FPL Review**: hauler RMSE is about 5.1–5.2 for both models, against 5.6 for a naive baseline. — [OpenFPL](https://arxiv.org/html/2508.09992v1)
- **FPL Watchmen GW1 2025/26** compared FF Scout, FPL Form, FF Fix, FPL Team, FF Hub, FPL Review and Draft Hound. All were within 1 point on average. FF Scout was closest overall, and the 30-man squad built from FF Scout's predictions scored the most. FFH and FPL Form were at about two-thirds of FF Scout's total, with FPL Review "close behind". Most sites rarely predicted 6+ hauls. The author warns that one GW is a tiny sample. — [FPL Watchmen](https://fplwatchmen.substack.com/p/fpl-2025-gw1-analysis-of-prediction)
- **FPL Review's own claim**: it is about 15% better R² for goals than bookmakers (0.129 against 0.112). — [FPL Review 2020](https://docs.fplreview.com/articles/massive-data/)
- **Onside's claims**: MAE 1.57 against 1.86 for `ep_next` (unverified, with inconsistencies noted above). — [Onside](https://onsidearena.com/accuracy)

### Inferences
- A sound evaluation should use prospective, deadline-time projections. It should report error by return category and separately for zeros (did not play) and players who played, and it should evaluate decision value such as squad points, not just RMSE. FPL Review re-runs projections at the deadline for exactly this reason.

### Gaps
- I found no Reddit or community season-long tracker comparing FPL Review, FFH and Solio.

## Design choices that distinguish the best models

### Takeaway
The leaders model components (minutes, team goals, player shares, CS, bonus) and combine them through the scoring rules, often by simulation. They blend market odds with xG-based performance data, weight recent data with shrinkage, and model minutes explicitly. Direct-regression ML can compete on returns but struggles with zeros.

### Cited Findings
- **Component plus market blend**: FPL Review lists per-event EV, market odds plus performance plus tactical features, and hourly news and xMins updates — [Massive Data docs](https://docs.fplreview.com/the-model/projections/massive-data-model/). Solio is market-based — [Jake Thom](https://jakethom95.substack.com/p/exploring-solio-analytics-fpls-newest). AIrsenal builds team goals from xG with CMP, a Dirichlet player share and shrunk bonus — [AIrsenal docs](https://raw.githubusercontent.com/alan-turing-institute/AIrsenal/main/docs/how-it-works.md)
- **Sparse data**: FPL Review falls back to market odds for players with fewer than 5 matches, which handles new signings — [FPL Review 2020](https://docs.fplreview.com/articles/massive-data/). AIrsenal fills minutes gaps with last season's average at the current team — [AIrsenal docs](https://raw.githubusercontent.com/alan-turing-institute/AIrsenal/main/docs/how-it-works.md)
- **Noisy signals**: raw recent goals are worse than useless, and xG needs about 20 games — [FPL Review 2020](https://docs.fplreview.com/articles/massive-data/)
- **DEFCON**: the 2025/26 rules added defensive contributions, and AIrsenal (`--no-def-con`) and Solio both model them — [AIrsenal docs](https://raw.githubusercontent.com/alan-turing-institute/AIrsenal/main/docs/how-it-works.md); [Jake Thom](https://jakethom95.substack.com/p/exploring-solio-analytics-fpls-newest)

### Inferences
- A "better than FPL Review" design would combine three things: OpenFPL-style ML for return rates, an explicit probabilistic xMins model (FPL Review's edge on zeros), and market priors for sparse-data players and promoted teams. All three are supported by the evidence above. The blend itself is a recommendation, not proven.

### Gaps
- I found no public source on how any tool handles promoted teams specifically (as of 2026). Common practice, such as regressing to a Championship-adjusted prior or using market odds, is unconfirmed.
