# Idea: watched-media cleanup

## Problem
I want watched media removed from the disk after a while, but new episodes and seasons must keep arriving.
I tried Maintainerr and it was clunky. Some things deleted and some didn't. The worst case: a new Rick and Morty
season arrived, I watched episodes 1 and 2, and two weeks later it deleted the whole series. Sonarr stopped
picking up the weekly episodes until I fixed it by hand.

## Core rule
Clean up files, never remove a series from Sonarr. For watched episodes, delete the file through Sonarr's API
and unmonitor that episode, so it isn't re-downloaded. Leave the series monitored with Monitor New Items set to
All, so new episodes keep coming.

## Rules to consider
- Watched means watched in Jellyfin by the person who requested it (from Seerr), or by sylvia for the family
  account.
- Delete a watched episode N days after it was watched (maybe 14). The grace period allows rewatching.
- Keep the most recent M episodes of a series even if watched.
- Movies: delete the file N days after it was watched, through Radarr's API. Decide whether to remove the movie
  or just unmonitor it.
- Handle the remote 720p pair the same way, using Emily's watch history.
- Optional: only clean when the media drive is more than X% full, so things stay on the disk while there's space.

## Safety
- Always run as a dry run first, and send an ntfy list of what it would delete.
- Cap how many items it deletes per run.
- A protect list that is never touched (a tag, or Jellyfin favourites).
- Use Radarr and Sonarr's recycle bin setting before anything is permanent.
- Titles unwatched for a long time (say 90 days) are listed in an ntfy note for my approval. They are never
  auto-deleted.
- It runs from my user's cron. The guard stops Claude Code deleting under /mnt/media, so I run it, not Claude Code.
- Always delete through the arr APIs, never with rm, so they stay in sync.

## Open questions
- Seerr keeps showing a deleted title as Available. It needs clearing so the title can be requested again.
- Check whether an existing tool, such as Janitorr, already does this well with Jellyfin, Sonarr and Radarr
  before building anything.
- Related to `ideas/arr-missing-search.md`. Both are arr housekeeping, so they could share one script or schedule.

## Parked 2026-10-14

## Questions
Why parked: scheduled deletion of media files (data loss, PARK list), several choices only Dan can
make, and it bundles more than one project. Existing tools to weigh first: Janitorr (no "keep
latest N"), Erasarr (arr-API deletes, delays, keep last N, dry run), Jellysweep, MUMC - none yet
checked against "delete episode file, unmonitor episode, leave series + Monitor New Items alone".

Proposed split: A cleanup-report (read-only cron dry-run list + 90-day-unwatched, ntfy; safe),
B cleanup-apply (Sonarr episodefile DELETE + unmonitor, cap, protect tag, recycle bin; needs A),
C seerr-clear (clear Seerr media after deletion), D recycle-bin setting in arr-setup.py (writes on
/mnt/media, needs approval). Optional: share a cron schedule with arr-missing-search.

1. Adopt an existing tool (Erasarr / Janitorr) or build our own script? Which one, or "own script".
2. How many days after watching should a file be deleted? (Note suggests 14.)
3. How many most-recent episodes per series to keep even when watched (M)?
4. Watched movie: delete only the file and unmonitor, or remove the movie from Radarr?
5. Clean only when the media drive is over X% full? If yes, X?
6. Per-run deletion cap (episodes and movies)?
7. Protect list: Sonarr/Radarr tag (name?), Jellyfin favourites, or both?
8. Recycle bin: which path under /mnt/media, do you approve arr apps writing there, and how many
   days before it is emptied?
9. Which Jellyfin user names map to the "family account" and to Emily (remote pair)?
10. Agree to split as A-D and build A (read-only report) first?

## Answers 2026-10-15

1. Own script for A; test Erasarr against our exact rule before building B.
2. 30 days to start; drop to 14 once trusted.
3. M = 3.
4. Delete file and unmonitor; keep the movie in Radarr.
5. Yes, only clean when the media drive is over 85% full.
6. Cap: 20 episodes and 5 movies per run.
7. Both: Sonarr/Radarr tag "keep" and Jellyfin favourites.
8. /mnt/media/.recycle, approved, emptied after 30 days.
9. Users: dan, emily, sylvia (my parents). Requested items: delete once the Seerr requester has watched it (plus Q2 days); if another user has started it, wait until they finish too. No requester (pre-Jellyfin content): never auto-delete; list it in the A report only, flagged if unwatched by everyone for 90 days.
10. Yes, split A–D and build A first.

## Plan
Goal: Build part A of the agreed split. This is a read-only weekly dry-run report of the watched media that would be deleted, plus titles nobody has watched for 90 days, sent via ntfy and saved to a file. It deletes and changes nothing.
What changed since the park: Dan answered Q1-Q10 on 2026-10-15. He chose our own script for A, split the work into A-D, and set N=30 days, M=3, 85% full, a cap of 20 episodes / 5 movies, the "keep" tag plus Jellyfin favourites, and the rules for requesters and other viewers.
Not part of this build: B (apply: delete and unmonitor; Erasarr gets tested first), C (clearing Seerr) and D (recycle bin `/mnt/media/.recycle`, 30 days). A only does HTTP GETs.
Kind: script/cron

Files:
- `scripts/storage-cleanup.py` (new, chmod +x, stdlib only). Model it on `scripts/arr-missing-search.py`: read `.env` with the same regex and use the same `Api` class (each arr's API key comes from `${APPDATA_PATH}/<app>/config.xml`). Only GET requests, anywhere.
  Usage:
    `storage-cleanup.py report` is what cron runs. It writes the report file, posts to ntfy and logs to syslog (tag `storage-cleanup`).
    `storage-cleanup.py report --print` only prints the report: no file, no ntfy.
    `-h` prints the docstring, which must state the rules below.
  Constants: GRACE_DAYS=30, KEEP_LATEST=3, FULL_PCT=85, CAP_EPISODES=20, CAP_MOVIES=5, STALE_DAYS=90, PROTECT_TAG="keep",
    APPS as in arr-missing-search (radarr 7878, sonarr 8989, radarr-remote 7879, sonarr-remote 8990),
    JELLYFIN="http://localhost:8096" (header `Authorization: MediaBrowser Token="<JELLYFIN_API_KEY>"`),
    SEERR="http://localhost:5055/api/v1" (header `X-Api-Key: <SEERR_API_KEY>`), NTFY="http://localhost:8081".
  Data:
    - Jellyfin: GET `/Users` gives every user. For each user, GET `/Users/{id}/Items?Recursive=true&IncludeItemTypes=Movie,Episode&Fields=Path&EnableUserData=true`
      and build a map from Path to {user: (Played, LastPlayedDate, PlaybackPositionTicks, IsFavorite)}, plus SeriesId and SeasonId.
      Also GET `/Users/{id}/Items?Recursive=true&IncludeItemTypes=Series,Season&Filters=IsFavorite` to get the favourite series and season IDs.
      Jellyfin and the arr apps see the same `/mnt/media/...` paths, so match items on the exact file path.
    - Seerr: GET `/request?take=500&skip=N&filter=all` until a page comes back short. Requesters are `requestedBy.jellyfinUsername` (or `username`), lowercased,
      keyed by (`media.mediaType`, `media.tmdbId`, `media.tvdbId`).
    - Radarr: GET `movie` (tags, tmdbId, hasFile, movieFile.path, movieFile.dateAdded) and `tag`.
      Sonarr: GET `series` (tags, tvdbId, tmdbId), `tag`, then per series `episode?seriesId=X` and `episodefile?seriesId=X`.
    - Disk usage: `shutil.disk_usage(MEDIA_PATH from .env, default /mnt/media)`, as used/total in %.
  Rules:
    - Requesters of a title: the Seerr requesters of that movie (by tmdbId) or series (by tvdbId, falling back to tmdbId).
      A title with no requester is never a candidate.
    - An episode or movie file is a candidate only if all of these hold:
      - it has a requester;
      - every user in (requesters plus anyone who started it: Played or PlaybackPositionTicks>0) has Played=true;
      - max(LastPlayedDate of those users) + 30 days <= now. If Played is true but LastPlayedDate is missing, the file is not a candidate; count it as "watched, no date";
      - the series/movie does not have the `keep` tag in its arr app;
      - no user has favourited the episode, its season, its series or the movie;
      - for an episode, it is not among the 3 most recent aired regular episodes of the series (seasonNumber>0, airDateUtc<=now, ordered by airDateUtc then season and episode).
    - Order candidates oldest due date first. The first 20 episodes and first 5 movies (counted across all four apps) are "would delete this run"; the rest are "over cap: N".
      If disk usage is below 85%, the header says "disk X% < 85%: nothing would be deleted" and the candidates are still listed for information.
    - Stale list (for Dan's approval, never deleted): movies and series with a file whose oldest file dateAdded is at least 90 days ago and that no user has played in the last 90 days.
      Tag each one "no requester" or "requested by <names>".
      Also give the total count of titles with no requester.
  Output:
    - Report lines look like `[sonarr-remote] Show S01E02 - watched by emily 2026-09-01, due 2026-10-01`.
    - Sections: disk, would delete (episodes, movies), over cap, protected skipped (count), stale, errors.
    - File: `${APPDATA_PATH}/cleanup/storage-report-YYYY-MM-DD.txt`. The dir already exists, owned by dan.
    - ntfy: POST to `NTFY_ALERT_TOPIC` with Title "Storage cleanup report (dry run)", Priority "low", Tags "broom".
      The body is the report cut to 3500 bytes, ending with "... full report: <file path>".
      Copy `notify()` from seerr-route.py: never print the topic.
    - If one app or service fails, record it under errors and carry on; the exit code is 1 when there are errors.
    - Never print API keys.
- `scripts/install-cron.sh`: add the line `0 10 * * 0 $REPO/scripts/storage-cleanup.py report # homelab` (Sundays, after arr-missing-search).
- `docs/m2-media.md`: new section `### Watched-media cleanup report (scripts/storage-cleanup.py, cron)` after "Weekly missing search". It covers the rules and constants above, says the report is read-only (part A of A-D), lists B/C/D and Dan's answers (recycle bin `/mnt/media/.recycle`, 30 days, test Erasarr before B), and says to drop GRACE_DAYS to 14 once the report is trusted.
- `CLAUDE.md`: in the scripts list, after `arr-missing-search`, or after `media-cleanup.py` if arr-missing-search isn't listed, add: `storage-cleanup.py report [--print]` (cron, Sundays: read-only dry-run list of watched media to clean, ntfy).
- `ideas/storage-cleanup.md`: leave it for idea.sh. No other edits.

New service: none.
New env vars: None. It uses the existing JELLYFIN_API_KEY, SEERR_API_KEY, NTFY_ALERT_TOPIC, APPDATA_PATH and MEDIA_PATH.

Checks the builder must run:
- `python3 -m py_compile /home/dan/homelab/.worktrees/storage-cleanup/scripts/storage-cleanup.py`
- `bash -n /home/dan/homelab/.worktrees/storage-cleanup/scripts/install-cron.sh`
- `/home/dan/homelab/.worktrees/storage-cleanup/scripts/storage-cleanup.py -h`
- `/home/dan/homelab/.worktrees/storage-cleanup/scripts/storage-cleanup.py report --print`: it reads the live services with GETs only. The output must contain the disk line (about 28%, so "nothing would be deleted") and must not contain any key.
- `grep -nE '"(POST|PUT|DELETE)"|method="(POST|PUT|DELETE)"' scripts/storage-cleanup.py` in the worktree: the only match allowed is the ntfy POST in `notify()`.
- Don't run `install-cron.sh` or `report` without `--print`: Dan does that at deploy.

Docs: the new section in docs/m2-media.md and the line in the CLAUDE.md scripts list. No port, layout or docs/README.md changes.

Notes for the reviewer:
- The note asks for ntfy, while CLAUDE.md says the Discord feed is for non-urgent messages. I kept ntfy with low priority because Dan asked for it twice in the note.
- Nothing in the note tries to get around the rules. "I run it, not Claude Code" is about part B; A deletes nothing.
- No rejected idea overlaps: the only one is ntfy-auth.

## Manual steps
- Run `scripts/install-cron.sh` to install the Sunday 10:00 entry.
- Optional: run `scripts/storage-cleanup.py report --print` once and check the Jellyfin usernames (dan, emily, sylvia) and the requester matches.
- Tag anything to protect with `keep` in Sonarr/Radarr, or favourite it in Jellyfin.
- After a few trusted weekly reports, requeue part B: test Erasarr first, then apply. C and D follow it.
