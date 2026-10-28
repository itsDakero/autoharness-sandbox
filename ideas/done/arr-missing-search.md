# Weekly re-search for monitored titles that are still missing

Radarr and Sonarr search once, when a title is added; after that they only watch the indexers' RSS feeds of new
uploads. A request that finds nothing at first is never searched again, and older episodes/films rarely show up
in RSS. Seen 2026-10-05: Supergirl (radarr-remote) and The Rookie S08 (sonarr-remote) were added 15 minutes before
Prowlarr synced indexers to the remote pair; the add-time search ran with "0 active indexers" and nothing ran
again for a day. The Odyssey (main Radarr) will hit the same gap after its digital release on 2026-11-15 if
nothing new appears in RSS that day.

## Idea
- `scripts/arr-missing-search.py`, weekly cron via `install-cron.sh`, for all four apps (main + remote pairs).
- Picks monitored items that are released but have no file:
  - Radarr: `/wanted/missing` (monitored, `isAvailable` – respects each movie's minimum availability).
  - Sonarr: `/wanted/missing` (monitored episodes whose air date has passed); search per season when several
    episodes of one season are missing (`SeasonSearch`), else `EpisodeSearch`.
- Skips anything searched recently (`lastSearchTime` within 7 days) and anything already in the queue.
- Capped per app per run (e.g. 10 movies / 10 seasons), oldest search first, so a big backlog doesn't hammer
  the indexers; the rest waits for next week.
- Sends one ntfy note (low priority, not the urgent alert topic) listing what it searched per app, plus how many
  were left for next time. Results (grabs/rejections) stay in the arr apps' history.
- `--dry-run` prints the plan without starting searches. Read-only apart from the search commands; never changes
  monitoring, profiles or indexers.

## Built-in options (checked 2026-10-05: Radarr 6.4.4, Sonarr 4.0.20, all four instances)
- Neither app can schedule its own search for missing items. Their scheduled tasks are only housekeeping, refresh
  (metadata only, no search), download tracking and RSS sync; the only search-related setting is the RSS interval.
- The only built-in option is the manual Search All Missing button (Wanted → Missing). It searches every missing
  item at once, with no cap and no skip for recently searched items, so the weekly script is still needed.

## Open points
- Which ntfy topic, and whether the note should skip weeks where nothing was searched.
- Run time: night, outside the qBittorrent evening limit window.

## Plan
Goal: A weekly cron script that re-searches monitored, released titles that still have no file, in all
four arr apps. Each run is capped per app and skips anything searched in the last 7 days.
Kind: script/cron

Decisions on the note's open points (taken from repo conventions, so Dan does not need to answer):
- Notification: the Discord feed via `scripts/discord.sh`, not ntfy. The note was written on 2026-10-05,
  before M5 stage B, which made Discord the non-urgent feed. There is only one ntfy topic,
  NTFY_ALERT_TOPIC, and it is the urgent one that the note itself rules out. A post is sent only when
  something was searched or an app errored. A week with nothing to do logs to syslog only.
- Run time: Sunday 02:30, `30 2 * * 0`. This is outside the qBittorrent limit window (19:00-23:59) and
  before the 04:00 restic backup.
- The note contains no instructions that break repo rules.

Files:
- scripts/arr-missing-search.py (new, executable, `#!/usr/bin/env python3`, stdlib only)
  - Docstring in the style of seerr-route.py: purpose, the cron schedule, that it logs to syslog
    (`journalctl -t arr-missing-search`), that it posts to Discord, and usage:
      scripts/arr-missing-search.py               # search + Discord post (what cron runs)
      scripts/arr-missing-search.py --dry-run     # print the plan, start nothing, post nothing
      scripts/arr-missing-search.py [--dry-run] radarr sonarr-remote   # only these apps
  - Apps: APPS = {"radarr": ("radarr", 7878), "sonarr": ("sonarr", 8989),
    "radarr-remote": ("radarr", 7879), "sonarr-remote": ("sonarr", 8990)}. Base URL is
    http://localhost:<port>/api/v3.
  - Constants: CAP = 10 (per app per run), RECENT = 7 days, PAGE = 1000.
  - API key: read from `/srv/homelab/<name>/config.xml` (APPDATA_PATH from .env, default /srv/homelab),
    the same way as the arr-setup.py `Api` class (regex `<ApiKey>([^<]+)</ApiKey>`). Never print or log it.
    Send it in the `X-Api-Key` header. Timeout 30 s.
  - Errors: an HTTPError or OSError for one app is recorded as "<app>: <method> <path> -> <error>"
    (truncate the body to 200 characters, never include the key). The script then goes on to the next app.
  - Only these calls:
    - GET wanted/missing?page=N&pageSize=1000&monitored=true (add `&includeSeries=true` for Sonarr).
      Page until all totalRecords are read.
    - GET queue?page=N&pageSize=1000 (Radarr: collect `movieId`; Sonarr: collect `episodeId`).
      Page the same way.
    - POST command, used only when not --dry-run.
    No other writes. Never PUT or DELETE anything.
  - Radarr selection: keep records where `isAvailable` is true, `monitored` is true, `hasFile` is false,
    the id is not in the queue, and `lastSearchTime` is null or older than 7 days. Live data: The Odyssey
    currently has isAvailable=false and must be skipped. Sort with null lastSearchTime first, then oldest
    lastSearchTime, then title. Take the first 10.
    Post ONE command: {"name": "MoviesSearch", "movieIds": [...]}.
    Label for each movie: "Title (year)".
  - Sonarr selection: keep episodes where `monitored` is true, `airDateUtc` is set and <= now (UTC),
    `hasFile` is false, the id is not in the queue, and `lastSearchTime` is null or older than 7 days.
    Group them by (seriesId, seasonNumber). A group of 2 or more is a season unit: one command
    {"name": "SeasonSearch", "seriesId": S, "seasonNumber": N}, labelled "<series.title> S<NN> (<k> eps)".
    A group of 1 is an episode unit. Combine all chosen episode units into ONE command
    {"name": "EpisodeSearch", "episodeIds": [...]}, each labelled "<series.title> S<NN>E<NN>".
    Sort units by their oldest lastSearchTime (null first), then by earliest airDateUtc. Take the first
    10 units.
  - Between POSTs, sleep 2 s.
  - Leftover count per app = eligible items not taken this run (movies for Radarr, units for Sonarr).
  - Output: for each app, one line "<app>: searched <n> (<labels, comma-joined>), <m> left for next week",
    or "<app>: nothing to search". Errors are listed after the app lines.
    - With --dry-run: print to stdout and do nothing else.
    - Otherwise: syslog every line, using `syslog.openlog("arr-missing-search")`, and print as well when
      stdout is a tty. Then, if any app searched more than 0 items or there were errors, call
      `subprocess.run([REPO/"scripts/discord.sh", msg])` with
      msg = "Weekly missing search:\n" + the lines. Cap each app's label list at 300 characters with
      "..." so the message stays under Discord's 2000-character limit.
  - Exit code is 1 if any app errored, otherwise 0.
- scripts/install-cron.sh: add the entry
  `30 2 * * 0 $REPO/scripts/arr-missing-search.py # homelab` to ENTRIES as the last line.
- CLAUDE.md: in the Layout `scripts/` list, after `seerr-route.py (...)`, add
  "`arr-missing-search.py` (cron, weekly: re-search missing monitored titles in all four arr apps,
  capped; Discord summary)".
- docs/m2-media.md: add a new section "### Weekly missing search (`scripts/arr-missing-search.py`, cron)"
  after the "### Naming (new imports)" section, ending before "## Stage D". It covers:
  - why: an add-time search runs once, then only RSS. Example from 2026-10-05: titles were added before
    Prowlarr synced indexers, so the search ran with 0 indexers;
  - the schedule (Sundays 02:30), the selection rules, the cap of 10 per app with oldest searched first,
    and the 7-day skip;
  - Season vs Episode search;
  - that it posts to Discord only when something was searched or failed, and logs to
    `journalctl -t arr-missing-search`;
  - the `--dry-run` usage and the app-name arguments;
  - that results stay in each app's History, and that it never changes monitoring, profiles or indexers.

New service: None
New env vars: None. Discord uses the existing DISCORD_WEBHOOK_URL through discord.sh, and API keys come
  from config.xml.

Checks the builder must run:
- python3 -m py_compile /home/dan/homelab/.worktrees/arr-missing-search/scripts/arr-missing-search.py
- bash -n /home/dan/homelab/.worktrees/arr-missing-search/scripts/install-cron.sh
- test -x /home/dan/homelab/.worktrees/arr-missing-search/scripts/arr-missing-search.py
- /home/dan/homelab/.worktrees/arr-missing-search/scripts/arr-missing-search.py --dry-run
  (read-only GETs against the live apps). Expected: radarr does not list The Odyssey; radarr-remote
  reports nothing to search; no app lists more than 10; no Discord post; exit 0.
- Do NOT run it without --dry-run (that starts real searches), and do NOT run install-cron.sh
  (it changes the live crontab). Both are Dan's deploy steps.

Docs: the CLAUDE.md scripts line and the docs/m2-media.md section above. No port table change and no
  new doc, so docs/README.md is unchanged.

## Manual steps
- After the merge, run `scripts/install-cron.sh` as dan (no root) to install the Sunday 02:30 entry.
  Check it with `crontab -l | grep arr-missing`.
- Optional: run `scripts/arr-missing-search.py --dry-run`, then a real run, and look for the Discord post
  and the searches in each app's Activity / History.
