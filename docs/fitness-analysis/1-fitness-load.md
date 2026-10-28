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
