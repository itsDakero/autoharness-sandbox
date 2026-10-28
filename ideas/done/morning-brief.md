# Morning brief at 07:00 on Discord

Value: 4   (one daily message instead of several apps; the first proactive assistant habit)
Effort: 2  (extends wardrobe-daily.sh and reads the personal feed)
Risk: 1    (read-only; one Discord post a day)
Score: 16
Source: claude 2026-10-25 (reports/Homelab autonomy and assistant gaps.md, roadmap #5)
Depends on: hermes-personal-feed (it reads `personal.json`). Park if that isn't built yet.

## Problem
`scripts/wardrobe-daily.sh` posts only the outfit at 07:00. Readiness, illness warnings, deal hits, card
drops and "anything broken overnight" are spread across apps and alerts.

## Proposal
- Replace `wardrobe-daily.sh` with `scripts/morning-brief.sh` (or .py) at 07:00, same cron slot, built from
  the dashboard's `personal.json` and `status.json`: outfit (only when the wardrobe toggle is on, as today),
  readiness + illness warning, yesterday's activity, deal/card hits since yesterday, services down or
  unhealthy, and anything waiting for Dan (Parked/Deploy/Proposed counts).
- Plain template, no model call: fast and works when the Mac mini is off. Sections with nothing to say are
  left out; one Discord message, under Discord's 2000-char limit.
- A toggle to turn the brief off (env var or a setting in the dashboard's admin), and `test` argument
  posts one to Discord now.

## Notes
- Keep the wardrobe's 204-means-off behaviour for the outfit line.
- An LLM-written version can come later, once the memory plan says there's room.

## Parked 2026-10-25

## Questions
1. The note says "Depends on: hermes-personal-feed ... Park if that isn't built yet." It has been built and reviewed on branch `idea/hermes-personal-feed` (commit dd77e5e, adds `core/dashboard/app/personal.py`, which writes `personal.json`), but it isn't merged to main yet, so the morning-brief worktree has no `personal.json` code or schema to read. Will you deploy it (`scripts/deploy-idea.sh hermes-personal-feed`) and then requeue morning-brief? Planning it now would mean building against an unmerged branch whose format could still change or be rejected.
2. When it's requeued, how should the brief be switched off: an env var (e.g. `MORNING_BRIEF_ENABLED`, flipped by editing the env file) or a toggle in the dashboard's admin (more work: a setting the cron script reads)?
3. Should `scripts/wardrobe-daily.sh` and its 07:00 cron line be deleted once the brief replaces them, or kept as a fallback with only the cron line removed?

Notes for the replan: today's `scripts/wardrobe-daily.sh` treats 204 as off, posts on 200 with a non-empty body, and on anything else writes only to syslog. Its cron line is `scripts/install-cron.sh:22` (`0 7 * * *`). The branch's review note flags one weak spot: `personal.py` can null the whole "watches" (deals) block when one `last_changed` value is odd. The brief should leave that section out rather than fail.

## Answers 2026-10-25

1. hermes-personal-feed is deployed (merge 33d942a): `core/dashboard/app/personal.py` and `personal.json`
   are on main. Plan against main.
2. Off switch: an env var, `MORNING_BRIEF_ENABLED` (add it to `.env.example`, default on when unset; `0`
   turns the whole brief off). The outfit section keeps following the wardrobe profile's daily toggle,
   as `wardrobe-daily.sh` does today (204 = leave the outfit out, not the brief).
3. Delete `scripts/wardrobe-daily.sh` and its 07:00 line in `scripts/install-cron.sh` once the brief
   carries the outfit; git history is the fallback. Replace the `cron-wardrobe-daily` Kuma push monitor
   with `cron-morning-brief`, and update the CLAUDE.md scripts list.

## Plan
Goal: A 07:00 Discord brief built from the agent feed (outfit, fitness, yesterday's run, deals, services, waiting items) replaces wardrobe-daily.sh. Dan answered the earlier park on 2026-10-25: hermes-personal-feed is on main, the off switch is `MORNING_BRIEF_ENABLED`, and wardrobe-daily.sh gets deleted.
Kind: script/cron
Files:
- scripts/morning-brief.py: new, executable, Python stdlib only (details below)
- scripts/wardrobe-daily.sh: delete (`git rm`)
- scripts/install-cron.sh: replace the line `0 7 * * * $R wardrobe-daily 600 $REPO/scripts/wardrobe-daily.sh # homelab` with `0 7 * * * $R morning-brief 600 $REPO/scripts/morning-brief.py # homelab`
- core/uptime-kuma/compose.yaml: swap the 4 `kuma.cron-wardrobe-daily.push.*` labels for `kuma.cron-morning-brief.push.name=cron-morning-brief`, `.push_token=${KUMA_CRON_PUSH_SECRET:-}morningbrief0000`, `.interval=93600`, `.max_retries=0` (AUTOKUMA__ON_DELETE=delete removes the old monitor)
- .env.example: after `DISCORD_WEBHOOK_URL=`, add a comment line ("Morning brief (scripts/morning-brief.py, 07:00): 0 = off; unset or anything else = on") and `MORNING_BRIEF_ENABLED=`
- CLAUDE.md: in the scripts list, replace the `wardrobe-daily.sh (...)` entry with `morning-brief.py [test|--print]` (cron 07:00: one Discord brief from the dashboard's agent feed: outfit when the wardrobe toggle is on, readiness/illness, yesterday's activity, deals, services not up, items waiting for Dan; `MORNING_BRIEF_ENABLED=0` turns it off)
- tools/wardrobe/README.md: in "Daily Discord line" and the "Failures" lines, change `scripts/wardrobe-daily.sh` and `journalctl -t wardrobe-daily` to `scripts/morning-brief.py` (the outfit line in the brief) and `journalctl -t morning-brief`
- docs/mac-mini.md (about line 258): change "`wardrobe-daily.sh` (07:00)" to "`morning-brief.py` (07:00)"
- docs/m6-research.md: below the "### Personal feed" paragraph, add "### Morning brief": a 3-5 line paragraph covering what it reads, the toggle, `test`/`--print`, the stale rules and the log tag

scripts/morning-brief.py:
- Usage: `morning-brief.py` (cron), `morning-brief.py test` (post now, ignoring the toggle), `--print` (print to stdout, no post), `--feed-dir <dir>` (default `$APPDATA_PATH/dashboard/agent-feed`).
- APPDATA_PATH and MORNING_BRIEF_ENABLED come from os.environ first, then from the repo env file, using the line-regex `env()` reader from storage-cleanup.py (read only these two names; never print the file). Defaults: `/srv/homelab` and on.
- Off (`MORNING_BRIEF_ENABLED` == "0", and not `test` or `--print`): write one syslog line and exit 0.
- Log to syslog with tag `morning-brief` (`syslog.openlog("morning-brief")`), and also to stdout when it's a tty.
- Message (plain text; each section only when it has content):
  1. `**Morning brief, Mon 26 Oct**`
  2. Outfit: a live GET to `http://127.0.0.1:8091/api/daily.txt` (urllib, 60 s timeout). 204 = no line. 200 with a non-empty body = `Outfit: <body>`. Anything else = no line, plus a syslog line.
  3. Fitness, from personal.json `fitness.data`, only when `data.date` == today: put `Illness warning: <readiness/recovery>, take it easy` first when `illness_warning` is true. Then one line: `Readiness 83 (High) · recovery 55 · form Fresh`, leaving out each null part.
  4. Yesterday: `last_activities` entries whose `date` is yesterday, as `Yesterday: running 10.1 km, 52 min`, joined with "; ". None = no line.
  5. Deals: `deals.data.watches` entries whose `last_changed` (ISO) is within the last 24 h, as `title`, and `deals.data.card_drops` whose `alerted` date is today or yesterday, as `name (set) low €x`. Show at most 5 of each, then "and N more". If either list is null, or `deals.data` is null, skip that part without failing.
  6. Services: status.json `services` whose `status` isn't `up` or `maintenance`, as `Not up: Name (down), ...`. If `kuma_reachable` is false: `Service status unknown: Kuma unreachable`.
  7. Waiting: `ideas.parked`, `ideas.ready_to_deploy` and `ideas.proposed` lengths, as `Waiting: 2 parked, 4 to deploy, 1 proposed` (zeros left out; no line when all are zero). Add the link `http://192.168.0.210/admin`.
  If no section has anything: `All quiet.`
- Feeds: a missing, unreadable or malformed file, or a top-level `updated` older than 2 h (personal.json) or 15 min (status.json), means that file's sections are skipped and one line is added: `Personal feed stale (updated 03:10)` or `Status feed missing`. Any odd type inside a block is caught per section and logged; one bad block never stops the post.
- Length: keep the message ≤ 1900 chars by dropping whole lines from the end and adding `…`.
- Post with `subprocess.run([REPO/scripts/discord.sh, msg])`. A non-zero exit gets a syslog line. Always exit 0 after handling (only a real crash makes cron-run mark it down).
New service (if any): None
New env vars: MORNING_BRIEF_ENABLED: `0` turns the 07:00 brief off; unset = on
Checks the builder must run:
- `python3 -m py_compile scripts/morning-brief.py`; `bash -n scripts/install-cron.sh`
- `scripts/dc.sh <worktree>/core/uptime-kuma config -q`
- `scripts/morning-brief.py --print`, run against the live feed (read-only).
- `--print --feed-dir <scratch>` with: (a) no files; (b) a personal.json with `"deals": {"data": {"watches": null, "card_drops": []}}` and `fitness.data.date` = yesterday; (c) a status.json whose `updated` is 1 h old and with one service `down`; (d) a file containing `{` only. None of these may crash, and each must show the expected lines.
- `--print` with long fake data (60 services down) prints ≤ 1900 chars.
- `CRON_LIST=<scratch file holding the new ENTRIES> scripts/install-cron.sh --check` prints "cron: in sync".
- `grep -n wardrobe-daily` over CLAUDE.md, scripts/, docs/, tools/, core/: no hits left
Review focus:
- Wardrobe 204, app down or an empty 200 -> no outfit line; the rest of the brief still posts
- personal.json deals block null, or watches null (the review flag on hermes-personal-feed) -> that part left out, no traceback
- Feed files missing, half-written or hours old (dashboard down overnight) -> one "stale/missing" line, never yesterday's readiness shown as today's (date check)
- Many services down or many deals -> one message ≤ 1900 chars, never two posts
- Toggle `0` -> no post, exit 0 (the Kuma push stays up); `test` still posts
Docs: CLAUDE.md scripts list; tools/wardrobe/README.md daily-line and failures text; docs/mac-mini.md line 258; docs/m6-research.md new "Morning brief" paragraph. No port, layout or docs index change.

## Manual steps
- Optional: set `MORNING_BRIEF_ENABLED=0` in the env file to turn the brief off (unset = on).
- After the deploy (deploy-idea reinstalls cron on drift and restarts core/uptime-kuma for the labels), run `scripts/morning-brief.py test` once and check the Discord post. Also check that `scripts/kuma-status.py cron` shows `cron-morning-brief` and no `cron-wardrobe-daily`. If the monitor didn't change, run `scripts/dc.sh core/uptime-kuma up -d`.
- The outfit line still needs "Daily Discord line" ticked in the wardrobe's /profile, as before.

## Review notes
1. /home/dan/homelab/.worktrees/morning-brief/scripts/morning-brief.py:379-390: the feed notes ("Personal feed stale/missing") are added last, so when the message is too long they are the first lines cut. This follows the plan ("drop whole lines from the end"), and I could only make it happen with an absurd 3000-char activity line. In normal use the cap of 5 items per line keeps the message short: 60 services down plus 9 deals plus 7 card drops came to about 700 chars.
2. morning-brief.py:228-230: a file that is there but half-written gets the same "feed missing" line as a file that isn't there. That's fine for Dan, but "unreadable" would be more accurate. The syslog line already gives the cause (JSONDecodeError).
3. morning-brief.py:340: a status.json with `services` set to a string, or `ideas` set to a list, gives "All quiet." without a warning line. Both are caught and nothing crashes. The dashboard never writes those shapes.
4. `scripts/morning-brief.py` is staged with intent-to-add (git status shows " A"). Make sure the commit step stages the whole file.

## Declined to judge
- The host runs on UTC while the fitness feed's `date` uses the container's local day: at 07:00 UTC both give the same calendar day, and the old outfit-only job used the same timing.
- "Yesterday:" lists every activity type, not only runs: the plan says `last_activities` entries without filtering by type.
- I didn't run `test`, because it would post to Discord. I checked the post path by reading it: discord.sh is run with a 60 s timeout, a non-zero exit is logged, and the script exits 0.
