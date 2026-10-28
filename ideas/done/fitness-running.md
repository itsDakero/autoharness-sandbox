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

## Plan
Goal: Add HR zones, 80/20, aerobic efficiency, decoupling, effective VO2max, race predictions, endurance gap,
long-run readiness and best efforts to the fitness app (analysis note 3 of 5; notes 1 and 2 are already built).
Kind: change to tools/fitness

Files:
- tools/fitness/app/db.py: SCHEMA_VERSION = 3. Append a third MIGRATIONS entry (leave the old ones as they are):
    activity_zones(activity_id INTEGER NOT NULL, zone INTEGER NOT NULL CHECK(zone BETWEEN 1 AND 5),
      seconds REAL NOT NULL, low_bpm REAL, PRIMARY KEY(activity_id, zone))       -- Garmin's own zones
    activity_hr(activity_id INTEGER NOT NULL, bpm INTEGER NOT NULL, seconds REAL NOT NULL,
      PRIMARY KEY(activity_id, bpm))                                            -- seconds-at-bpm histogram
    best_efforts(activity_id INTEGER NOT NULL, distance TEXT NOT NULL CHECK(distance IN
      ('400m','1k','1mi','5k','10k','half')), seconds REAL NOT NULL,
      source TEXT NOT NULL CHECK(source IN ('details','laps')), PRIMARY KEY(activity_id, distance))
  Add helpers replace_zones, replace_hr_hist and replace_best_efforts, each doing delete-then-insert per activity.
- tools/fitness/app/garmin.py: keep the parsers pure, with no library import.
  - parse_hr_zones(d): takes the list (or a dict holding a list) of {zoneNumber, secsInZone, zoneLowBoundary}.
    Returns [(zone, secs, low)] for zones 1-5 only and drops odd items.
  - parse_samples(d): maps metricDescriptors[].key to metricsIndex, then reads sumDuration (s), sumDistance (m)
    and directHeartRate from each activityDetailMetrics[].metrics. Returns a list of (t, dist, hr|None).
    Samples with no t are dropped. Missing descriptors give [].
  - The wheel is garminconnect 0.3.19, already pinned. Its method names are checked:
    get_activity_hr_in_timezones(id) -> /activity/{id}/hrTimeInZones and
    get_activity_details(id, maxchart=2000, maxpoly=4000). Call details with maxchart=2000, maxpoly=0
    (no polyline).
  - New step _run_details(con, f, api), constant RUN_DETAILS_PER_RUN = 20. It takes running activities
    (type LIKE '%running%') that have no raw row of kind 'details', newest first, up to the limit. For each one
    it calls hrzones and then details through the _Fetcher (2 s gap). It saves the raw data: kind 'hrzones' gets
    the full JSON; kind 'details' gets only {metricDescriptors, activityDetailMetrics} so the DB stays small.
    From those it writes activity_zones, activity_hr (running.hr_histogram) and best_efforts (running.best_efforts
    on the samples). If there are fewer than 2 usable samples it falls back to running.best_efforts_from_laps
    on the laps table, with source 'laps'.
    Failures: if a call returns None, increment sync_state key 'detail_fail:<id>' and stop the step for this run
    (break), so a run of errors never reaches MAX_CONSECUTIVE_ERRORS. At 3 failures, save
    raw('details', id, None) so the activity is skipped from then on, and still write the laps fallback efforts.
  - Call _run_details last in run_sync, after rematch_fiit. Nothing in it may make run_sync fail unless a
    429 or auth error is raised (those keep the behaviour they have now).
- tools/fitness/app/running.py (new, stdlib only): all constants sit at the top. Functions:
  - ZONE_PCT = (0.50, 0.60, 0.70, 0.80, 0.90). zone_bounds(max_hr) returns 5 (low, high) pairs. Below 50%
    counts in no zone.
  - zones_from_hist(hist_rows, max_hr) gives [secs z1..z5]. hr_histogram(samples) skips intervals with dt <= 0
    or dt > GAP_S = 30 and bins by round(hr).
  - default_max_hr(rows) is the highest activities.max_hr in the last 365 days, or None. effective_max_hr(setting,
    rows) uses the setting when it is valid, otherwise that default.
  - share_easy(zone_secs) gives the Z1+Z2 share. EASY_GOOD = 0.75 and EASY_WARN = 0.60 set the tones (80/20 chip,
    last 28 days). weekly_zone_secs(...) covers the last 26 weeks, Monday starts, using logic.week_start.
  - is_easy(avg_hr, z2_low, z3_low). efficiency(distance_m, duration_s, avg_hr) is (m/min)/bpm, only for runs of
    20 min or more. ef_trend compares the mean of the last 28 days with the 28 before (up = good).
  - decoupling(laps) only works for runs of 45 min or more with at least 4 laps that have HR. A lap goes in the
    first half when its time midpoint is before half the total. Each half's EF is duration-weighted, and the
    result is (EF1-EF2)/EF1*100. Tones: < 5 good, 5-10 warn, > 10 bad. Otherwise it returns None.
  - vo2_at_speed(v_m_min) = -4.60 + 0.182258v + 0.000104v^2 (Daniels).
    pct_vo2max(t_min) = 0.8 + 0.1894393e^(-0.012778t) + 0.2989558e^(-0.1932605t).
    vdot(dist_m, secs) = vo2_at_speed / pct_vo2max. predict_time(vdot, dist_m) finds the time by bisection
    between 60 s and 6 h. riegel(t1, d1, d2) = t1*(d2/d1)**1.06.
  - effective_vo2max(dist, secs, avg_hr, max_hr) = vo2_at_speed / ((avg_hr/max_hr - 0.37)/0.64), the Runalyze
    method. It returns None for runs under 20 min, missing HR or avg/max <= 0.5.
    correction_factor(runs) looks at runs of 3 km or more in the last 365 days and takes the one with the
    highest vdot(dist, time). The factor is that vdot divided by the run's effective VO2max, clamped to
    0.8-1.2, and 1.0 when there is no such run.
  - endurance_gap(pb_5k, pb_half) = half PB minus the half that vdot(5k PB) predicts. Tones: <= 300 s good,
    <= 720 s warn, else bad.
  - long_run_readiness(vdot, weekly_km_56d_avg, longest_km_42d)
    = 100*(2/3*min(1, weekly/(0.5*vdot**1.135)) + 1/3*min(1, longest/18)).
    Constants: HALF_WEEKLY_FACTOR = 0.5 and HALF_LONG_KM = 18. Tones: >= 90 good, >= 70 warn.
    Label it "like Runalyze's marathon shape, with our own half targets".
  - best_efforts(samples) works on cumulative (t, dist) with a sliding window and linear interpolation, for
    DISTANCES {400m, 1k, 1mi, 5k, 10k, half}. It skips windows where distance goes backwards and drops any
    effort faster than MIN_PACE_S_PER_KM = 150. best_efforts_from_laps(laps) uses the fastest contiguous span
    of laps that is at least the target distance, with the time scaled to the target.
  - SVG builders, inline only, using the CSS tokens: svg_zone_bars (weekly stacked), svg_zone_strip (one
    run), svg_pace_curve (pace vs distance, last 90 days vs all time).
- tools/fitness/app/main.py:
  - Add a loader load_running(con) that never raises on odd rows. Settings reads max_hr and zone_source.
    zone_source is 'maxhr' (the default; uses activity_hr) or 'garmin' (uses activity_zones). The easy-run
    bounds for 'garmin' come from that activity's own zone 2 and zone 3 low_bpm.
  - /trends: add the 80/20 chip and four charts: weekly zones, EF of easy runs (180 days), corrected effective
    VO2max per run (180 days), pace curve.
  - /runs/{id}: add the zone strip, decoupling chip, effective VO2max tile (with Garmin's daily.vo2max on the
    latest date on or before the run as the sub line) and that run's best efforts.
  - /pbs: under each PB show the Riegel and VDOT predictions from the best 5k best_effort in the last 90 days.
    If there is none, show "no 5k effort in 90 days". Add an endurance gap tile, a long-run readiness tile
    (VDOT from that effort, falling back to the 5k PB) and a current effective VO2max tile (mean of the last
    30 days) next to Garmin's VO2max.
  - POST /settings: add the optional fields max_hr (blank = auto, otherwise an integer 100-230) and zone_source
    (maxhr|garmin), defaulting to the stored values. Validate all fields before writing any. Bad input gives
    a 400 and nothing is written.
- tools/fitness/app/templates/{trends,run,pbs,settings}.html: the new tiles, chips and charts in the 2026-10-17
  style. Each new number gets a one-line "what this means". Warnings are worded as suggestions. Keep the footer.
  Settings shows the auto max HR value in the help text.
- tools/fitness/tests/test_running.py (new): one worked example per formula:
  - vdot(5000, 1197) is 50.0 +-0.3, and predict_time(50, 21097.5) is 5495 +-30 s (Daniels' table).
  - riegel(1500, 5000, 10000) is about 3127.6.
  - vdot(5000, 1503) gives a half about 19 min faster than 8090 s.
  - Also cover: zone bounds at max 190, share_easy, decoupling (with the < 4 laps and < 45 min cases giving
    None), effective_vo2max None at avg/max <= 0.5, correction clamp, readiness, best_efforts on a synthetic
    constant-pace run plus one GPS spike, the laps fallback, and hr_histogram gap skipping.
- tools/fitness/tests/test_parse.py: add tests for parse_hr_zones and parse_samples, including empty, missing
  descriptors and None input.
- tools/fitness/tests/test_db.py: the expected schema version becomes 3. Add a test that the three new tables
  exist.
- tools/fitness/compose.yaml: image homelab/fitness:0.4.0 -> 0.5.0.
- tools/fitness/README.md: add a "### Running" subsection under Analysis with the formulas, constants and
  sources. Update the Schema line (new tables; settings max_hr and zone_source). Under Sync behaviour, add the
  per-run details backfill (20 runs per sync, 2 calls each, skipped after 3 failures, laps fallback).

New service: none
New env vars: None
Checks the builder must run:
- cd .worktrees/fitness-running/tools/fitness && python3 -m unittest discover -s tests
- python3 -m py_compile app/*.py
- scripts/dc.sh .worktrees/fitness-running/tools/fitness config -q
- Render each changed template with jinja2, if it is installed locally. If not, the unit tests have to cover
  the loaders.

Review focus:
- A details or hrzones call fails or 404s, for example on old activities -> the sync still finishes, last_ok is
  set and there is no Kuma stale alert. The activity is retried on later runs, skipped after 3 failures with
  laps-based efforts, and the backfill goes on to the other runs.
- No HR channel, missing metricDescriptors, a sample list that is empty or None, or a GPS spike -> the parsers
  return empty data, the pages show "–", and no effort is faster than 2:30/km.
- No max HR known (no activities, or a corrupt setting) -> the pages say "set max HR in Settings" with no 500.
  VO2max and decoupling return None rather than dividing by zero.
- A Settings POST with only sleep_need_h (the old form), max_hr "abc" or 300, or zone_source "x" -> the old
  form still saves. Invalid values give a 400 and nothing is written, including sleep need.
- Switching zone_source -> the zones are recomputed on page load from the stored tables, with no refetch from
  Garmin.

Docs: tools/fitness/README.md (Running analysis, schema, sync). No change to CLAUDE.md or docs/README.md
(the port, layout and docs index stay the same).

## Manual steps
Deploy as usual (deploy-idea.sh builds homelab/fitness:0.5.0). Optionally set max HR and the zone source on
/settings. The per-run backfill fills in over about 10 hours of syncs, at 20 runs per 30 minutes.

## Review notes
1. `/home/dan/homelab/.worktrees/fitness-running/tools/fitness/app/main.py` `load_running`: if `running.load` hits any odd row, it returns None and the whole Running section disappears from Trends and PBs. Dashes would be friendlier. I couldn't make it fail with NULL start_local, distance or HR, or with corrupt settings, so this is a fallback that shouldn't trigger.
2. `/home/dan/homelab/.worktrees/fitness-running/tools/fitness/app/garmin.py` `_run_details`: a newest run that keeps failing blocks the backfill for up to 3 syncs (about 1.5 h) before the other runs get their turn. The plan asks for exactly this (`break`). The `detail_fail:<id>` keys are never cleared, which does no harm.
3. `/home/dan/homelab/.worktrees/fitness-running/tools/fitness/app/main.py` `settings_save`: a POST with no fields at all now redirects to `saved=1` and writes nothing, where before it gave a 400. This is harmless.
4. `/home/dan/homelab/.worktrees/fitness-running/tools/fitness/app/templates/trends.html`: the easy-run efficiency tile shows only the % change between the two 28-day windows, not the EF value itself. The EF value is on the 180-day chart.
5. With zone_source=garmin, an easy-run EF point needs Garmin's own zone 2 and zone 3 `low_bpm` for that run. If Garmin leaves those out, the EF chart stays empty with no explanation.

## Declined to judge
- Paused time inside `sumDuration` makes best efforts slower, never faster: it can't produce a wrong fast effort, and the plan doesn't cover pauses.
- The VDOT, Riegel and readiness constants: they are the plan's formulas, and the worked-example tests pass.
- Unit handling on /pbs (`?unit` query param): it follows the existing page convention, which is outside this plan.
- Size of the stored `details` raw (up to 2000 samples × 3 metrics per run): the plan accepts this and trims it to descriptors plus metrics.
- None
