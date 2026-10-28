# Weekly Jellyfin watch stats to Discord

## Problem
Nothing shows what actually gets watched on Jellyfin. `scripts/jellyfin-library-check.py` only checks that the
libraries are present and being scanned, and the storage cleanup report only lists watched media to delete. A
short weekly summary would show whether the remote pair and the family are using the server, what's popular
and what never gets played, which helps with requests and cleanup.

## Proposal
`scripts/jellyfin-watch-stats.py`, a weekly cron job (Sundays 20:00, after the fitness summary at 19:00).
It follows the cron rules: `scripts/cron.d/jellyfin-watch-stats.cron` wrapped in `scripts/cron-run.sh`, plus
`core/uptime-kuma/compose.d/cron-jellyfin-watch-stats.yaml`.
- Read-only GETs against `http://localhost:8096`, with `JELLYFIN_API_KEY` read from `.env` the same way
  `jellyfin-library-check.py` does it (never printed).
- Covers the last 7 days of plays, from the activity log (`/System/ActivityLog/Entries`, playback
  start/stop entries) or from the Playback Reporting plugin if that's installed (see open points).
- One Discord post via `scripts/discord.sh` (the feed, not ntfy). It has:
  - Totals: plays, hours watched, number of active users.
  - Per user: plays and hours.
  - The top 5 films and top 5 series (episodes rolled up into their series).
  - New this week: titles added to each library, and how many of those have been played.
  - The split between the main libraries and the remote (720p) libraries.
- A quiet week (no plays) still sends one short line, so a broken script is easy to spot.
- `--dry-run` prints the message and posts nothing. Jellyfin unreachable: logged, exit 0 (its own Kuma
  monitor alerts). Missing key: exit 2.

## Open points
- Data source: the core activity log has play start/stop events but no clean durations. The Playback
  Reporting plugin keeps proper per-play time. Installing it would mean a pinned plugin in
  `scripts/jellyfin-setup.py plugins`, next to Intro Skipper. Is that worth it, or are play counts enough?
- Privacy: should per-user lines name family members and the remote users, or just show totals?
- Day and time of the post.

## Checks
`python3 -m py_compile`, then `--dry-run` against the live server shows a sensible week. Add the script to
`scripts/README.md` (alphabetical) and a line to `docs/m2-media.md`.

_Added by Claude in the terminal for Dan, 2026-10-28._
