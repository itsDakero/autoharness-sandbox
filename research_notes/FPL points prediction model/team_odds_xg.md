# Team-level match prediction for an FPL points model: betting odds plus xG to forecast team goals, clean sheets and results

Scope note: research done 25 Oct 2026 with about 16 search/fetch calls. Some core sources could not be opened (the Significance magazine page returned 403; most journal PDFs were not fetched). Where a formula or result comes from a classic paper that I cite by DOI but did not re-read this session, it is marked "(paper cited, not re-fetched)". Treat those as standard textbook definitions, not freshly verified quotes.

## 1. Classical goal models (Poisson, Maher, Dixon-Coles, bivariate Poisson, negative binomial, Bayesian hierarchical, dynamic, pi-ratings): which work best for the EPL?

### Takeaway
Use a Poisson-family attack/defence model with a Dixon-Coles low-score correction and exponential time decay as the baseline. Bivariate, diagonal-inflated, negative-binomial and dynamic Bayesian variants bring small and inconsistent gains on EPL data. None of these goals-only models beats closing betting odds, so their main use in an FPL model is projecting fixtures beyond the odds horizon, not replacing the market.

### Cited Findings
- **Maher (1982), independent Poisson (paper cited, not re-fetched).** Home goals X ~ Poisson(λ), away goals Y ~ Poisson(μ), with λ = α_home · β_away · γ and μ = α_away · β_home. α is attack, β is defence (higher β means a weaker defence) and γ is home advantage. Fitted by maximum likelihood with a constraint such as mean(α) = 1. — [Maher 1982, Statistica Neerlandica](https://doi.org/10.1111/j.1467-9574.1982.tb00782.x)
- **Dixon & Coles (1997) (paper cited, not re-fetched).** Multiply the independent Poisson probabilities by τ(x, y), which adjusts the four low scores:
  - τ(0,0) = 1 − λμρ
  - τ(0,1) = 1 + λρ
  - τ(1,0) = 1 + μρ
  - τ(1,1) = 1 − ρ
  - τ = 1 for every other score

  The likelihood is weighted by φ(t) = exp(−ξ·t), where t is the age of each match. — [Dixon & Coles 1997, JRSS C](https://doi.org/10.1111/1467-9876.00065)
- **Decay parameter.** Dixon and Coles chose ξ by maximising predictive log-likelihood. With time measured in half-weeks (days / 3.5) they got ξ = 0.0065, a half-life of about one year. — [arXiv 2605.16066](https://arxiv.org/pdf/2605.16066)
- penaltyblog's examples use `dixon_coles_weights(dates, xi=0.001)` per day: ξ = 0 weights all matches equally, about 0.001 keeps older matches relevant, and about 0.03 focuses on recent results. — [penaltyblog models overview](https://penaltyblog.readthedocs.io/en/latest/models/overview.html)
- A football MCP tool uses ξ = 0.0018 per day as a default and includes `tune_time_decay`, a grid search over ξ scored by backtest RPS. — [search result, glama.ai MCP listing](https://images.glama.ai/mcp/servers/ellisegrant/afrodevXG)
- **Models in penaltyblog.**

  | Model | What it does | Limitation |
  |---|---|---|
  | Poisson | Baseline | Overpredicts high scores |
  | Dixon-Coles | Fixes 0-0, 1-0 and 1-1 | |
  | Bivariate Poisson | Adds score correlation | |
  | Zero-inflated Poisson | Extra 0-0s only | |
  | Negative binomial | Handles overdispersion | Still assumes independent scores |
  | Weibull count + copula | Flexible score dependence | Heavy to compute |
  | Bayesian | MCMC posteriors | Slow; needs convergence checks |
  | Hierarchical Bayesian | League-wide priors | Slowest |

  The page gives no head-to-head accuracy numbers. — [penaltyblog models overview](https://penaltyblog.readthedocs.io/en/latest/models/overview.html)
- **Karlis & Ntzoufras (2003), bivariate Poisson (paper cited, not re-fetched).** X = W1 + W3 and Y = W2 + W3, with Wk ~ Poisson(λk), so Cov(X, Y) = λ3. The diagonal-inflated version adds extra probability to draws. — [Karlis & Ntzoufras 2003, JRSS D](https://doi.org/10.1111/1467-9884.00366)
- **Baio & Blangiardo (2010), Bayesian hierarchical (paper cited, not re-fetched).**
  - log θ_home = home + att_h + def_a
  - log θ_away = att_a + def_h
  - att and def are drawn from shared normal priors with sum-to-zero constraints, which shrinks team ratings toward the league mean.

  — [Baio & Blangiardo 2010, J. Applied Statistics](https://doi.org/10.1080/02664760802684177)
- **Koopman & Lit (2015), dynamic model (paper cited, not re-fetched).** Bivariate Poisson with attack and defence strengths that follow random walks / AR(1) processes, estimated as a state-space model on EPL data. — [Koopman & Lit 2015, JRSS A](https://doi.org/10.1111/rssa.12042)
- **Recent EPL comparison (2025 preprint).** The paper tests six count models under three dynamic Bayesian frameworks on EPL, Bundesliga and La Liga, 2020/21 to 2024/25:
  - Models: bivariate Poisson, diagonal-inflated bivariate Poisson, double Poisson, negative binomial, Skellam and zero-inflated Skellam.
  - Frameworks: Owen 2011, Egidi et al. 2018, and the authors' new weighted dynamic approach.
  - EPL result, last three rounds of 2024/25, diagonal-inflated bivariate Poisson with the new approach: Brier 0.602, ACP 0.421.
  - The new approach is usually but not always best. In one EPL table Owen (2011) has a slightly lower Brier score.
  - Gains are largest for short-horizon forecasts.
  - There is no comparison against bookmaker odds. Not peer reviewed.

  — [arXiv 2508.05891](https://arxiv.org/html/2508.05891v1)
- **Pi-ratings and gradient-boosted features.** Pi-ratings come from Constantinou & Fenton (2013). Hubáček, Šourek & Železný won the 2017 Soccer Prediction Challenge (Machine Learning journal special issue) with gradient-boosted trees on hand-built features, using pi-ratings and PageRank ratings as inputs. — [CTU news](https://cs.fel.cvut.cz/en/news/detail/1302); [paper record](https://scholarhub.vn/publication/:slug/a5c98243-1c17-45e8-be49-fce7d4ed5063)
- **Pi-rating implementations.** R package `piratings` on CRAN. — [CRAN piratings](https://cran.uni-muenster.de/web/packages/piratings/index.html)
- **Pi-ratings paper.** Constantinou & Fenton, "Determining the level of ability of football teams by dynamic ratings based on the relative discrepancies in scores between adversaries", JQAS 2013. — [doi](https://doi.org/10.1515/jqas-2012-0036) (paper cited, not re-fetched)

### Inferences
- Pi-ratings and Elo give a single strength rating (or an outcome probability), not separate attack and defence goal rates. An FPL model needs λ (goals for) and μ (goals against) per team per fixture, so an attack/defence Poisson-family model is the better structural fit. Pi-ratings are best used as a feature or a sanity check.
- Dixon and Coles' half-week ξ = 0.0065 is about 0.0019 per day (0.0065 / 3.5), which matches the common 0.0018–0.002 per-day defaults. Tune ξ by rolling-origin RPS or log-loss on your own data. Expect the best value with xG inputs to differ from the best value with goals.
- Clean sheet probabilities are especially sensitive to the low-score correction. Under independent Poisson, P(CS) = e^(−λ_opp). With Dixon-Coles, the 0-0 adjustment (1 − λμρ) feeds into P(CS) = Σ_x P(x, 0). Because ρ is usually slightly negative, Dixon-Coles raises 0-0 and 1-1 and lowers 1-0 and 0-1 relative to Poisson. The net change to P(CS) is small but not zero.
- For FPL, adding a negative binomial or bivariate layer is unlikely to beat calibrating directly to market prices for the next gameweek. Keep the model simple and calibrated.

### Gaps
- I did not find a recent head-to-head table (RPS or log-loss) ranking Dixon-Coles against bivariate Poisson, negative binomial, Koopman-Lit and pi-ratings on the same EPL test seasons.
- I did not retrieve Constantinou & Fenton's reported RPS, or the 2017 challenge leaderboard RPS values.
- A typical fitted Dixon-Coles ρ for the EPL was not retrieved. It is commonly reported as small and negative, around −0.05 to −0.15, but that is unverified here.

## 2. xG-based team ratings: npxG for and against, predictive value vs goals, weighting/decay, mixing, game state

### Takeaway
The literature broadly agrees that shot-based and xG measures are more repeatable than goals, so team ratings fitted to non-penalty xG (plus a penalty term) should forecast future goals better than goals-based ratings. I found no fresh EPL split-half statistic to quantify the gain. Practical setups fit goalmodel or penaltyblog with xG as the response, or mix xG and goals.

### Cited Findings
- **Fitting to xG directly.** The goalmodel R package can fit expected goals instead of observed goals as the response, using `model = 'gaussian'` or `'ls'` (least squares). The author calls this experimental and sometimes unstable. — [opisthokonta via R-bloggers, 2019](https://www.r-bloggers.com/2019/01/expected-goals-from-bookmaker-odds/)
- goalmodel is a package for building prediction models of goals, aimed mainly at football. — [goalmodel GitHub](https://github.com/opisthokonta/goalmodel)
- **Repeatability of creation vs finishing.** A Wharton research note on EPL 2022–25 finds shot-based measures more repeatable year to year than goals-over-expected: "creation is the steady signal; finishing is higher variance." — [Wharton Sports Business, "Beyond expected goals"](https://wsb.wharton.upenn.edu/beyond-expected-goals/)
- **First-half xG and second-half points.** A 2026 preprint on EPL 2015/16 found that teams with stronger first-half-season xG profiles earned more points in the second half, even after controlling for league position. — [arXiv 2602.15673](https://arxiv.org/abs/2602.15673v1)
- **Counterpoint.** An article in The Conversation argues that actual goals "remain king" for predicting who wins, and notes that xG ignores the identity of the shooter and the goalkeeper. — [The Conversation](https://theconversation.com/a-brief-history-of-statistics-in-football-why-actual-goals-remain-king-in-predicting-who-will-win-194314)

### Inferences
- **Recommended construction.**
  1. Fit attack and defence ratings to npxG for and against per match, with time decay and a home term.
  2. Add expected penalty xG per team: about 0.76 xG per penalty times the team's penalty-award rate (the 0.76 figure is a commonly used value, not verified this session).
  3. Optionally blend in goals-based ratings with a small weight, or fit both and stack them by out-of-sample log-loss.
- **Practical sources of xG.** FBref (Opta), Understat and The Analyst publish team npxG. Their models differ, and Understat's xG runs slightly higher than Opta's.
- **Game state.** Leading teams concede more xG and create less. A team's xG is therefore partly a function of score state. Possible corrections are weighting xG by game state, using only the time spent level, or simply accepting the noise. I found no sourced quantification of this effect for the EPL.
- **Fitting xG with a Poisson likelihood.** xG is not an integer, but quasi-Poisson / Gaussian least squares works, and so does a Poisson likelihood with non-integer y (penaltyblog and statsmodels accept it). Separately, the "xG to probability" step should simulate shot-by-shot (Poisson-binomial) only if you need the score distribution from single-match xG. For forecasting, use the rates.

### Gaps
- No split-half or next-season correlation figures (xG vs goals vs points) for the EPL were retrieved. StatsBomb, American Soccer Analysis and 11tegen11 published such analyses in the 2010s, but they were not fetched here.
- There is no sourced optimal xG/goals mixing weight, and no sourced decay rate for xG-based ratings.
- Game-state adjustment magnitudes are unsourced.

## 3. Betting odds as inputs: accuracy of closing odds, de-vig methods, turning 1X2, O/U 2.5 and AH prices into team expected goals, clean sheet markets

### Takeaway
Market prices are the strongest public forecast. Bookmaker-implied ratings carry more information about team strength than results do. To turn odds into goal rates:
1. De-vig each market. Power, Shin or odds-ratio methods beat the basic proportional method.
2. Solve for the (λ, μ) pair that reproduces the de-vigged 1X2 probabilities, plus the O/U 2.5 probability if available, under Poisson or Dixon-Coles. O/U alone fixes only λ + μ; 1X2 (or AH) fixes how the total splits between the teams.

### Cited Findings
- **Odds carry more information than results.** Wunderlich's dissertation, supervised by Memmert, reports that pre-game betting odds contain more information about team strength than actual match results. It also stresses that profitability and predictive accuracy must be judged separately. — [Wunderlich dissertation, DSHS Köln](https://fis-db.dshs-koeln.de/ws/portalfiles/portal/6465170/Dissertation_Wunderlich.pdf)
- **The Betting Odds Rating System.** Wunderlich & Memmert's Elo-style rating is driven by bookmaker-implied probabilities rather than results. Odds-based ratings looked more stable through a season. For example, Leicester 2015/16 had attack and defence near average in the odds-based fit but much stronger in the results-based fit. — [opisthokonta via R-bloggers](https://www.r-bloggers.com/2019/01/expected-goals-from-bookmaker-odds/); paper: [arXiv 1802.08848](https://arxiv.org/abs/1802.08848) (paper cited, not re-fetched)
- **Odds vs prediction markets vs tipsters.** Spann & Skiera (2009), using 678–837 Bundesliga games over three seasons, found prediction markets and betting odds equally accurate, and both clearly better than tipsters. — [IAOR record](https://iaorifors.com/paper/64997)
- **Štrumbelj (2014) (paper cited, not re-fetched).** "On determining probability forecasts from betting odds", International Journal of Forecasting. It found Shin-based probabilities more accurate than basic normalisation, and betting-exchange-derived probabilities at least as good. — [doi](https://doi.org/10.1016/j.ijforecast.2014.02.008)
- **De-vig formulas.** From the documentation of the R `implied` package (opisthokonta). r_i = 1/O_i is the raw implied probability, n the number of outcomes and M the margin.

  | Method | Formula | Notes |
  |---|---|---|
  | Basic (multiplicative) | p_i = r_i / Σr | "tend[s] to be the least accurate" |
  | Additive | p_i = r_i − (Σr − 1)/n | Can go negative for longshots. Equals Shin for two outcomes |
  | Power | p_i = r_i^(1/k), k chosen so Σp = 1 | Called the logarithmic method by Buchdahl |
  | Odds ratio | OR = p_i(1 − r_i) / (r_i(1 − p_i)), constant across outcomes | Cheung 2015 |
  | Margin weights proportional to odds (wpo) | p_i = (n − M·O_i) / (n·O_i) | Models the favourite-longshot bias. Buchdahl |
  | Shin, balanced books | Solve for insider share z | Shin 1992/93; Fingleton & Waldron 1999 |
  | Jensen–Shannon distance | Not given in this table | C. D. Long |

  Since v0.5, `target_probability` can be above 1 for multi-winner markets. — [implied vignette, CRAN](https://cran.r-project.org/web/packages/implied/vignettes/introduction.html)
- **Odds-ratio closed form.** Solving the OR definition gives p_i = OR·r_i / (1 + r_i(OR − 1)). This is my derivation; the vignette's rendering was garbled. — same source
- **penaltyblog equivalents.** `pb.implied.calculate_implied(odds, method=ImpliedMethod.X)`, with X = MULTIPLICATIVE (default), ADDITIVE, POWER, SHIN, DIFFERENTIAL_MARGIN_WEIGHTING, ODDS_RATIO or LOGARITHMIC. It returns the probabilities, the margin and method parameters (Shin z, power k). The documentation does not rank the methods. — [penaltyblog implied docs](https://penaltyblog.readthedocs.io/en/latest/implied/implied.html)
- **1X2 to expected goals.** Search for the (λ_home, λ_away) whose Poisson-implied home/draw/away probabilities match the de-vigged odds. The 2019 post used power-method de-vigging on 2015/16 EPL odds. goalmodel can then fit team attack and defence ratings to these market-implied expected goals. — [opisthokonta via R-bloggers](https://www.r-bloggers.com/2019/01/expected-goals-from-bookmaker-odds/)
- **O/U to expected total.** With total goals ~ Poisson(λ + μ), solve ppois(floor(line), λtot) = P(under) with `uniroot` on [0.01, 10]. Example: P(under 2.5) = 0.62 gives λtot = 2.21. O/U alone cannot split the total between the teams; "there is no information about this in over/under odds alone." — [opisthokonta via R-bloggers, 2020](https://www.r-bloggers.com/2020/09/expected-goals-from-over-under-odds/)
- **Reconstructing correct-score odds.** An OddsPapi tutorial on Poisson in Python solves λ_home and λ_away from market prices: the 1X2 price is needed to split the O/U-implied total. — [OddsPapi blog](https://oddspapi.io/blog/?p=3120)
- **Wunderlich & Memmert's blend.** They fit a score-based model on actual results and then take a weighted average of its expected goals and the odds-implied expected goals. — [opisthokonta via R-bloggers search summary](https://www.r-bloggers.com/2019/01/expected-goals-from-bookmaker-odds/)

### Inferences
- **Recommended solver (no single source; standard practice).** For each fixture, minimise over (λ, μ):

  ```
  Σ_k w_k · (P_model,k(λ, μ, ρ) − P_market,k)²
  ```

  or the KL divergence. Here k runs over {H, D, A, Over 2.5} and, if available, the Asian handicap line and both-teams-to-score.
  - P_model comes from a Dixon-Coles score matrix, truncated at about 10 goals.
  - Fix ρ at its league-fitted value rather than solving for it. Three 1X2 probabilities give only two independent constraints, plus one from O/U, so (λ, μ) is exactly identified by 1X2 alone and over-identified with O/U.
  - Put more weight on the most liquid markets: Asian handicap and the main totals line at Pinnacle or Betfair.
  - Use log(λ) and log(μ) as the optimisation variables.
- **Clean sheet from the solved rates.** P(team A keeps a clean sheet) = Σ_x P(x, 0) from the Dixon-Coles matrix, or e^(−μ) under independent Poisson.
- **Team-total markets.** P(A over 0.5) = 1 − P(CS for B). This gives μ directly via μ = −ln(P(A scores 0)) under Poisson, a good cross-check.
- **"Win to nil."** Price = Σ_{x>y=0} P(x, 0), another constraint on the low-score region.
- These derivative markets carry higher margins. Two-way markets can be de-vigged with power or Shin (equivalent to additive for two outcomes, per the vignette).
- **Fitting team ratings to market rates.** Fit attack, defence and home parameters to the market-implied (λ, μ) of all recent fixtures (goalmodel with `model='gaussian'`, or a log-linear least-squares regression of log λ). This gives market-implied team ratings that can be projected to any future fixture. It is the key step for FPL gameweeks 3–8 (see section 5).
- Prefer Pinnacle or Betfair closing prices. Retail books' higher margins and favourite-longshot shading add noise. Power or Shin de-vigging corrects some of that shading.

### Gaps
- I did not retrieve a quantitative comparison of de-vig methods on EPL 1X2. The vignette says only that the basic method tends to be least accurate. Štrumbelj (2014) is the reference, but its numbers were not re-fetched.
- No source was fetched quantifying the closing-line accuracy of Pinnacle vs Betfair vs average odds for the EPL. This is widely asserted but not verified this session.
- Asian handicap to (λ, μ): no worked source was retrieved. Quarter lines need split-stake handling (half on each adjacent line), and push probabilities must be removed. Implementation is left to the solver above.

## 4. Player-level markets: anytime scorer, assist, 2+ goals, shots, cards; implied player xG and de-vigging

### Takeaway
I found no authoritative source on deriving player xG from anytime scorer odds. The standard approach is the Poisson inversion λ_p = −ln(1 − p). Because these markets are one-sided and carry large margins, the best de-vig is to normalise player λs so they sum to the team's market-implied goal expectation (minus own goals), rather than de-vigging prices one at a time.

### Cited Findings
- **Player-prop margins.** A public panel (52 bookmakers, odds collected 29 Jun–2 Aug 2026) measured an average 7.93% margin across 699,733 two-sided player-prop markets. That is 66% more than two-way head-to-head markets (4.77%). Three-way soccer 1X2 averaged 7.67%. Goalscorer markets are not broken out. Note the dates are mostly off-season for the EPL. — [Mendeley Data, Bookmaker Margin Panel](https://data.mendeley.com/datasets/yt3xsvk7zn)
- **Overround is not margin in multi-winner markets.** Summing implied probabilities measures the margin only when exactly one outcome wins. Anytime scorer lists, where several players can score, do not satisfy this. — [OddsPapi, bookmaker margin analytics](https://oddspapi.io/blog/?p=3086)
- **Multi-winner de-vigging.** The `implied` package's `target_probability` > 1 handles markets with several winners. — [implied vignette](https://cran.r-project.org/web/packages/implied/vignettes/introduction.html)
- **Bet rules and a rough heuristic.** Anytime bets are usually voided if the player does not play. A 40% per-appearance scorer is priced around 2.50–3.00. This is a weak, unverified heuristic. — [SoccerNews goalscorer guide](https://www.soccernews.com/goalscorer-betting/403382/)

### Inferences (method proposal, unsourced)
- **Single-player inversion.** Fair anytime probability p, from a de-vigged price, gives the player's goal rate for the match under Poisson: λ_p = −ln(1 − p). Check it against the 2+ goals market: P(2+) = 1 − e^(−λ)(1 + λ). The ratio of "2+" to "anytime" prices shows whether the book uses a Poisson-consistent λ.
- **Team-consistency de-vig.** Within a team, Σ_p λ_p (over all players with prices, scaled by expected minutes) should equal the team's market-implied λ_team × (1 − own-goal share).
  1. Solve a single power or multiplicative shrink factor so the implied λs meet this constraint.
  2. Apply the shrink factor as p_fair = 1 − (1 − p_raw)^c, or by scaling λ_p.

  This uses the 1X2/AH market, which has low margins, to anchor the high-margin player market.
- **Minutes risk.** Because bets are voided for non-starters/non-appearances (book rules vary), the price is conditional on the player appearing. FPL needs the unconditional figure: E[goals] = P(plays) × λ_p, with λ_p scaled for expected minutes.
- **Assists and shots.** Assist, shots and shots-on-target markets (often Over/Under 0.5/1.5) can be inverted the same way into per-match Poisson rates. A two-sided O/U can be de-vigged with power or Shin, which are equivalent to additive for two outcomes.
- **Cards** feed FPL deductions. A yellow card at price p gives P(booked) after a basic de-vig. It is a minor term.

### Gaps
- No academic or high-quality source was found on anytime scorer de-vigging or on how accurate player-implied xG is against outcomes.
- No Pinnacle- or EPL-specific goalscorer margins were found.
- Own-goal share (about 3% of EPL goals is often quoted) was not verified.

## 5. Blending market and statistical estimates, odds availability, projecting GW+3 to GW+8

### Takeaway
Use market-implied (λ, μ) for fixtures with liquid odds, typically only the next gameweek. Further out, fit team attack and defence ratings to recent market-implied goal rates (optionally blended with npxG ratings) and project them through the fixture list. Weight the blend by out-of-sample log-loss.

### Cited Findings
- **Wunderlich & Memmert's blend.** A weighted average of results-model expected goals and odds-implied expected goals. — [opisthokonta](https://www.r-bloggers.com/2019/01/expected-goals-from-bookmaker-odds/)
- **Fitting ratings to market-implied goals.** goalmodel can fit attack and defence ratings with market-implied expected goals as the response, giving odds-based ratings that are more stable than results-based ones. — [opisthokonta](https://www.r-bloggers.com/2019/01/expected-goals-from-bookmaker-odds/)
- **Dynamic models help most at short horizons.** — [arXiv 2508.05891](https://arxiv.org/html/2508.05891v1)

### Inferences
- **Pipeline.**
  1. For every past and next-GW fixture with closing (or current) Pinnacle/Betfair odds, solve market (λ, μ).
  2. Fit log λ_ij = home + att_i − def_j by weighted least squares, with time decay ξ of about 0.002–0.005 per day. Markets update quickly, so a shorter half-life than results-based models is reasonable.
  3. Separately fit an npxG Dixon-Coles model.
  4. Combine with log λ_blend = w·log λ_market-rating + (1 − w)·log λ_xG-rating, choosing w by rolling-origin log-loss on goals. Alternatively, use the market ratings as the prior mean in a Bayesian model where npxG updates enter as observations.
  5. For gameweek h ahead, shrink toward the mean as uncertainty grows. A dynamic random-walk model (Koopman-Lit style) handles this naturally.
- **Odds availability.** Next-gameweek EPL odds are widely available. Outright markets (title, relegation, top 4) and season-long team-points lines give extra long-horizon constraints on team strength. They can be converted with a simulated season and treated as additional calibration targets.
- **Clean-sheet and goal projections.** Feed the blended λ and μ into a Dixon-Coles matrix for each future fixture to get P(CS), the expected-goals distribution and the win probability for each FPL gameweek.

### Gaps
- No published optimal market-vs-xG weight was found.
- No evidence was found on how fast market-implied ratings degrade over a 3–8 week horizon.

## 6. Home advantage post-COVID, promoted teams, managerial changes, fixture congestion

### Takeaway
EPL home advantage collapsed in the empty-stadium season of 2020/21 and is generally believed to have recovered with fans back, possibly below pre-2020 levels. I could not retrieve 2022–2026 figures (the Significance page was blocked). Estimate the home parameter from recent seasons inside the model rather than hard-coding it. There was no time to research promoted teams, managerial changes or European congestion.

### Cited Findings
- **Empty stadiums.** After the 2020 restart behind closed doors, average EPL home points advantage fell from 0.48 to 0.10 points per game. Home goals were 1.55 → 1.52 and away goals rose 1.19 → 1.38. — [LCP press release, Dec 2020](https://www.lcp.com/media-centre/2020/12/covid-19-and-var-decimate-home-advantage-in-football-leagues-across-europe)
- **Conflicting estimates.** One bivariate Poisson study estimated the EPL home effect slightly higher after the Covid restart (0.264 vs 0.246, log scale). A 2022 study found no significant change in goal-based EPL home advantage. — [arXiv 2012.14949](https://arxiv.org/pdf/2012.14949); [search summary of later studies](https://lida.sport-iat.de/dfb/Record/4076053?lng=en)
- **Later seasons.** A Significance magazine article examines EPL home advantage for 2021/22–2024/25 after fans returned. Its content could not be retrieved (HTTP 403). — [Significance](https://significancemagazine.com/home-advantage-whats-changed-since-covid/)

### Inferences
- Fit γ (home) by maximum likelihood on the last 2–3 fan-attended seasons, with time decay. Do not hard-code a pre-2020 value of about +0.3 goals. Market-implied ratings already include the market's view of home advantage.
- **Promoted teams.** A common approach is to initialise them at the average of past promoted-team ratings, or from the market (relegation odds and first-gameweek prices), with wide uncertainty. Market prices fix this fastest, since odds reflect squad changes before any match data exists.
- **Manager changes and congestion.** Market prices adjust immediately. Statistical models do not, which is another argument for weighting the market heavily at the next gameweek. Congestion and rotation affect player minutes more than team λ in FPL. Handle them in the minutes model.

### Gaps
- No 2022/23–2025/26 EPL home-advantage figures were verified.
- No sourced findings on promoted-team performance, managerial "new manager bounce" effects, or the effect of European midweek fixtures on EPL goal rates.
- Recommended libraries are covered above:
  - [penaltyblog](https://penaltyblog.readthedocs.io/) (Python): models, `dixon_coles_weights`, `implied`
  - [goalmodel](https://github.com/opisthokonta/goalmodel) (R): models, odds-to-expected-goals
  - [implied](https://cran.r-project.org/web/packages/implied/) (R): de-vig
  - [piratings](https://cran.uni-muenster.de/web/packages/piratings/index.html) (R): pi-ratings
