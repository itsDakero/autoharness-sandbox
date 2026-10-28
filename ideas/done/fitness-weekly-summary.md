# Fitness weekly summary: a written "what's improving" each Sunday (fitness analysis 5 of 5)

## Problem
The numbers from notes 1–4 still need reading. Whoop and Oura write a short summary. Phase 1
planned the Mac mini's model for this.

## Proposal
- Sunday evening, build a small JSON of the week: load, form, ACWR, recovery, sleep debt, zones,
  efficiency, predictions, check-ins, illness flags.
- Send it to the Mac mini's model, the same way Hermes does (local model only, no paid API key).
  It writes 5 bullets: what improved, what slipped, what it means, one suggestion.
- Store it in a new `summaries` table. Show it on a new **Insights** page (newest first).
- Post it to Discord with `scripts/discord.sh`.
- The model only sees the numbers JSON: never raw Garmin JSON, tokens or check-in note text.

## Notes
- Needs notes 1–3 deployed (it summarises their numbers); works with whatever exists.
- If the Mac mini is down, skip the week and say so on Insights; no retry storm.

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
Goal: A written summary of the week, made each Sunday at 19:00 by the Mac mini's model from a JSON of the week's numbers only. It is stored in a new `summaries` table, shown on a new Insights page and posted to Discord.
Kind: change to tools/fitness (plus a cron script)
Files:
- tools/fitness/app/insights.py: new, stdlib only. It holds:
  - The constants: `OLLAMA_URL` (env `OLLAMA_URL`, default `http://100.74.81.122:11434`), `MODEL` (env `FITNESS_MODEL`, default `qwen3.5:9b`, the model Hermes uses), `TIMEOUT_S = 240`, `MIN_BULLETS = 3`, `MAX_BULLETS = 5`.
  - `class Offline(Exception)`.
  - `build_facts(load_series, load_sum, rec, rn, weeks, streak, checkins, today) -> dict | None`. It returns None when the week (Monday to today) has no daily rows and no activities or FiiT. The dict has:
    - `week_start` and `week_end`.
    - `load`: ctl, atl and tsb now and 7 days ago, form zone, acwr, ramp, monotony, and this week's load total against last week's.
    - `recovery`: average recovery score this week against last week, sleep debt in hours, consistency, the HRV and RHR chip text, and the count of illness-warning days this week.
    - `running`: easy_share, ef_trend, vo2_current, predictions as h:mm:ss strings, vdot, long-run readiness.
    - `volume`: this week's row (km, hours, runs, FiiT, long_share) against the average of the previous 4 weeks, and the streak.
    - `checkins`: count, average feeling, and counts of ill / sore_legs / stressed / slept_badly days.
    - Floats rounded to 1 decimal, missing values as null.
    - Never note text and never raw JSON. Build the dict from an explicit whitelist of keys, not by copying the check-in dicts.
  - `prompt(facts) -> (system, user)`. The system text says: exactly 5 lines, each starting with "- ": what improved, what slipped, recovery and sleep, what it means, one suggestion. Use only these numbers. Say "not enough data" rather than guess. No diagnosis. Word warnings as suggestions.
  - `ask_model(facts) -> str`. A urllib POST to `/api/chat` with `stream:false` and `think:false`, the same way as `tools/wardrobe/app/tagger.py`. It raises `Offline` on URLError, timeout, a non-200 answer or bad JSON. One attempt, no retry.
  - `parse_bullets(text) -> list[str]`. It drops `<think>...</think>`, takes lines starting with `-`, `*`, `•` or `1.`–`5.`, strips the markers and caps the list at `MAX_BULLETS`.
- tools/fitness/app/db.py: append one migration at the end of `MIGRATIONS`: `CREATE TABLE summaries(week_start TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL /* ok|skipped|failed */, model TEXT, facts TEXT, bullets TEXT, reason TEXT)`. Add `upsert_summary(...)`, which is INSERT ... ON CONFLICT(week_start) DO UPDATE.
- tools/fitness/app/main.py:
  - `SUMMARY_LOCK = threading.Lock()`.
  - `POST /api/weekly-summary`, which runs the work in `asyncio.to_thread`:
    - If the lock is already held, answer 409 "already running".
    - Build the facts from `load_analysis`, `load_recovery`, `load_running(con, "km")`, `analysis.weekly_summary`/`run_streak` (the same queries as `/runs`) and this week's check-ins. Wrap all of it in try/except so a failure becomes status failed.
    - No facts: store nothing and answer 204.
    - `Offline`: upsert status=skipped with reason "Mac mini unreachable: skipped this week" and answer 503.
    - Fewer than `MIN_BULLETS` bullets: upsert status=failed with reason "model reply unusable" and answer 502.
    - OK: upsert status=ok and answer 200 text/plain: "Fitness week of <week_start>\n- b1\n...".
  - `GET /insights`: summaries newest first (LIMIT 52), plus `rec["accuracy"]` for the illness-flag accuracy block.
- tools/fitness/app/templates/insights.html: new page in the 2026-10-17 look:
  - One card per week with a status chip: none for ok, `--warn` for skipped, `--bad` for failed with its reason.
  - The bullets.
  - A `<details>` "Numbers the model saw" showing the pretty-printed facts.
  - The empty state "First summary on Sunday evening."
  - The accuracy block, the same wording as on Trends.
  - The one-line "what this means": "Written by the Mac mini's model from the numbers above only; a suggestion, not advice."
  - Keep the footer.
- tools/fitness/app/templates/base.html: add ("/insights", "Insights") to the nav before Settings.
- tools/fitness/tests/test_insights.py: unittest tests:
  - `build_facts` on a fixture whose check-in has `note="secret note"`: "secret" is not in `json.dumps(facts)`, the averages and counts are worked out by hand, and missing sections come out as null.
  - `build_facts` on an empty week returns None.
  - `parse_bullets` on: 5 dash lines, a numbered list, a reply with `<think>` text plus 6 bullets (capped at 5), and prose with no bullets (empty list).
  - `ask_model` with `insights.OLLAMA_URL` patched to `http://127.0.0.1:9` raises `Offline`.
- tools/fitness/tests/test_db.py: a test that the summaries migration applies and that `upsert_summary` replaces the row for the same week.
- tools/fitness/compose.yaml:
  - Change the image to `homelab/fitness:0.7.0`.
  - Add to `environment:`: `OLLAMA_URL: ${FITNESS_OLLAMA_URL:-http://100.74.81.122:11434}` and `FITNESS_MODEL: ${FITNESS_MODEL:-qwen3.5:9b}`.
- scripts/fitness-weekly.sh: new, modelled on scripts/wardrobe-daily.sh.
  - It runs `curl -s -m 300 -X POST http://127.0.0.1:8086/api/weekly-summary`.
  - On 200 with a non-empty body: `scripts/discord.sh "<body>\nInsights: http://192.168.0.210:8086/insights"`.
  - On 204, 409, 502, 503 or anything else: one syslog line only (`logger -t fitness-weekly`), no Discord post.
  - Always exit 0.
- scripts/install-cron.sh: add `0 19 * * 0 $REPO/scripts/fitness-weekly.sh # homelab` to ENTRIES.
- .env.example: add, with comments in the style of the wardrobe lines, `FITNESS_OLLAMA_URL=` (empty = http://100.74.81.122:11434) and `FITNESS_MODEL=` (empty = qwen3.5:9b).
- tools/fitness/README.md: a "Weekly summary" section covering the cron time, what the model sees (numbers only, no notes or tokens), the skipped/failed states, running `scripts/fitness-weekly.sh` by hand, and the new `summaries` table in the schema list.
- docs/fitness-analysis-prompt.md: mark section 6 "**Built** (0.7.0)".
- CLAUDE.md: add to the scripts list: `fitness-weekly.sh` (cron Sundays 19:00: the fitness app's weekly written summary to Discord; Mac mini model).
New service (if any): none
New env vars:
- FITNESS_OLLAMA_URL: the Mac mini's Ollama base URL for the summary (optional, has a default).
- FITNESS_MODEL: the text model (optional, default qwen3.5:9b).
Checks the builder must run:
- `cd <worktree>/tools/fitness && python3 -m unittest discover -s tests`
- `python3 -m py_compile <worktree>/tools/fitness/app/*.py`
- `bash -n <worktree>/scripts/fitness-weekly.sh <worktree>/scripts/install-cron.sh`
- `scripts/dc.sh <worktree>/tools/fitness config -q`
Review focus:
- Mac mini down or slow (connection refused, a 240 s timeout) -> one attempt, the row stored as skipped, Insights says "Mac mini unreachable: skipped this week", no Discord post and no retry until next Sunday.
- The script run twice at once (cron plus a run by hand) -> the second call gets 409 and only one model call runs. A re-run in the same week replaces that week's row (upsert), with no duplicate rows.
- Model reply odd (empty, `<think>` text, prose with no bullets, more than 5 bullets) -> fewer than 3 bullets gives status failed with no Discord post; more than 5 are capped at 5.
- A week with no data, or a missing section (no max HR, no check-ins, under 14 days of bands) -> no data at all gives 204 and no post. Missing sections go to the model as null and the page still renders.
- Privacy: check-in note text, raw Garmin JSON and tokens never reach the facts JSON or the prompt (the whitelist plus the test above).
Docs: the CLAUDE.md scripts list line; the tools/fitness/README.md weekly summary section and schema line; docs/fitness-analysis-prompt.md section 6 marked built. No port change.

## Manual steps
- Optional: set FITNESS_OLLAMA_URL and FITNESS_MODEL in the env file. The defaults match Hermes.
- After the deploy (deploy-idea reinstalls cron on drift), run `scripts/fitness-weekly.sh` once by hand, then check the Discord post and http://192.168.0.210:8086/insights.

## Review notes
1. /home/dan/homelab/.worktrees/fitness-weekly-summary/tools/fitness/app/main.py:653-658: a hand re-run while the Mac mini is down replaces that week's `ok` row with `skipped`, and the bullets are lost. That matches the plan ("a re-run replaces the week's row"), but keeping an existing `ok` row when the new result is skipped or failed would be kinder.
2. POST /api/weekly-summary has no login, like the existing POST /sync. Anyone on the LAN or tailnet can start a model call or overwrite the week's row. SUMMARY_LOCK stops two calls running at once. Admin-only app, no new port.
3. /home/dan/homelab/.worktrees/fitness-weekly-summary/scripts/fitness-weekly.sh:20: discord.sh cuts messages at 1990 characters. If the model writes five long bullets, the "Insights:" link at the end is cut off first. The app could cap each bullet's length.
4. `build_facts` also counts a week with only check-ins as having data. The plan only named daily rows, activities and FiiT. This seems reasonable: a week of check-ins still gets a summary.
5. main.py imports: `import json` sits out of alphabetical order. Cosmetic only.

## Declined to judge
- How good the model's wording is: it depends on the model at runtime and can't be checked from the code.
- The model call timing out when no data arrives for 240 s rather than after 240 s in total: Ollama with stream:false sends nothing until it finishes, so the two are effectively the same.
