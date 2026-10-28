# Fitness load: fitness, fatigue, form and ramp rate (fitness analysis 1 of 5)

## Problem
The Fitness app stores Garmin training load per activity and session-RPE per FiiT class, but never
adds them up. intervals.icu and TrainingPeaks turn the same data into fitness, fatigue and form, so
Dan can see if a block is paying off or piling up.

## Proposal
- **Daily load** = Garmin `training_load` per activity, plus FiiT `srpe` scaled to the same range.
  Fit the scale once from FiiT classes matched to a Garmin activity that has a load; default 1.0.
- **Fitness (CTL)** = 42-day exponential average of daily load. **Fatigue (ATL)** = 7-day.
  **Form (TSB)** = yesterday's CTL − ATL.
- **Form zones** (intervals.icu): fresh > +5, neutral −10..+5, optimal −30..−10, high risk < −30.
- **Ramp rate** = CTL change per week; warn above +5/week.
- **ACWR** = 7-day load ÷ 28-day load; 0.8–1.3 green, 1.3–1.5 amber, > 1.5 red.
- **Monotony** (7-day mean ÷ SD of daily load) and **strain** (weekly load × monotony); warn when
  monotony > 2.
- Pages:
  - Today: a Form tile (value + zone chip) and an ACWR chip.
  - Trends: a load chart card: CTL line, ATL line, TSB bars coloured by zone, 180 days.

## Notes
- Computed on page load from `activities` and `fiit`; no new tables.
- Builds first: notes 2 and 4 use the daily load from this one.

## Shared rules (all fitness analysis notes)
- Background and the full list of analyses: `docs/fitness-analysis-prompt.md`.
- Maths is stdlib only, in `tools/fitness/app/logic.py` or a new `app/analysis.py`. Each formula gets a
  unit test with a worked example. Thresholds live in one place as constants.
- Look: same as the 2026-10-17 redesign. Tiles, chips coloured with `--good`/`--warn`/`--bad`, chart cards.
  Charts are inline SVG, no CDN. Each new number gets a one-line "what this means".
- Schema: append migrations at the end of `MIGRATIONS` in `app/db.py`; never edit an old one.
- Bump the image tag in `tools/fitness/compose.yaml` (minor version).
- Not medical advice: keep the footer; word warnings as suggestions.

## Plan
Goal: Add up Garmin load and FiiT sRPE into a daily load, then show fitness/fatigue/form, ramp rate, ACWR, monotony and strain on Today and Trends. (Fitness analysis note 1 of 5.)
Kind: change to tools/fitness
Files:
- tools/fitness/app/analysis.py: new, stdlib only. Holds the constants, the maths and `svg_load_chart`
- tools/fitness/app/main.py: `today()` and `trends()` call analysis; pass the results to the templates
- tools/fitness/app/templates/today.html: a "Training load" section after the hero with two tiles, Form and Load balance
- tools/fitness/app/templates/trends.html: put the load chart card first, with a zone legend
- tools/fitness/app/static/style.css: TSB bar classes and CTL/ATL line classes
- tools/fitness/tests/test_analysis.py: new, one worked-example test per formula
- tools/fitness/compose.yaml: image `homelab/fitness:0.2.0` -> `homelab/fitness:0.3.0`
- tools/fitness/README.md: new "Analysis" section with the formulas, thresholds and edge rules
- docs/fitness-analysis-prompt.md: mark section 1 as built (one line)

analysis.py, decisions (the builder follows these exactly):
- Constants in one block: CTL_DAYS=42, ATL_DAYS=7, ACWR_SHORT=7, ACWR_LONG=28, RAMP_WARN=5.0,
  MONOTONY_WARN=2.0, ACWR_GREEN=(0.8, 1.3), ACWR_AMBER_MAX=1.5, MIN_SCALE_PAIRS=3,
  FORM_ZONES = fresh > +5 / neutral -10..+5 / optimal -30..<-10 / high risk < -30.
  Tones: fresh = chip with no class (neutral grey), neutral = no class, optimal = good, high risk = bad.
- `fiit_scale(pairs)`: pairs are (srpe, garmin_load) for FiiT rows whose activity_id points at an
  activity with training_load > 0. The scale is sum(load)/sum(srpe). Return 1.0 when there are fewer
  than MIN_SCALE_PAIRS pairs or sum(srpe) <= 0.
- `daily_load(activities, fiit, scale, start, end)`: returns [(date, load)] with one entry per calendar
  day from start to end inclusive; a day with nothing on it is 0. An activity counts on
  start_local[:10]; a None load counts as 0. A FiiT row adds srpe*scale only when it is unmatched or
  its matched activity has no load. A matched activity that has a load is counted once, as the Garmin load.
- `ewma(loads, n)`: v_t = v_{t-1} + (load_t - v_{t-1})/n, seeded at 0 on the first day. The window
  starts 365 days before today, or at the first day with any data if that is later. The chart then
  shows the last 180 days.
- Form (TSB) for a day = CTL - ATL of the previous day. The Today tile shows today's TSB, which is
  yesterday's CTL - ATL.
- Ramp = CTL today - CTL 7 days ago. ACWR = mean daily load over the last 7 days (including today)
  divided by the mean over the last 28 days; None if the 28-day mean is 0. ACWR chip: inside 0.8-1.3
  good, 1.3-1.5 warn, above 1.5 bad, below 0.8 no class ("low").
- Monotony = mean / pstdev of the last 7 daily loads; None if pstdev is 0. Strain = 7-day sum x
  monotony; None when monotony is None.
- `summary(...)` returns a dict: ctl, atl, tsb, zone (label, tone), ramp, ramp_tone, acwr, acwr_tone,
  monotony, monotony_tone, strain, scale, scale_pairs, days_of_data.
- `svg_load_chart(series)`: inline SVG in a `figure.chart.card`, the same frame as
  `logic.svg_line_chart` (axes, gridlines, first/last date). It draws CTL as a polyline (class
  `ctl`), ATL as a polyline (class `atl`), and TSB as bars from a zero line, with class
  `tsb fresh|neutral|optimal|high`. TSB has its own y-scale that is symmetric around 0. Each bar gets
  a `<title>` with the date, TSB and zone. Fewer than 2 days gives "Not enough data yet."
- main.py: query `activities(id, start_local, training_load)` from 400 days back, and every `fiit`
  row LEFT JOINed to its activity's training_load. No new tables and no migration.
- Today tiles, each with a one-line "what this means" in `.sub`:
  - Form: the TSB value, a zone chip, and "Fitness X · Fatigue Y". Meaning: "Fitness minus fatigue: negative = building, very negative = consider easing off."
  - Load balance: the ACWR value and its chip. Sub-lines: "Ramp +N/wk" (warn chip above 5), "Monotony N" (warn chip above 2) and "Strain N". Each gets a one-line meaning. Warnings are worded as suggestions ("consider an easier day").
  - When days_of_data < 42, add the muted line "Fitness is still building (N days of data)".
  - When the FiiT scale is the default, show "FiiT scale 1.0 (default, fewer than 3 matched classes)"; otherwise "FiiT scale X from N classes".
- CSS: `.ctl { stroke:var(--acc) }`, `.atl { stroke:var(--warn); stroke-dasharray:4 3 }`, and `.tsb.fresh` = --acc,
  `.neutral` = --muted, `.optimal` = --good, `.high` = --bad, with opacity .7. Works in both light and dark mode.
- Keep the footer.

New service: None (the port stays 8086 and the labels don't change).
New env vars: None
Checks the builder must run:
- cd /home/dan/homelab/.worktrees/fitness-load/tools/fitness && python3 -m unittest discover -s tests
- python3 -m py_compile tools/fitness/app/analysis.py tools/fitness/app/main.py
- scripts/dc.sh /home/dan/homelab/.worktrees/fitness-load/tools/fitness config -q
- Tests needed: a scale fit (3 pairs gives the ratio, 2 pairs gives 1.0); a matched FiiT that is not
  double counted; zero-fill of empty days; ewma on [100,0,0] with n=7 giving 14.29, 12.24, 10.50; TSB
  taking the previous day; ramp; ACWR worked example and the 28-day zero giving None; monotony/strain
  worked example and a constant load giving None; every zone boundary (+5, -10, -30); svg_load_chart
  with empty data and with 3 days.
Review focus:
- FiiT class matched to a Garmin activity with a load -> counted once (the Garmin load), never srpe on top
- No activities at all, or under 28 days of history -> tiles show "–" with no chip and a "not enough data" line; no ZeroDivisionError, no 500
- 7 identical or all-zero load days -> monotony and strain are "–", no crash
- Activity with training_load NULL or start_local NULL -> NULL load counts as 0, NULL date is skipped
- Days with no training -> zero-filled, so ATL decays and the chart has no gaps
Docs: tools/fitness/README.md gets an Analysis section; docs/fitness-analysis-prompt.md marks section 1 as built. No changes to CLAUDE.md, the port table or docs/README.md.

## Manual steps
None beyond the normal deploy (`scripts/deploy-idea.sh fitness-load` rebuilds the image as 0.3.0).

## Review notes
1. /home/dan/homelab/.worktrees/fitness-load/tools/fitness/app/templates/today.html:30-36: when there are fewer than 28 days of history, the Form tile still shows a value and a zone chip. With 1 day of data it shows "-1 Neutral". Only Load balance shows "–" with no chip. One review-focus item reads as "under 28 days, the tiles show –", which this doesn't match. But the plan's own rule ("days_of_data < 42 → Fitness is still building" line) assumes Form is shown early, and that line does appear. If Dan wants Form hidden until there is more history, that is a small follow-up.
2. /home/dan/homelab/.worktrees/fitness-load/tools/fitness/app/analysis.py:200: this is an edge case. Take a FiiT class matched to an activity that has a load but whose `start_local` is NULL, or older than 400 days. That class adds nothing, so its load is lost. It is never double counted, so this is harmless in practice.
3. today.html:472: the scale label is chosen from `scale_pairs < 3`. If there are 3 or more pairs but their total sRPE is 0, `fiit_scale` falls back to 1.0, yet the page says "FiiT scale 1.00 from N classes". The wording is wrong; nothing breaks.
4. /home/dan/homelab/.worktrees/fitness-load/tools/fitness/tests/test_analysis.py:604: the assertion `assertIsNone(sm["monotony"] if sm["monotony"] is None else None)` is always true. Nothing else covers it (the case is handled correctly), but this line tests nothing.

## Declined to judge
- Server timezone used by `date.today()` for "today": the existing pages already work this way; outside the plan.
- Whether the ACWR word "high" covers both amber and red: the chip colour already tells them apart; a style choice.
