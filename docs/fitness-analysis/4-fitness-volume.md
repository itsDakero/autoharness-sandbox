# Fitness volume: calendar heatmap, weekly summary, streaks (fitness analysis 4 of 5)

## Problem
Trends has one weekly-distance line. Strava and intervals.icu show a year at a glance and simple
habit numbers that keep you consistent.

## Proposal
- **Calendar heatmap** (GitHub style) of daily load (from note 1) for 12 months, on Trends.
- **Weekly summary table** on Runs: distance, time, runs, FiiT classes, long-run share of weekly
  distance (warn above 35%), and a streak of weeks with ≥ 2 runs.
- **Cadence trend** for easy runs (chart card on Trends).

## Notes
- Needs note 1 (`fitness-load`) for daily load. No new tables.

## Shared rules (all fitness analysis notes)
- Background and the full list of analyses: `docs/fitness-analysis-prompt.md`.
- Maths is stdlib only, in `tools/fitness/app/logic.py` or a new `app/analysis.py`. Each formula gets a
  unit test with a worked example. Thresholds live in one place as constants.
- Look: same as the 2026-10-17 redesign. Tiles, chips coloured with `--good`/`--warn`/`--bad`, chart cards.
  Charts are inline SVG, no CDN. Each new number gets a one-line "what this means".
- Schema: append migrations at the end of `MIGRATIONS` in `app/db.py`; never edit an old one.
- Bump the image tag in `tools/fitness/compose.yaml` (minor version).
- Not medical advice: keep the footer; word warnings as suggestions.
