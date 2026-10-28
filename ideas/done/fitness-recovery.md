# Fitness recovery: normal ranges, recovery score, sleep debt, illness warning (fitness analysis 2 of 5)

## Problem
Today compares last night with a 7-day median only. Athlytic, Oura and Whoop show a personal
"normal range" and a recovery score built from several signals. Phase 1's real problem was that Dan
felt ill while his numbers looked fine; an early warning from his own patterns needs these ranges.

## Proposal
- **Normal range bands** for HRV and resting HR: 60-day mean ± 1 SD. Plot the 7-day rolling average
  against the band on Trends. The Today tile chip says "in range", "below" or "above".
- **Own recovery score 0–100** (Whoop style), next to Garmin's readiness: HRV z-score, RHR z-score
  (inverted), sleep vs need. Check-in overrides: ill = capped at 33; sore legs / stressed / slept
  badly = −10 each. Show the parts, not only the total.
- **Sleep debt**: 7-day sum of (need − actual); need defaults to 8 h. **Sleep consistency**: SD of
  bedtime and wake time over 14 days (sleep start/end from the raw sleep JSON in the `raw` table).
- **Strain vs recovery**: daily chart of load (from note 1) vs recovery score; flag high load on a
  red recovery day.
- **Illness early warning**: flag when resting HR is ≥ 3 bpm above its band and HRV is below its band
  for 2 nights in a row, or one of those plus a "slept badly"/"stressed" check-in. Warn banner on
  Today: "your numbers look like the start of illness: consider an easy day".
- After 60 days of check-ins, show on Trends how often a flag came 1–3 days before an "ill" check-in.
- A small **Settings** page (new `settings` table): sleep need.

## Notes
- Needs note 1 (`fitness-load`) deployed first, for the strain vs recovery chart.

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
Goal: Add normal-range bands, a recovery score, sleep debt and consistency, a strain vs recovery chart, an illness warning and a sleep-need setting to the fitness app (analysis note 2 of 5).
Kind: change to tools/fitness
Prerequisite met: fitness-load is merged and `homelab/fitness:0.3.0` is running.

Files:
- tools/fitness/app/analysis.py: new recovery section. All constants go at the top (listed below).
- tools/fitness/app/db.py: append migration 2, `CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);`. Set SCHEMA_VERSION = 2. Add `get_setting(con, key, default=None)` and `set_setting(con, key, value)`, which commits.
- tools/fitness/app/main.py:
  - New `load_recovery(con, load_series)`. It reads:
    - `daily` from today-250 days;
    - `checkins` from the same date;
    - raw `kind='sleep'` rows with key >= today-13;
    - the `sleep_need_h` setting.
  - It calls `analysis.recovery(...)`. Call `load_analysis` once per request and pass its series in.
  - Today and Trends get the new context.
  - New routes `GET /settings` and `POST /settings`.
- tools/fitness/app/templates/today.html: changes listed under Today below.
- tools/fitness/app/templates/trends.html: legend for the band (shaded = normal range, line = 7-day average) and for the strain/recovery marks, plus the warning-accuracy card.
- tools/fitness/app/templates/settings.html: new page. One number input `sleep_need_h` (step 0.25, 4 to 12), Save button, "Saved." notice, one-line explanation.
- tools/fitness/app/templates/base.html: add a "Settings" tab (`/settings`) at the end of the nav.
- tools/fitness/app/static/style.css: `.band` fill (`--acc-soft`), `.ravg` line (`--acc`), `.rec` line, `.loadbar` (`--muted`), `.flag` (`--bad`). Use the existing tokens only.
- tools/fitness/compose.yaml: image `homelab/fitness:0.4.0`.
- tools/fitness/tests/test_analysis.py: one worked-example test per formula below, plus the edge cases under Review focus.
- tools/fitness/tests/test_db.py: the migration test expects version 2. Add a settings get/set round-trip test.
- tools/fitness/README.md: a "Recovery" subsection under Analysis with the formulas, thresholds and edge rules. Add `settings(key)` to Schema.
- docs/fitness-analysis-prompt.md: mark sections 2 and 5 as built (one line each).

Formulas (analysis.py; constants in caps):
- Band, `band(values_by_date, d)`:
  - Built from the BAND_DAYS=60 days before d (d itself excluded): mean ± pstdev.
  - None when there are fewer than MIN_BAND_VALUES=14 values or the SD is 0.
  - Used for hrv_avg and rhr.
- Position, `band_pos(v, band)`: "below" / "in range" / "above"; None when v or the band is missing.
  - Chip tones: in range = good.
  - HRV: below = warn, above = good.
  - RHR: above = warn, below = good.
- 7-day rolling average for d: mean of the values present in d-6..d. A gap when fewer than ROLL_MIN=3 are present.
- Recovery score for day d:
  - Part scores, each clamped 0..100:
    - z = (v - mean) / sd against the band for d.
    - HRV part = 50 + 25*z_hrv.
    - RHR part = 50 - 25*z_rhr.
    - Sleep part = 100 * sleep_s / need_s.
  - Weights W_HRV=0.4, W_RHR=0.3, W_SLEEP=0.3. When a part is missing, the remaining weights are renormalised. All parts missing gives None.
  - Check-in adjustment: -10 (ADJ_FLAG) for each of sore_legs, stressed, slept_badly.
  - Illness cap: if ill_neck or ill_chest, min(score, 33) (ILL_CAP).
  - Clamp 0..100, round to an int.
  - Bands: >= 67 "Green" good; 34-66 "Yellow" warn; <= 33 "Red" bad.
  - Return the parts (value, z, part score, weight) and the adjustments too.
  - Worked test: z_hrv=+1 -> 75, z_rhr=0 -> 50, 7 h of an 8 h need -> 87.5. 30+15+26.25 = 71.25, then -10 for stressed = 61 Yellow. The same day with ill_chest -> 33 Red.
- Sleep debt:
  - Sum of (need_s - sleep_s) over the nights present in today-6..today.
  - None when fewer than 4 nights (DEBT_MIN_NIGHTS) are present. The total is floored at 0.
  - Tone: < 2 h good, 2-5 h warn, > 5 h bad.
- Consistency:
  - Data: raw sleep JSON `dailySleepDTO.sleepStartTimestampLocal` and `sleepEndTimestampLocal`, epoch ms, already shifted to local time. Read them with `datetime.fromtimestamp(ms/1000, timezone.utc)`, then take hour and minute.
  - Bedtime = minutes from noon, `(h*60+m-720) % 1440`, so a bedtime either side of midnight doesn't wrap.
  - Wake = minutes from midnight.
  - Value: pstdev of each over the last 14 nights. None when fewer than 5 nights are valid.
  - Tone: <= 30 min good, <= 60 warn, else bad.
- High load: day index >= 28 in the load series, load > 0, and load >= HIGH_LOAD_RATIO=1.5 × the CTL of the day before.
- Red flag: a high-load day whose recovery is Red.
- Illness signals:
  - rhr_high(d) = rhr >= band mean + sd + RHR_MARGIN (3 bpm).
  - hrv_low(d) = hrv < band mean - sd.
  - both(d) = rhr_high and hrv_low.
- Warning on d when both(d) and both(d-1) hold, or both(d) holds and d's check-in has slept_badly or stressed.
  - The note's "one of those" is read as one night with both signals.
  - Missing data never counts as a signal.
- Warning accuracy:
  - Shown when checkins >= ACC_MIN_CHECKINS=60.
  - Illness starts = ill check-in days whose previous day is not ill. A hit = a warning on any of the 1-3 days before.
  - Show "X of Y illness starts had a warning 1-3 days before".
  - Show "Z warnings with no illness in the next 3 days".
  - Below 60: "Shows after 60 check-ins (now N)".
- History: compute recovery and warnings for each of the last 180 days, each day against its own 60-day band.
- `recovery()` returns a dict: today's score with its parts, the bands, positions, sleep debt, consistency (SD plus mean bedtime/wake as HH:MM), the warning today, and series for the charts plus the accuracy stats.

Charts:
- `svg_band_chart(points, title, unit, markers)`: shaded band polygon with breaks where the band is None, the 7-day average line, and the existing check-in markers. It replaces the plain RHR and HRV charts on Trends.
- `svg_strain_recovery_chart(load_series, rec_series)`, 90 days:
  - load bars on their own scale;
  - the recovery line on a 0-100 scale, with dashed lines at 33 and 67;
  - red-flag days get a `.flag` dot with a `<title>`.
- Fewer than 2 points -> "Not enough data yet."

Today:
- Banner when the warning is on: "Your numbers look like the start of illness: consider an easy day." (warn class)
- A "Recovery" tile next to the readiness hero:
  - the score, a Green/Yellow/Red chip, and one sub line per part plus each adjustment;
  - the what-this-means line: "Your own score from HRV and resting HR against your normal range, and sleep vs need; check-in flags lower it.";
  - when today's load is high and recovery is Red: chip "high load on a red day: consider an easier session".
- A band chip on the HRV and Resting HR tiles, next to the existing d7 chip. "learning (N/14)" when the band is None.
- Tiles for Sleep debt and Sleep consistency (bedtime ± min, wake ± min), each with a one-line meaning.

Settings:
- POST accepts a float from 4 to 12.
- Anything else -> the error.html page with status 400; the stored value is unchanged.
- A corrupt stored value -> SLEEP_NEED_DEFAULT_H=8.0.

New service: None
New env vars: None

Checks the builder must run:
- cd /home/dan/homelab/.worktrees/fitness-recovery/tools/fitness && python3 -m unittest discover -s tests
- python3 -m py_compile on app/*.py
- scripts/dc.sh /home/dan/homelab/.worktrees/fitness-recovery/tools/fitness config -q

Review focus:
- Under 14 days of HRV/RHR, or a flat SD -> no band, "learning" chip, a part is missing or the score is "-", no warning, no ZeroDivisionError.
- Raw sleep JSON missing, invalid, or with null timestamps -> that night is skipped; under 5 nights shows "-".
- Bedtimes of 23:30 and 00:30 -> SD of about 30 min, not about 11 h (noon-anchored minutes, tested).
- Today's row missing or no sleep yet -> no banner, no false Red, score from the parts that exist.
- The stored sleep-need setting is bad, or POST sends "", "abc" or 20 -> default 8 h, or a 400 with no write; pages never 500.

Docs: tools/fitness/README.md (Recovery subsection, settings table, Settings page) and docs/fitness-analysis-prompt.md (sections 2 and 5 built). No changes to CLAUDE.md, the port table or docs/README.md.

## Manual steps
deploy-idea.sh fitness-recovery. Migration 2 runs at startup. Sleep need can be changed at http://192.168.0.210:8086/settings.

## Review notes
1. The output of `scripts/idea.sh diff fitness-recovery` looks like it reverts the LeafGreen cards work: `games/leafgreen/*` and `scripts/card-prices.py` deleted, the cron line removed, the CLAUDE.md scripts entry removed, `ideas/done/pokemon-card-collector.md` moved back. It doesn't. That diff compares two points against main, and main gained a63d98c (the pokemon-card-collector merge) after this branch was cut at d0d7f0a. `git diff --stat main...idea/fitness-recovery` and the worktree's `git status` show only `tools/fitness/*`, `docs/fitness-analysis-prompt.md` and the idea note. The merge should be clean. Worth a glance at deploy time all the same.
2. In tools/fitness/app/main.py:211, `today()` passes `rec_band` to the template, but today.html never uses it. It is dead context.
3. In tools/fitness/app/analysis.py `recovery()`, an HRV or resting HR value of 0 counts as real data, because `logic.num(0)` is 0.0 and not None. Sleep debt drops 0 s nights, but the bands don't drop 0 values. Garmin rarely sends 0 for these, so this is minor.
4. Warning accuracy counts check-ins from the 250 days that `load_recovery` reads, not all of them. That is fine for the 60 check-in threshold.
5. tools/fitness/tests/test_analysis.py `test_consistency_across_midnight` has a leftover `if i % 2 or True`. It is harmless because only the hour and minute are used.

## Declined to judge
- Live FastAPI behaviour of `/settings`, the 303 redirect and the 400 page: fastapi isn't installed on the host. I checked them by reading the code and rendering the templates with Jinja2. `render()` takes `status_code`, and error.html uses `message`.
- Whether 25 points per SD and the 0.4/0.3/0.3 weights give a sensible score: the plan fixes these values.
