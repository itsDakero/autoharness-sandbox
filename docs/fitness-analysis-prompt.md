# Fitness phase 2: analysis like the best training apps (rewritten prompt)

The full picture. Don't queue this file: queue the 5 split notes in `docs/fitness-analysis/`,
one at a time (see the end). Written 2026-10-17 after comparing
`tools/fitness` with intervals.icu, Runalyze, TrainingPeaks, Whoop, Oura, Athlytic and Garmin Connect.

## Problem
The Fitness app shows the raw numbers well (since the 2026-10-17 redesign: readiness ring, tiles
with 7-day deltas and sparklines, chart cards). But it does not explain them. The best apps add
analysis on top of the same data. Dan's app is missing most of it:

| Analysis | Who does it | Fitness app today |
|---|---|---|
| Fitness / fatigue / form (CTL / ATL / TSB) | intervals.icu, TrainingPeaks | no |
| Load ramp rate and acute:chronic ratio (ACWR) | EveryStride, Garmin "load ratio" | no |
| HRV "normal range" band, not just a median | Athlytic, Oura, Whoop | no (7/30-day median only) |
| Own recovery score from HRV + RHR + sleep + check-in | Whoop, Athlytic | no (Garmin readiness only) |
| Strain vs recovery each day | Whoop | no |
| Time in HR zones, 80/20 polarisation | Runalyze, intervals.icu | no |
| Aerobic efficiency (pace at HR) and decoupling | intervals.icu, TrainingPeaks | no |
| Effective VO2max per run, race predictions vs PBs | Runalyze (VDOT, "marathon shape") | no |
| Monotony and strain from session-RPE (Foster) | TrainingPeaks-style coaches | no (sRPE stored, unused) |
| Sleep debt and sleep consistency | Whoop, Oura | no |
| Illness early warning (RHR up + HRV down) | Oura "Symptom Radar", Whoop | no (check-in markers only) |
| Volume calendar heatmap, long-run share, streaks | Strava, intervals.icu | partly (weekly distance chart) |
| Weekly written summary | Whoop/Oura coaches | no (planned for phase 2) |

## Proposal
Add an **Analysis** layer to `tools/fitness`. Stdlib maths in `app/logic.py` (or a new
`app/analysis.py`, also stdlib only), unit-tested. Same look as the redesign: tiles, chips
coloured good/warn/bad, chart cards. Each number gets a one-line "what this means".

### 1. Training load
**Built** (0.3.0, `app/analysis.py`; see the Analysis section of `tools/fitness/README.md`).
- **Daily load** = Garmin `training_load` per activity, plus FiiT `srpe` scaled to the same range
  (fit the scale once from FiiT classes that matched a Garmin activity with a load).
- **Fitness (CTL)** = 42-day exponential average of daily load. **Fatigue (ATL)** = 7-day.
  **Form (TSB)** = CTL − ATL (yesterday's values).
- **Form zones** (intervals.icu style): fresh > +5, neutral −10..+5, optimal −30..−10,
  high risk < −30. Chart: CTL line, ATL line, TSB bars coloured by zone.
- **Ramp rate** = CTL change per week; warn above ~+5/week.
- **ACWR** = 7-day load ÷ 28-day load; band 0.8–1.3 green, > 1.5 red.
- **Monotony** (7-day mean ÷ SD of daily load) and **strain** (weekly load × monotony); warn when
  monotony > 2.

### 2. Recovery
**Built** (0.4.0, `app/analysis.py`; see the Recovery subsection of `tools/fitness/README.md`).
- **Normal range bands**: for HRV and resting HR, a band = 60-day mean ± 1 SD. Plot the 7-day
  rolling average against the band (Athlytic/Oura). Today's tile chip says "in range", "below",
  "above", not just ±.
- **Own recovery score 0–100** (Whoop style), shown next to Garmin's readiness:
  HRV z-score, RHR z-score (inverted), sleep vs need, plus check-in overrides
  (ill = capped at 33, sore legs/stressed/slept badly = −10 each). Show the parts, not only the total.
- **Sleep debt**: 7-day sum of (need − actual), need defaults to 8 h (setting). **Consistency**:
  SD of bedtime and wake time over 14 days (needs sleep start/end, from the raw sleep JSON).
- **Strain vs recovery**: daily chart of load vs recovery score; flag days with high load on a red
  recovery day.

### 3. Running performance
- **HR zones**: 5 zones from max HR (setting; default the highest `max_hr` seen in 12 months) or
  Garmin's own zones. Time in zone per run (`get_activity_hr_in_timezones`, store in a new
  `activity_zones` table; raw JSON kept as usual). Weekly stacked bar; **80/20 check**:
  share of time in Z1–Z2.
- **Aerobic efficiency**: pace ÷ HR for easy runs (avg HR in Z2), trend over 180 days.
  Rising = fitter at the same effort. **Decoupling** from laps: pace:HR of the second half vs the
  first half; < 5% = good aerobic base (only for runs ≥ 45 min).
- **Effective VO2max per run** (Runalyze method: from pace and %HRmax), with a correction factor
  from the best recent race. Compare with Garmin's VO2max.
- **Race predictions**: Riegel (`T2 = T1 × (D2/D1)^1.06`) and VDOT from the best recent 5k effort,
  for 5k, 10k, half. Show next to the PBs. Add an **endurance gap** line: actual half PB vs the
  half the 5k predicts (today ~20 min slower), and a "long-run readiness" % like Runalyze's
  marathon shape (weekly volume and longest run vs what the target needs).
- **Best efforts**: fastest 1 km / 1 mi / 5k inside any run (needs per-second data:
  `get_activity_details`; laps as fallback). Pace-duration curve for the last 90 days vs all time.

### 4. Volume and habits
- **Calendar heatmap** (GitHub style) of daily load for 12 months.
- **Weekly summary row**: distance, time, runs, FiiT classes, long-run share of weekly distance
  (warn above 35%), streak of weeks with ≥ 2 runs.
- **Cadence trend** for easy runs.

### 5. Illness early warning
**Built** (0.4.0, with section 2).
- Flag when resting HR is ≥ 3 bpm above its band **and** HRV is below its band for 2 nights in a
  row, or one of those plus a "slept badly"/"stressed" check-in. Show a warn banner on Today
  ("your numbers look like the start of illness: consider an easy day").
- After 60 days, score how often flags came 1–3 days before an "ill" check-in (precision/recall on
  his own data), shown on the Trends page. This is the "felt ill while the numbers looked fine"
  problem from phase 1.

### 6. Weekly written summary
**Built** (0.7.0, `app/insights.py`; see the Weekly summary section of `tools/fitness/README.md`).

- Sunday evening, the Mac mini's model (as Hermes uses; never `ANTHROPIC_API_KEY`) gets a small JSON
  of the week's numbers above and writes 5 bullets: what improved, what slipped, what it means, one
  suggestion. Stored in a `summaries` table, shown on a new **Insights** page, sent to Discord
  with `scripts/discord.sh`. The model only sees numbers, never raw Garmin JSON or tokens.

### Pages
- **Today**: add form (TSB) tile, recovery score tile, ACWR chip, illness banner when flagged.
- **Trends**: add the load chart (CTL/ATL/TSB), HRV/RHR with bands, efficiency, zones, heatmap.
- **Runs / run detail**: zones bar, decoupling, effective VO2max, best efforts in the run.
- **PBs**: predictions and endurance gap next to each PB.
- **Insights** (new): weekly summaries, illness-flag accuracy.
- **Settings** (new, small): max HR, sleep need, zone source.

## Notes
- Schema: new tables `activity_zones`, `best_efforts`, `summaries`, `settings`; append migrations
  in `app/db.py`, never edit old ones. Everything else is computed on page load from `daily`,
  `activities`, `laps`, `fiit`, `checkins` (cache only if a page gets slow).
- New Garmin calls (`get_activity_hr_in_timezones`, `get_activity_details`): check the names in the
  pinned `garminconnect` wheel first; rate-limit like the backfill (2 s gap, max 20 activities per run).
- Every formula has a unit test with a worked example. Thresholds live in one place as constants.
- Charts stay inline SVG, no CDN. Colours use the CSS tokens (`--good`, `--warn`, `--bad`).
- Not medical advice: keep the footer, and word the illness banner as a suggestion.
- Too big for one build. It is split into 5 ready notes in `docs/fitness-analysis/`.
  Queue them **one at a time, in order**, and deploy each before queuing the next
  (they edit the same files, so a build made before the last one is merged would conflict):
  1. `1-fitness-load.md` (section 1 + Today tiles)
  2. `2-fitness-recovery.md` (sections 2 + 5)
  3. `3-fitness-running.md` (section 3, new Garmin calls)
  4. `4-fitness-volume.md` (section 4)
  5. `5-fitness-weekly-summary.md` (section 6)

## Sources
- intervals.icu fitness/fatigue/form: https://app.intervals.icu
- Runalyze effective VO2max, race prediction, marathon shape: https://runalyze.com/glossary/marathon-shape,
  https://blog.runalyze.com/tutorial/runalyze-understanding-the-calculations/
- Tool comparison incl. ACWR (EveryStride) and Runalyze TRIMP/VDOT: https://www.gneta.app/blog/garmin-data-analysis-tools-2026
- Fitness/fatigue/freshness dashboards: https://the5krunner.com/2026/07/13/my-running-dashboard-analytics/
