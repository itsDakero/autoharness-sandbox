# Fitness plan engine: goal, training block and today's session (phase 3 of the running coach)

## Problem
The Fitness app only looks back: Garmin sync, check-in, FiiT log and the phase-2 analysis. It has no
goal, no week plan and no "today's session", and it never says when to fit in a FiiT class. Phase 3
of `ideas/done/garmin-fitness-dashboard.md` (Later phases, item 3) describes the plan engine; this note
builds it.

## Proposal
- **Goal** (Settings page): distance (5k, 10k, half, or custom metres), target time, optional race
  date. Goals change often; the first one is 5k sub-24. New `goals` table: one active goal, old ones
  kept as history.
- **Block**: phases base -> build -> sharpen -> taper.
  - With a race date: phase lengths back-planned from the date (taper 1 week for 5k/10k, 2 weeks for
    the half; the rest split base/build/sharpen roughly 40/40/20).
  - Without a date: rolling 4-week cycles (3 build-up weeks + 1 easier week), base until the next
    goal is set with a date.
  - Stored as `plan_weeks(week_start, phase, ...)` when the goal is saved, so daily changes never
    rewrite the block. Changing the goal regenerates the future weeks only.
- **Minimum week** (template per phase):
  - **Wednesday**: work run club, fixed. 3-4 miles steady at 9:00-9:30/mile. Never moved and never
    turned into speed work.
  - **One FiiT class**, type suggested by phase from `logic.FIIT_TYPES` (e.g. strength in base, hiit
    in build/sharpen, light or none in taper). Suggested day: not the day before the weekend quality
    run, and not the day after Wednesday's run if avoidable (default Monday or Tuesday; Friday only
    when the weekend run is easy).
  - **Weekend run**: the quality session. Base: long easy run. Build: tempo or intervals. Sharpen:
    race-pace work. Taper: short sharpener. Pace targets from the goal time and the current PBs
    (`pbs` table).
  - **Optional bonus session**, offered only when readiness is good: Garmin readiness and HRV vs
    baseline (phase-2 recovery analysis) both good, and form not in the high-risk zone.
- **Daily adjustment**: readiness and the morning check-in can swap or soften sessions within the
  week, never rewrite the block. The check-in overrides the numbers (neck check): above-neck symptoms
  = easy only; chest symptoms or fever = rest; graded return afterwards (easy, then steady, then
  quality, over a few days). Stored per day in `plan_days(date, planned, adjusted, reason)`.
- **Done or missed**: a planned session counts as done when a Garmin run or a logged FiiT class lands
  that day (reuse `logic.match_fiit` and the `activities` table). A missed quality run may move to the
  next free day in the same week, never into the next week.
- **Pages**:
  - Today: a "Today's session" tile (session, pace or effort target, and the reason if adjusted).
  - New Plan page: goal, current phase and week number, this week and next week, done/missed chips.
  - Feed (`app/feed.py`): add today's session so the morning brief and Hermes can use it later.

## Notes
- Maths and plan rules are stdlib only, in a new `app/plan.py` (or `app/logic.py`). Each rule gets a
  unit test with a worked example. Phase lengths, pace offsets and readiness thresholds live in one
  place as constants.
- Schema: append migrations at the end of `MIGRATIONS` in `app/db.py`; never edit an old one.
- Look: same as the 2026-10-17 redesign. Tiles, chips coloured with `--good`/`--warn`/`--bad`. Inline
  SVG, no CDN. Each new number gets a one-line "what this means".
- Bump the image tag in `tools/fitness/compose.yaml` (minor version). Update `tools/fitness/README.md`.
- Not medical advice: keep the footer; word changes as suggestions.
- Out of scope (phase 4): Discord #training brief, pushing planned runs to the Garmin calendar,
  illness early warning from his own patterns.

## Plan
Goal: Phase 3 of the fitness app. Add a goal, a stored training block (`plan_weeks`), and a per-day session with readiness and check-in adjustments (`plan_days`). Show them on Today, a new Plan page and the feed.
Kind: change to tools/fitness
Note fix: `logic.FIIT_TYPES` is the list of Garmin activity types used for matching. The FiiT class types are the `fiit` table's own (strength/hiit/mobility/other), so suggestions use those. The note asks for nothing against the repo rules.

Files:
- tools/fitness/app/plan.py: new, stdlib only. Holds all the constants and rules below. Pure functions take rows and dates and return dicts. Never raises on odd rows: missing data gives "-" or "no change".
- tools/fitness/app/db.py: append migration 5 (SCHEMA_VERSION = 5). Add helpers `active_goal`, `save_goal`, `upsert_plan_day`.
- tools/fitness/app/main.py: add `load_plan(con, write)`, GET `/plan`, and POST `/settings/goal`. Add the plan context to `/` and `/settings`.
- tools/fitness/app/feed.py: add `todays_session` (with `load_plan` passed in, like `load_analysis`).
- tools/fitness/app/templates/plan.html: new.
- tools/fitness/app/templates/today.html: add a "Today's session" tile at the top of the tiles.
- tools/fitness/app/templates/settings.html: add a goal form (separate `<form>` to `/settings/goal`) and the last 10 goals.
- tools/fitness/app/templates/base.html: add a nav tab ("/plan", "Plan") after Today.
- tools/fitness/app/static/style.css: only if the chips or week grid need it (reuse `--good`/`--warn`/`--bad`).
- tools/fitness/tests/test_plan.py: new. One worked-example test per rule below.
- tools/fitness/tests/test_db.py, tests/test_feed.py: add tests for migration 5 and the seed goal, and for `todays_session` (None with no goal, set with one).
- tools/fitness/compose.yaml: image `homelab/fitness:0.8.0` -> `homelab/fitness:0.9.0`.
- tools/fitness/README.md: add a "Plan (`app/plan.py`)" section. Add `goals`, `plan_weeks` and `plan_days` to Schema.

Schema (migration 5):
- `goals(id INTEGER PK AUTOINCREMENT, distance TEXT NOT NULL CHECK(distance IN ('5k','10k','half','custom')), distance_m REAL NOT NULL, target_s INTEGER NOT NULL, race_date TEXT, created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0)`
  - Add `CREATE UNIQUE INDEX goals_one_active ON goals(active) WHERE active=1`.
  - Seed the first goal: ('5k', 5000, 1439, NULL, '2026-10-26T00:00:00', 1).
- `plan_weeks(week_start TEXT PK, goal_id INTEGER NOT NULL, phase TEXT NOT NULL CHECK(phase IN ('base','build','sharpen','taper')), week_no INTEGER NOT NULL, easy INTEGER NOT NULL DEFAULT 0, race_date TEXT)`
- `plan_days(date TEXT PK, planned TEXT NOT NULL, adjusted TEXT, reason TEXT, updated_at TEXT NOT NULL)`
  - `planned` and `adjusted` hold session kinds: rest, run_club, fiit, quality, long_easy, easy, steady, bonus, race.

Rules (constants at the top of plan.py):
- Week = Monday-first (`logic.week_start`).
- Fixed days:
  - WED = 2: run_club, always "3-4 miles steady, 9:00-9:30/mile". Never moved and never made speed work.
  - WEEKEND_DAY = 5 (Saturday): the quality session.
  - FIIT_DAYS = (0, 1), Monday then Tuesday. Friday (4) is also allowed when the week's weekend session is long_easy (a base or easy week).
  - All other days are free (rest).
- Dated block, generated at save from the first week to generate (see Goal save):
  - N = number of weeks up to and including the race week.
  - taper = TAPER_WEEKS {5k:1, 10k:1, half:2}; custom is 1 if ≤ 10000 m, else 2. Capped at N.
  - rest = N - taper. sharpen = int(0.2·rest + 0.5), build = int(0.4·rest + 0.5), base = the remainder (floored at 0).
  - Worked tests: 5k, N=12 gives 5/4/2/1; half, N=16 gives 5/6/3/2; 5k, N=1 gives taper only.
  - The race week row carries race_date. On that date the session is "race".
- No date (and every week after a race week): rolling base weeks. week_no continues; easy = week_no % 4 == 0.
- Lazy append: when fewer than 2 weeks after the current one are stored, append rolling weeks up to 12 ahead. Never rewrite an existing row.
- Goal save, in one transaction:
  - Set the old goal to active=0 and insert the new goal.
  - Delete plan_weeks with week_start > this Monday, and plan_days with date > today.
  - Generate from next Monday. If no row exists for this week, generate from this Monday.
- Weekend session by phase:
  - base: long_easy, 60-75 min easy.
  - build: quality. Odd week_no = tempo, 2 x 10 min. Even = intervals, 5 x 1 km with 2 min jog.
  - sharpen: race-pace. 3 x 1 mile at goal pace for 5k/10k; 3 x 3 km for half or a custom distance over 10 km.
  - taper: 20 min easy + 4 x 400 m at goal pace.
  - Easy week: easy run, 45 min.
- FiiT type by phase: base = strength, build and sharpen = hiit, taper = mobility, easy week = mobility. Race week: none.
- Paces in s/km, shown in the page's unit via `logic.fmt_pace`:
  - P5 = 5k PB / 5 (`pbs`). If there is no PB, use G5 instead.
  - G5 = `running.riegel(target_s, distance_m, 5000)` / 5. Goal pace = target_s / distance_m · 1000.
  - easy = P5 + (60, 90). steady = P5 + (35, 55). tempo = P5 + (15, 25). intervals = G5 + (-5, 0). race-pace = goal pace ± 3.
- Done or missed:
  - A run kind is done when an activity whose type contains "running" falls on that date.
  - The week's FiiT is done when any `fiit` row falls in the week on or before today. While it isn't done, it is re-suggested on the next allowed FiiT day. It is missed after the last allowed day.
  - Past days with nothing done are "missed". Today and later are "planned".
- Moving the quality session: if quality (or long_easy) was missed or swapped, it moves once to the next free day ≥ today in the same week, never Wednesday, never into the next week. reason = "moved from <Day> (missed)".
- Daily adjustment for today. The first rule that applies wins:
  1. Today's check-in has ill_chest: rest, "chest symptoms or fever: rest".
  2. ill_neck: cap at easy. Runs become easy 20-30 min or rest. FiiT becomes mobility or rest.
  3. Graded return, counted from the last ill check-in day within 7 days:
     - After neck: day 1 is capped at easy, day 2 at steady.
     - After chest: days 1-2 easy, day 3 steady.
     - Then normal.
  4. Soften (missing data never triggers it): Garmin readiness < 50, or recovery score < 34, or the illness warning. A quality session today becomes easy and moves under the moving rule if a free day remains; otherwise it becomes steady.
  5. Bonus: offered only on a free day with no planned session when all of these hold:
     - readiness ≥ 75 (BONUS_READINESS_MIN)
     - `rec["chips"]["hrv"]["tone"] == "good"`
     - form zone is not "High risk"
     - no ill cap is active
     - no run or FiiT done on a free day this week yet

     It reads "optional: easy 20-30 min or mobility".
- plan_days write: only today's row is upserted, from Today and Plan page loads (`write=True`). Past rows are never rewritten. The feed computes with `write=False`.

Pages:
- Today tile: kind title, target pace or effort, a reason chip when adjusted, and a one-line "what this means". With no goal: "Set a goal in Settings".
- Plan page:
  - Goal (distance, target, race date or "rolling").
  - "<Phase> · week N", plus "easier week" when it is one.
  - This week and next week as 7-day rows: session, target, and done/missed/planned chips (good/bad/neutral).
  - The phase timeline as an inline SVG strip of the stored weeks.
  - One-line explainers. Keep the footer.
- Goal form validation:
  - distance must be one of the 4. Custom metres must be an integer from 400 to 50000.
  - Target is "mm:ss" or "h:mm:ss", 5 min to 6 h, and no faster than 2:30/km.
  - race_date is blank, or ISO > today and ≤ today + 365.
  - Anything invalid gives a 400 via error.html and nothing is written.
- Feed: `todays_session` = {phase, week_no, kind, title, target, adjusted (bool), reason}, or None when there is no goal. Wrap it in `_part`. No check-in note text.

New env vars: None
Checks the builder must run:
- `cd <worktree>/tools/fitness && python3 -m unittest discover -s tests`
- `python3 -m py_compile app/*.py`
- `scripts/dc.sh <worktree>/tools/fitness config -q`
Review focus:
- No active goal, or an empty plan_weeks (fresh DB, or the seed deleted) -> pages show "Set a goal", the feed gives `todays_session: null`, and nothing crashes.
- Missing readiness, HRV band still learning, or no check-in -> no soften and no bonus; the plan stays as stored.
- The race date passes, or a goal changes mid-week -> this week's and past weeks' rows are untouched, and rolling weeks are appended after the race.
- An invalid goal form (bad time, past date, custom out of range) -> 400, and the goal, plan_weeks and plan_days are unchanged.
- A missed Saturday quality run on a Saturday-or-later today -> it moves at most to Sunday and never into next week; a Wednesday run is never moved or made faster.
Docs: tools/fitness/README.md (Plan section + Schema). docs/README.md line 17: add "plan engine (goal, block, today's session)". CLAUDE.md layout fitness line: "+ training plan (goal, block, today's session)". No port changes.

## Manual steps
Deploy with `scripts/deploy-idea.sh fitness-plan-engine`. Migration 5 runs on start and seeds the 5k sub-24 goal (23:59, no date). Change it at http://192.168.0.210:8086/settings.

## Review notes
1. /home/dan/homelab/.worktrees/fitness-plan-engine/tools/fitness/app/main.py:446: the feed passes `load_plan(c, False)` without `rec`/`load`, so `/api/feed.json` runs `load_analysis` and `load_recovery` twice. The output is correct but the work is wasted. The feed could reuse the values it already has.
2. /home/dan/homelab/.worktrees/fitness-plan-engine/tools/fitness/app/plan.py:144: `missing_weeks` appends from `max(last+1, this Monday)`. If no Today or Plan page loads for about 10 weeks, the skipped weeks never get rows and the block strip has a gap. This is harmless in normal use.
3. plan.py:266-271: when the week's FiiT is missed and today is past every allowed day, the chip is moved to the last allowed day (Friday in base weeks) and shows "moved from Monday" with a missed chip. That reads a little oddly. Leaving it on Monday as missed would be clearer.
4. today.html: the "Today's session" tile has no done chip when today's session has already been done. Only the Plan page shows it.
5. The worktree changes are still uncommitted (17 files). That is expected before commit; just noting it.

## Declined to judge
- The week number counts on across goal changes ("Build · week 9") instead of restarting at 1 for each phase: the plan says week_no continues.
- Today and Plan page GETs write today's `plan_days` row: the plan specifies this (`write=True`).
- POST /settings/goal has no CSRF protection: it matches the existing settings POST on this admin-only app.
- When a goal changes mid-week, the current week keeps the old goal's race date: the plan requires that this week's row is left alone.
