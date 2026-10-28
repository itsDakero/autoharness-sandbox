# Wardrobe stage 2: outfit generator

Value: 4   (daily outfit ideas from clothes Dan owns)
Effort: 3  (rules, feedback weights, wear log, weather)
Risk: 1    (inside the existing tools/wardrobe app)
Source: Dan 2026-10-23 (stage 2 of ideas/done/pinterest-wardrobe.md, "Proposed split" and "Answers")

## Problem
tools/wardrobe (stage 1, deployed 2026-10-23, port 8091) catalogues items but suggests nothing.

## Proposal
In tools/wardrobe, as agreed in ideas/done/pinterest-wardrobe.md:
- Rule-based generator: top + bottom + shoes (optional outer layer), season and colour rules.
- **Only items marked bought** (never wishlist items, never retired ones).
- Thumbs up/down per outfit that adjusts rule weights.
- Wear log: no repeats within a window, a "never worn" list.
- Daily outfit using the Open-Meteo forecast (free, no key).
- Optional daily Discord line via `scripts/discord.sh` (off by default).
No product links or purchases here (that is wardrobe-gaps).

## Plan
Goal: Stage 2 of the agreed wardrobe split. It adds a rule-based outfit generator inside tools/wardrobe: only owned, active items; thumbs that adjust weights; a wear log with a no-repeat window and a "never worn" list; a daily outfit from the Open-Meteo forecast; and an optional daily Discord line, off by default.
Kind: change to tools/wardrobe (plus one cron script)
Files:
- tools/wardrobe/app/db.py: append migration 2:
  - `outfits(key TEXT PK, items TEXT json, created_at)`. The key is the sorted item ids joined by "-".
  - `votes(key TEXT PK, vote INTEGER CHECK(vote IN (-1,1)), at)`
  - `wear(id PK, date TEXT, key TEXT, items TEXT json, at)`
  - `daily(date TEXT PK, key TEXT, weather TEXT json, note TEXT)`
  - Helpers for each table. Profile keys need no schema change.
- tools/wardrobe/app/outfits.py (new, stdlib only, pure functions): candidate building, the rules, scoring, weights from votes, and pick(). Rules are below.
- tools/wardrobe/app/weather.py (new, stdlib urllib):
  - Open-Meteo fetch: `https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=auto&forecast_days=1`, 10 s timeout, returns dict or None.
  - `parse(json)` and `season_for(month, tmax)` kept pure so they can be tested.
- tools/wardrobe/app/main.py: the routes below, the profile fields, and the "Outfits" and "Worn" nav entries.
- tools/wardrobe/app/templates/outfits.html, worn.html (new); base.html (nav: add ("/outfits","Outfits"), ("/worn","Worn")); profile.html (new fields).
- tools/wardrobe/tests/test_outfits.py, tests/test_weather.py (new, stdlib unittest, no network); tests/test_db.py (migration 2 on a v1 DB keeps the existing rows).
- tools/wardrobe/compose.yaml: only change the image tag to `homelab/wardrobe:0.2.0`. Port 8091, labels and env stay unchanged.
- tools/wardrobe/README.md: a new "Outfits" section (rules, thumbs, wear log, weather, Discord toggle, failures). Change the "Later stages" line to drop outfits.
- scripts/wardrobe-daily.sh (new, executable):
  - `curl -s -m 60 -o <tmp> -w '%{http_code}' http://127.0.0.1:8091/api/daily.txt`.
  - 200 with a non-empty body: run `scripts/discord.sh "<body>"`.
  - 204: exit 0 silently (toggle off).
  - Anything else (app down): `logger -t wardrobe-daily` and exit 0, with no Discord post (Kuma already alerts on the app).
  - Use a tmp file from mktemp with a trap rm.
- scripts/install-cron.sh: add the entry `0 7 * * * $REPO/scripts/wardrobe-daily.sh # homelab`.
- CLAUDE.md: add `wardrobe-daily.sh` (cron 07:00: the wardrobe's daily outfit to Discord when the toggle in its profile is on) to the scripts list. Change the layout's wardrobe line to "clothes catalogue + outfit generator".

Generator rules (decisions for outfits.py):
- Pool: `kind='owned' AND status='active' AND category IS NOT NULL AND tag_status IN ('tagged','reviewed')`. Never wishlist, retired, pending or failed items. Accessories are ignored.
- Shapes: top+bottom+shoes, or dress+shoes, each with an optional outerwear item.
- Season: an item fits if its seasons include today's season, or if its seasons list is empty (that counts as all-season). The season is decided like this:
  - With a forecast: tmax ≥ 20 is summer, tmax ≤ 11 is winter, anything between is spring (Mar-Jun) or autumn (otherwise).
  - With no forecast, use the month: DJF winter, MAM spring, JJA summer, SON autumn.
- Outerwear:
  - Required when tmax < 14 or rain ≥ 50%. Left out when tmax ≥ 20 and rain < 50%. Otherwise optional, and added if a candidate scores higher with it.
  - If outerwear is required but none fits, generate without it and set the note "No suitable outer layer owned".
- Colour: NEUTRALS = black, white, grey, navy, beige, brown. At most 2 distinct non-neutral colours across the outfit, and at most one `multi` item. Shoes' colours count.
- Style clash (rejected pairs): sport+smart, sport+formal, casual+formal. Missing style = no clash.
- Weights from votes, recomputed from the votes table every time (no stored drift):
  - Features per outfit: each unordered colour pair across different items (`c:navy|white`) and each style pair (`s:casual|smart`).
  - weight(f) = clamp(1 + 0.2·ups − 0.3·downs, 0.2, 3.0).
  - Score = mean feature weight (1.0 if none) × random.uniform(0.85, 1.15).
- Excluded:
  - Any outfit key Dan voted down.
  - Any candidate whose top, bottom or dress appears in the wear log within `repeat_days` (profile, default 7, range 0-60). Shoes and outerwear may repeat.
  - If the window leaves no candidate, drop the window and set the note "Everything fits the no-repeat window; showing a repeat".
- Cap: if the product of the category counts is over 50 000, randomly sample 50 000 combinations (seed from the date for the daily pick).
- Empty pool or no valid shape: return None plus a reason naming the missing category ("Add at least one shoes item marked bought").

Routes (main.py):
- GET `/outfits`:
  - Today's outfit is stored in `daily`. On the first request of the date, fetch the weather (profile `lat`/`lon`, skipped if unset), generate the outfit, and `INSERT OR IGNORE`, then re-read so that parallel requests agree.
  - If a stored item has since been retired or deleted, regenerate today's row.
  - Shows the thumbnails, a weather line (or "No forecast; using the month"), the note, the 👍/👎 vote buttons, and "Wore this" and "Another".
  - "Another" (GET `/outfits?another=1`) shows a fresh pick that excludes today's key. It is shown only, and the daily row is not changed.
- POST `/outfits/vote` (key, vote): upsert the vote, so changing your mind replaces it. Validate the key format, and that it exists in `outfits`. Redirect to `/outfits`.
- POST `/outfits/wear` (key, date default today): insert one wear row with the items as JSON. The same key on the same date is ignored, so a double click doesn't double-log. Redirect.
- GET `/worn`:
  - "Never worn": owned active items with no wear row, oldest first, with days since bought_at/created_at.
  - The last 60 wear rows. Deleted items show as "(deleted)".
  - A "delete entry" POST `/worn/{id}/delete` for mistakes. It deletes the wear row only.
- GET `/api/daily.txt`:
  - 204 when profile `daily_discord` is not "1".
  - Otherwise 200 text/plain with one line, e.g. `Outfit for Fri 23 Oct (12°C, 60% rain): navy jumper, grey chinos, white trainers + rain jacket. http://homelab:8091/outfits`, with items named "colour category [brand]".
  - When there is no outfit, a 200 line with the reason.
- Profile: add `lat`, `lon` (floats, validated to -90..90 / -180..180, blank allowed), `repeat_days` (int 0-60), and `daily_discord` (checkbox, default off). Invalid input gets a 400 message and nothing is saved.

New service: None (existing wardrobe, host port 8091, Kuma and .lan unchanged).
New env vars: None (location and toggle live in the app's profile, so nothing personal goes in git).
Checks the builder must run:
- `scripts/dc.sh .worktrees/wardrobe-outfits/tools/wardrobe config -q`
- `python3 -m py_compile .worktrees/wardrobe-outfits/tools/wardrobe/app/*.py .worktrees/wardrobe-outfits/tools/wardrobe/tests/*.py`
- `cd .worktrees/wardrobe-outfits/tools/wardrobe && python3 -m unittest discover -s tests`. The tests cover:
  - wishlist, retired, pending and failed items are never picked
  - the season and outerwear thresholds
  - colour and style rules
  - a down-voted key is never returned
  - the repeat window and its fallback
  - the empty-pool reason
  - weights clamped
  - weather.parse on a sample JSON and on garbage, which returns None
- `bash -n scripts/wardrobe-daily.sh` and `shellcheck scripts/wardrobe-daily.sh` if available
- `CRON_LIST=/dev/null scripts/install-cron.sh --check` lists the new wardrobe-daily line as missing (this proves the entry parses)

Review focus:
- Open-Meteo down, slow or returning odd JSON -> 10 s timeout, generate from the month, show "No forecast"; /outfits and /healthz never 500; no retry storm (the weather is stored once per date in `daily`).
- Tiny or empty wardrobe (no shoes, nothing bought yet, everything worn this week) -> a clear reason or the repeat-fallback note, never an exception or a wishlist/retired item.
- Discord toggle off, or the app down at 07:00 -> no post at all (204 = silent, app down = a log line only); toggle on gives exactly one post a day.
- Two requests on a new day, or a double-clicked "Wore this"/vote -> one daily row, one wear row, one vote per outfit.
- Migration on the live v1 DB -> the existing items and profile are untouched, and user_version becomes 2.

Docs: CLAUDE.md scripts list (wardrobe-daily.sh) and layout wardrobe line; tools/wardrobe/README.md Outfits section. No port change.

## Manual steps
- Deploy with `scripts/deploy-idea.sh wardrobe-outfits`. It rebuilds the image and reinstalls cron on drift, which adds the 07:00 entry.
- Open `/profile`: set lat/lon for the forecast (optional; without them the month is used) and tick "Daily Discord line" if wanted (off by default).
- Then requeue wardrobe-gaps (parked, waiting on this).

## Review notes
1. /home/dan/homelab/.worktrees/wardrobe-outfits/tools/wardrobe/app/outfits.py:945-946: when every combination is excluded by a down-vote or by today's key, the message says "No combination passes the colour and style rules", which is wrong. In a tiny wardrobe, one 👎 on the only outfit leaves Dan with nothing to wear, a misleading reason, and no button to undo the vote because the outfit is no longer shown. A separate reason for this case would help, e.g. "Every combination is thumbed down".
2. /home/dan/homelab/.worktrees/wardrobe-outfits/tools/wardrobe/app/main.py (worn_page): the "Never worn" list uses `build_pool`, so it leaves out pending/failed items and accessories. The plan says "owned active items". Leaving out accessories makes sense, since outfits never include them, but the README could say so.
3. weather.py `fetch`: urllib's 10 s timeout covers each socket operation, not the whole request, and does not cover the DNS lookup. A slow resolver or a server that trickles data could hold the first `/outfits` request of the day for longer than 10 s. It never causes a 500 and only happens once per date.
4. main.py profile_save: `rd.isdigit()` accepts characters such as "²", and `int()` then raises, giving a 500 instead of the 400 message. A cosmetic edge case.
5. Voting on an "Another" pick redirects to `/outfits`, which shows the daily outfit again, so the alternative disappears from view. Small UX gap. Also, SQLite can reuse the id of the highest deleted item, so old votes or wear rows could attach to a new item. This is rare.

## Declined to judge
- The `scripts/idea.sh diff` output reverts backup.sh, docs/m4-backups.md and ideas/done/backup-pause-jelu-wardrobe.md: this is only because the branch is based on 09a8dfe, before the backup-pause merge (46fff77). The diff against the merge base doesn't touch these files, so the merge keeps main's version.
- No CSRF or login on the vote/wear/delete POSTs: the app has had no login since stage 1, which the README documents. Not in this plan's scope.
- I could not smoke-test the routes (FastAPI is not installed on the host). I checked the route logic by reading it, and ran the unit tests on the pure modules.
