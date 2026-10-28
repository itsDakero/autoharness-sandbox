# Fitness running: HR zones, efficiency, VO2max per run, race predictions (fitness analysis 3 of 5)

## Problem
Runs show averages only. Runalyze and intervals.icu show time in HR zones, aerobic efficiency,
an effective VO2max per run and race predictions. Dan's half is ~20 min slower than his 5k
predicts, so endurance is the gap; the app should measure it.

## Proposal
- **HR zones**: 5 zones from max HR (Settings; default the highest `max_hr` in 12 months) or
  Garmin's zones. Time in zone per run from `get_activity_hr_in_timezones`, stored in a new
  `activity_zones` table (raw JSON kept as usual). Weekly stacked bar on Trends; **80/20 check**:
  share of time in Z1–Z2.
- **Aerobic efficiency**: pace ÷ HR for easy runs (avg HR in Z2), 180-day trend.
  **Decoupling** from laps: pace:HR of the second half vs the first; < 5% = good aerobic base
  (runs ≥ 45 min only). Shown on run detail.
- **Effective VO2max per run** (Runalyze method: from pace and %HRmax), with a correction factor
  from the best recent race. Compare with Garmin's VO2max.
- **Race predictions**: Riegel (`T2 = T1 × (D2/D1)^1.06`) and VDOT from the best recent 5k effort,
  for 5k, 10k and half, next to each PB. An **endurance gap** line (half PB vs the half the 5k
  predicts) and a long-run readiness % like Runalyze's marathon shape.
- **Best efforts**: fastest 1 km / 1 mi / 5k inside any run, from `get_activity_details`
  (laps as fallback), in a new `best_efforts` table. Pace-duration curve: last 90 days vs all time.
- Settings: max HR, zone source (needs the Settings page from note 2; create it if missing).

## Notes
- New Garmin calls: check the method names in the pinned `garminconnect` wheel first. Rate-limit
  like the backfill: 2 s gap, at most 20 activities per sync run, resumable.
- Independent of notes 1 and 2, but build it after them so the migrations stay in order.

## Shared rules (all fitness analysis notes)
- Background and the full list of analyses: `docs/fitness-analysis-prompt.md`.
- Maths is stdlib only, in `tools/fitness/app/logic.py` or a new `app/analysis.py`. Each formula gets a
  unit test with a worked example. Thresholds live in one place as constants.
- Look: same as the 2026-10-17 redesign. Tiles, chips coloured with `--good`/`--warn`/`--bad`, chart cards.
  Charts are inline SVG, no CDN. Each new number gets a one-line "what this means".
- Schema: append migrations at the end of `MIGRATIONS` in `app/db.py`; never edit an old one.
- Bump the image tag in `tools/fitness/compose.yaml` (minor version).
- Not medical advice: keep the footer; word warnings as suggestions.
