# Fitness (tools/fitness)

Garmin stats, a morning check-in and a FiiT log. Phase 1 of a running coach. Port 8086, admin tile, no login
(anyone on the LAN or tailnet can open it). Not medical advice; your own data only.

- Code: FastAPI + SQLite, server-rendered, no CDN, charts are inline SVG. `app/garmin.py` is the only module that
  imports `garminconnect`; `app/logic.py` and `app/db.py` are stdlib only.
- Data: `/srv/homelab/fitness/` (`fitness.db`, `garmin/garmin_tokens.json` 0600 in a 0700 dir). Backed up by restic
  and B2, so the token is in the backups too.
- Env: `GARMIN_EMAIL`, `GARMIN_PASSWORD` (env file). Empty = the app runs, the banner says "not configured",
  no login is attempted, `/healthz` is 200 and `/healthz/sync` is 503.

## First run
1. `mkdir -p /srv/homelab/fitness` as dan (the container runs as uid 1000; Docker would create it as root).
2. Fill in `GARMIN_EMAIL`/`GARMIN_PASSWORD`, then `scripts/dc.sh tools/fitness up -d --build`
   (or `scripts/deploy-idea.sh garmin-fitness-dashboard`).
3. The first sync starts ~20 s after boot, then every 30 min. "Sync now" is on the Today page.
4. Backfill: 730 days, newest first, 30 days of daily metrics per run (2 s between Garmin calls), activities in
   90-day chunks, laps for at most 20 activities per run. About a day in total. Resumable (`sync_state`
   `backfill_cursor`, `act_cursor`); re-fetches are upserts.

## Sync behaviour and failures
- Tokens are reused. A credential login only happens when there is no token file, or Garmin rejects it, and
  at most once per 6 h (`last_login_attempt`).
- 429 (`GarminConnectTooManyRequestsError`): `backoff_until` = now + 24 h, shown in the banner. No retries.
- Other errors go to `last_error` (shown in the banner). One failed run does not page: `/healthz/sync` (Kuma
  monitor `fitness-sync`) turns 503 only when `last_ok` is over 3 h old.
- A missing field (no HRV, no scales data, no laps) is stored as NULL and shown as "–". 5 fetch errors in a
  row abort the run.
- Every Garmin response is kept in the `raw` table, so later phases can re-extract without re-fetching.
- Per-run details (last step of a sync): up to 20 running activities per sync, newest first, that have no
  `details` raw row. Two calls each (`get_activity_hr_in_timezones`, `get_activity_details` with no polyline),
  2 s apart, so the backlog fills in over about 10 hours of syncs. A failed call is counted in
  `sync_state` `detail_fail:<id>` and ends the step for that run (so errors never reach the 5-in-a-row abort and
  the sync still sets `last_ok`); the activity is retried next sync. After 3 failures it is skipped for good
  (`details` raw row = null) and its best efforts come from the laps table. Only 429 and auth errors still
  fail the sync. `details` raw keeps just the metric descriptors and samples.

## MFA
The account has no two-step verification today. If Garmin asks for a code, the banner says so; enter it at
`http://192.168.0.210:8086/garmin/mfa`. Wrong code: it can be retried (0.3.19 keeps the pending login). If the
login state is lost, press Sync now to request a new code. A pending MFA login is lost on a container restart.

## Re-login after Garmin breaks
1. `rm /srv/homelab/fitness/garmin/garmin_tokens.json` (only if the tokens are rejected for good).
2. Wait for the 6 h credential-login limit, or reset it:
   `sqlite3 /srv/homelab/fitness/fitness.db "update sync_state set value=0 where key in ('last_login_attempt','backoff_until')"`,
   then restart the container and press Sync now.
Do this rarely: fresh logins are what Garmin rate-limits.

## Bumping the library
`garminconnect` is pinned in `requirements.txt` (0.3.19 checked on 2026-10-16: it needs Python >= 3.12 and
`curl_cffi`). Releases are frequent and Garmin changes its API. Bump deliberately, rebuild, and check the Today page.
Signatures verified in the 0.3.19 wheel: `Garmin(email, password, return_on_mfa=...)`, `login(tokenstore)` ->
`("needs_mfa", _)` or `(None, None)`, `resume_login(client_state, mfa_code)`, `client.dump(path)`. Methods used:
`get_user_summary`, `get_sleep_data`, `get_hrv_data`, `get_training_readiness`, `get_training_status`,
`get_max_metrics_range`, `get_body_composition`, `get_activities_by_date`, `get_activity_splits`,
`get_personal_record`. Response shapes were not verified against a live account: parsers in `garmin.py` are
tolerant and the raw JSON is in the `raw` table, so a wrong field name shows as "–", not a crash.
Differences from the plan: PBs are mapped by Garmin's running typeIds (3 = 5k, 4 = 10k, 5 = half) without
calling `get_personal_record_types`; resting HR, Body Battery and stress come from `get_user_summary`.

## Analysis (`app/analysis.py`, stdlib only, computed on page load, no tables)
- Daily load: Garmin `training_load` per activity on `start_local[:10]`, plus FiiT `srpe` x scale. A FiiT class
  matched to an activity that has a load counts once (the Garmin load). NULL load = 0; NULL date = skipped; empty
  days = 0. The scale is sum(load)/sum(srpe) over matched classes, 1.0 with fewer than 3 pairs.
- Fitness (CTL) = 42-day EWMA, fatigue (ATL) = 7-day, `v = v_prev + (load - v_prev)/n`, seeded at 0, from 365 days
  back (or the first day with data). Form (TSB) of a day = CTL - ATL of the day before. Chart shows 180 days.
- Form zones: fresh > +5, neutral -10..+5, optimal -30..-10, high risk < -30.
- Ramp = CTL today - CTL 7 days ago (warn > +5/week). ACWR = 7-day mean / 28-day mean (0.8-1.3 green, 1.3-1.5
  amber, > 1.5 red, < 0.8 "low"); needs 28 days and a non-zero mean.
- Monotony = mean / SD of the last 7 days (warn > 2); strain = 7-day sum x monotony. Both "-" when load is flat.
- Edge rules: no data or too little history shows "-" and a "not enough data" line, never an error.
  Thresholds are constants at the top of `analysis.py`. Not medical advice.

### Recovery
- Band: mean +- population SD of the 60 days before the day (the day itself excluded), for HRV and resting HR.
  No band under 14 values or a flat SD (chip "learning (N/14)"). 7-day rolling average = mean of values in
  d-6..d, a gap under 3 values. Chip tones: in range good; HRV below / RHR above = warn; the other side good.
- Recovery score 0-100: HRV part 50 + 25 z, RHR part 50 - 25 z, sleep part 100 x sleep / need (each clamped
  0-100); weights 0.4 / 0.3 / 0.3, renormalised over the parts that exist; none = "-". Check-in: -10 for each of
  sore legs, stressed, slept badly; ill (neck or chest) caps at 33. Green >= 67, Yellow 34-66, Red <= 33.
- Sleep debt: sum of (need - sleep) over nights in the last 7 days, floored at 0, "-" under 4 nights (a night of
  0 s counts as missing). Good < 2 h, warn 2-5 h, bad > 5 h. Need comes from Settings (default 8 h).
- Sleep consistency: SD of bedtime (minutes from noon, so 23:30 vs 00:30 = 30 min SD) and wake time over 14 nights,
  from `dailySleepDTO.sleepStartTimestampLocal` / `sleepEndTimestampLocal` in the raw sleep JSON. Nights with
  missing or invalid JSON are skipped; "-" under 5 nights. Good <= 30 min, warn <= 60 min, else bad.
- High load: day index >= 28, load > 0 and >= 1.5 x the previous day's CTL. A red day with high load gets a flag.
- Illness warning: a night is a "signal night" when RHR >= band mean + SD + 3 bpm and HRV < band mean - SD.
  Warning when today and yesterday are both signal nights, or today is one and today's check-in says slept badly
  or stressed. Missing data is never a signal. Wording is a suggestion only.
- Warning accuracy (Trends, from 60 check-ins): illness starts (ill day whose previous day is not ill) with a
  warning 1-3 days before, and warnings with no ill check-in in the next 3 days (warnings from the last 3 days
  are not counted yet).
- Settings page (`/settings`): sleep need 4-12 h. Anything else gives a 400 and nothing is written; a corrupt
  stored value falls back to 8 h.

### Running (`app/running.py`, stdlib only, computed on page load)
- HR zones: lower edges at 50/60/70/80/90% of max HR (below 50% counts in no zone). Max HR = Settings value, else
  the highest `max_hr` in 12 months. Zone source `maxhr` bins the stored seconds-at-bpm histogram (`activity_hr`;
  samples more than 30 s apart are skipped); `garmin` uses Garmin's own zone seconds (`activity_zones`). Switching
  the source only recomputes from stored tables. No max HR: pages say "set max HR in Settings".
- 80/20 check: share of time in Z1+Z2 over 28 days (>= 75% good, >= 60% warn, else bad). Weekly stacked bars, 26 weeks.
- Aerobic efficiency (EF) = (m/min) / avg HR, runs of 20 min or more whose avg HR is in Z2 (the run's own Z2 for the
  Garmin source). Trend = mean of the last 28 days vs the 28 before.
- Decoupling = (EF1 - EF2) / EF1 x 100 from laps, first half = laps whose time midpoint is before half the total.
  Runs of 45 min or more with at least 4 laps with HR. < 5% good, 5-10% warn, > 10% bad.
- VDOT (Daniels/Gilbert): `vo2(v) = -4.60 + 0.182258 v + 0.000104 v^2`, `%max(t) = 0.8 + 0.1894393 e^(-0.012778 t)
  + 0.2989558 e^(-0.1932605 t)` (t in min), `VDOT = vo2 / %max`. Predicted time by bisection (60 s to 6 h).
  Riegel: `T2 = T1 (D2/D1)^1.06`. Predictions use the best 5k best effort of the last 90 days.
- Effective VO2max per run (Runalyze method) = vo2(v) / ((avg HR / max HR - 0.37) / 0.64); needs 20 min or more and
  avg/max > 0.5. Multiplied by a correction factor = VDOT of the best run of 3 km or more in 365 days divided by that
  run's effective VO2max, clamped to 0.8-1.2 (1.0 without such a run).
- Endurance gap = half PB minus the half the 5k PB predicts (<= 5 min good, <= 12 min warn). Long-run readiness =
  100 x (2/3 x min(1, weekly km / (0.5 x VDOT^1.135)) + 1/3 x min(1, longest km / 18)), weekly km = 56-day average,
  longest = 42 days (>= 90 good, >= 70 warn). Like Runalyze's marathon shape, with our own half targets.
- Best efforts (400 m, 1 km, 1 mile, 5k, 10k, half): sliding window with interpolation over the detail samples;
  steps and windows faster than 2:30/km are treated as GPS glitches. Laps fallback: fastest span of consecutive laps
  covering the distance, time scaled to it. Pace curve: last 90 days vs all time.
- Settings: `max_hr` (blank = auto, else 100-230) and `zone_source` (`maxhr`|`garmin`). Any invalid field gives a 400
  and nothing is written. Thresholds are constants at the top of `running.py`. Not medical advice.

### Volume (`app/analysis.py`, no tables)
- Heatmap (Trends): daily load for 53 Monday-first weeks. Level 0 = no load; levels 1-4 by the quartiles (25/50/75th
  percentile) of the non-zero loads in the window.
- Weekly table (Runs, 12 weeks, newest first): distance, time, runs, FiiT classes. Long-run share = longest run / week
  distance, shown only with 2+ runs; above 35% gets a warn chip (a suggestion, not medical advice).
- Streak: consecutive weeks with 2+ runs, counted back from last week; this week adds 1 once it has 2 runs, and
  neither counts nor breaks the streak before that.
- Cadence chart (Trends): easy runs (Z2 avg HR) in the last 180 days, 120-230 steps/min only (0, empty and
  stride-per-minute values are dropped).

## Weekly summary (`app/insights.py`, stdlib only)
- Cron `0 19 * * 0` runs `scripts/fitness-weekly.sh`, which POSTs `/api/weekly-summary` (up to 300 s). The app builds a
  JSON of the week (load, form, ACWR, recovery, sleep debt, zones, efficiency, predictions, volume, check-in counts),
  asks the Mac mini's Ollama (`FITNESS_OLLAMA_URL`, `FITNESS_MODEL`, default qwen3.5:9b; no paid API) for 5 bullets,
  stores them in `summaries` and the script posts them to Discord. The Insights page lists them, newest first.
- The model sees numbers only, from a whitelist: never check-in note text, raw Garmin JSON or tokens.
- `GET /api/feed.json` (read-only, no params): today's readiness, recovery, illness flag, form zone, last 3 activities
  and the newest weekly summary. The dashboard reads it for Hermes's `personal.json`; no check-in notes, no raw data.
- States: `ok`; `skipped` when the Mac mini is unreachable or slow (one attempt, no retry; Insights says "Mac mini
  unreachable: skipped this week"; no Discord post); `failed` when the reply has under 3 bullets (more than 5 are cut).
  A week with no data answers 204 and stores nothing. A second call while one runs gets 409. A re-run replaces the
  week's row.
- Bullets pass through `clean_bullet`: em dashes become commas, filler sentences ("Great question", "I hope this helps")
  are dropped; a bullet left empty is dropped.
- By hand: `scripts/fitness-weekly.sh` (it posts to Discord on success). Not medical advice.

## Plan (`app/plan.py`)
Phase 3: a goal, a stored training block and today's session. Stdlib only; constants at the top of the file.
- Goal: Settings page (5k, 10k, half or custom metres; target `mm:ss`/`h:mm:ss`; optional race date within a
  year). Saving makes it the active goal, deletes the future `plan_weeks` and `plan_days`, and regenerates from next
  Monday (this week stays). Invalid input is a 400 and nothing is written.
- Block: with a race date the weeks back from it split taper (1 week for 5k/10k, 2 for the half) and the rest
  roughly base 40% / build 40% / sharpen 20%. Without a date (and after a race): rolling base weeks, every 4th easier.
  More rolling weeks are appended when fewer than 2 remain after the current one; a stored row is never rewritten.
- Week: Wednesday work run club (fixed, never moved or made faster), one FiiT class (Monday, re-suggested Tuesday,
  Friday only when the weekend run is easy), Saturday quality run (long easy / tempo or intervals / race pace /
  taper sharpener). A missed or swapped weekend run moves once to Sunday, never into the next week.
- Today: the first rule that applies wins: chest symptoms or fever = rest; above-neck = easy only; graded return
  for a few days after; soften a quality run when readiness < 50, recovery < 34 or the illness warning (moves to
  Sunday if free, else steady); an optional bonus when readiness >= 75, HRV good and form not high risk. Missing
  data never softens or offers a bonus. Only today's `plan_days` row is written (Today and Plan page loads); the
  feed (`todays_session`) computes without writing.
- Pages: Today tile, `/plan` (goal, phase, this and next week, done/missed chips, block strip). Suggestions only.
- With no active goal the pages say "Set a goal" and the feed gives `todays_session: null`. A goal with no stored
  weeks (the seed on first start) gets its weeks created on the first Today or Plan load.

## Schema (`app/db.py`, version in `schema_version`)
`raw(kind,key)`, `daily(date)`, `activities`, `laps`, `checkins(date)` (one row per day, editable),
`fiit` (srpe = minutes x effort, `activity_id`, `match_manual`), `pbs` (seeded 5k 25:03, 10k 52:10, half 2:14:50),
`sync_state`, `settings(key)` (sleep need, max_hr, zone_source), `activity_zones` (Garmin's zone seconds),
`activity_hr` (seconds at each bpm), `goals` (one active, via a partial unique index; seeded 5k 23:59, no date; old ones kept), `plan_weeks(week_start)` (stored block: phase, week_no, easy, race_date), `plan_days(date)` (planned/adjusted/reason, today's row only), `summaries(week_start)` (weekly written summary: status ok|skipped|failed, facts, bullets, reason), `best_efforts` (fastest 400 m to half per run, source details|laps). Add a migration at the end of `MIGRATIONS`; never edit an old one.

## Tests
`cd tools/fitness && python3 -m unittest discover -s tests` (stdlib only).
