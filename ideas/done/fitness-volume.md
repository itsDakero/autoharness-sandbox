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

## Plan
Goal: Fitness 0.6.0 adds a 12-month daily-load heatmap and an easy-run cadence chart on Trends, and a 12-week summary table with long-run share and a 2-runs-a-week streak on Runs (fitness analysis 4 of 5).
Kind: change to tools/fitness (no schema change, no new tables, no migration)
Files:
- tools/fitness/app/analysis.py: new constants at the top, under a `# volume` comment: `HEATMAP_DAYS = 371` (53 weeks), `SUMMARY_WEEKS = 12`, `LONG_SHARE_WARN = 0.35`, `STREAK_MIN_RUNS = 2`, `LONG_SHARE_MIN_RUNS = 2`. New functions:
  - `heat_levels(loads)`: returns the 3 cut points (25th/50th/75th percentile) of the non-zero loads. Load 0 = level 0; level 1-4 by the cut points; no non-zero loads gives all level 0.
  - `svg_heatmap(series, today)`: `figure.chart.card`, "Daily load, last 12 months". 53 Monday-first columns ending in the week of `today`, 7 rows. Each cell is a `<rect>` with a `<title>YYYY-MM-DD: load N</title>` tooltip. Level 0 is `var(--line)`, levels 1-4 are `var(--acc)` at opacity .3/.5/.75/1. Days before the series starts and days after today get no cell. Month initials along the top. Inline 4-step legend. Fewer than 2 points: "Not enough data yet." like `svg_load_chart`.
  - `weekly_summary(runs, fiit, today, weeks=SUMMARY_WEEKS)`: `runs` = dicts (start_local, distance_m, duration_s), `fiit` = dicts (date). Returns the newest week first, with the current week included, as dicts week, dist_m, time_s, runs, fiit, long_m, long_share (longest run / week distance; None if runs < LONG_SHARE_MIN_RUNS or dist is 0), long_tone ("warn" if share > LONG_SHARE_WARN else "").
  - `run_streak(runs, today)`: the number of consecutive weeks with at least STREAK_MIN_RUNS runs, counting back from last week. The current week adds 1 if it already has 2 or more runs; if it has fewer, it neither counts nor breaks the streak. Use `logic.week_start` for week keys.
- tools/fitness/app/running.py: add `cadence` to the `_runs` SELECT. In `load()`, in the same loop and condition as `ef_pts` (easy run, within EF_DAYS), collect `(date, cadence)` when 120 <= cadence <= 230 spm. New constant `CADENCE_RANGE = (120, 230)` at the top. Apply `_mean_by_date` and return `"cadence_points"` in the dict.
- tools/fitness/app/main.py:
  - `/trends`: append `analysis.svg_heatmap(load_series, date.today())` as the first chart. If `rn`, append `logic.svg_line_chart(rn["cadence_points"], "Cadence of easy runs (steps/min)")`.
  - `/runs`: separate queries for the last 12 weeks of runs (`type LIKE '%running%' AND start_local >= <Monday 11 weeks before this week>`) and fiit rows (`date >= same`). Wrap `weekly_summary` and `run_streak` in try/except with `log.exception`, and pass `summary=[]`/`streak=None` on failure. Pass summary, streak and unit.
- tools/fitness/app/templates/runs.html:
  - New "Streak" tile: N weeks, sub "weeks in a row with 2+ runs".
  - "Last 12 weeks" table, placed above the runs list: Week (Mon date), Dist (in unit), Time, Runs, FiiT, Long run share (a `chip warn` above 35%, "–" when None).
  - A one-line `.what` under the table: "Long run share above 35% of the week's distance raises injury risk; consider spreading the distance. A suggestion, not medical advice."
- tools/fitness/app/templates/trends.html: legend line for the heatmap ("darker = higher daily load; grey = rest day") and a one-line "what this means" for cadence ("Steps per minute on easy runs; a slow rise often comes with better form. No target is implied.").
- tools/fitness/app/static/style.css: only what the heatmap needs (e.g. `.heat rect { rx:2 }`), using existing vars.
- tools/fitness/tests/test_analysis.py: worked-example tests:
  - heat_levels: all zeros, and loads 10/20/30/40.
  - weekly_summary: a week of 3 runs 5/5/10 km gives share 0.5 and warn; 1 run gives None; a FiiT count; an empty week gives zeros.
  - run_streak: a broken streak; the current week with 1 run doesn't break it; no runs gives 0.
  - svg_heatmap: empty series and a 400-day series render without error, with no more than 371 rects.
- tools/fitness/tests/test_running.py: cadence outside 120-230 is dropped; None cadence is skipped.
- tools/fitness/compose.yaml: image `homelab/fitness:0.5.0` -> `homelab/fitness:0.6.0`.
- tools/fitness/README.md: a "### Volume" subsection (heatmap levels = quartiles of non-zero load, 53 weeks; weekly table and long-run share rule; streak rule; cadence = easy runs, 120-230 spm, 180 days).
New service (if any): None
New env vars: None
Checks the builder must run:
- `cd <worktree>/tools/fitness && python3 -m unittest discover -s tests`
- `python3 -m py_compile app/*.py`
- `scripts/dc.sh <worktree>/tools/fitness config -q`
- Render runs.html and trends.html with jinja2 for empty data (no runs, no fiit, rn=None) and with sample data.
Review focus:
- No runs or no load data at all -> Runs and Trends render with "–"/"Not enough data yet", no 500.
- A week with a single run -> long-run share "–", not a 100% warn chip.
- No max HR set (rn has no easy runs) -> the cadence chart shows an empty-state card, not an error.
- Cadence 0/None or a stride-per-minute value (~85) from Garmin -> dropped by the 120-230 filter, not plotted.
- Current week with 0-1 runs on a Monday -> streak still shows the run of completed weeks, not 0.
Docs: tools/fitness/README.md Volume subsection only. No CLAUDE.md or port changes.

## Manual steps
None (deploy-idea.sh builds and starts 0.6.0).

## Review notes
1. The build goes beyond the plan in two places, and both look justified. In /home/dan/homelab/.worktrees/fitness-volume/tools/fitness/app/garmin.py:150 the builder now reads Garmin's `averageRunningCadenceInStepsPerMinute` and falls back to the old `averageRunningCadenceInSteps`. In running.py `_runs` (around lines 600-606), when an activity has no cadence the query takes a duration-weighted average of its laps' cadence. The old key was probably always empty, which would have left the cadence chart blank. Both are tested (test_cadence_filter, test_cadence_from_laps), but neither was in the plan, so Dan should know about them.
2. trends.html:18-19: the heatmap and cadence "what this means" lines sit in the top legend block and show even when `rn` is None, when there is no cadence chart. Moving the cadence line inside `{% if rn %}` would be tidier.
3. The streak query in main.py (`_streak_runs`) only looks back 60 weeks, so a streak longer than about 60 weeks stops counting there. This is harmless in practice, but there is no comment saying the cap is deliberate.
4. runs.html: the weekly table always has 12 rows, so with no runs at all it shows 12 rows of 0 and "–" rather than an empty-state line. It doesn't crash, and it matches the "–" wording in the review focus.
5. The heatmap gets `load_series` from `compute`, which covers at most 365 days. The first week (up to 6 days of the 53-week grid) has no cells, as the plan intends for days before the data starts.

## Declined to judge
- How the week label is formatted (an ISO Monday date such as 2026-10-19 rather than "19 Oct"): the plan only says "Week (Mon date)".
- Whether Garmin's lap `averageRunCadence` is in steps or strides per minute: the 120-230 filter drops stride values either way.
- Whether a re-sync rewrites cadence on activities already in the DB: the lap fallback covers old rows, and re-syncing wasn't part of this plan.
