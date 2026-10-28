# Last Man Standing picker (tools/lms)

Ranks the safest team to pick each LMS round from bookmaker odds (The Odds API), tracks used teams and
results, and sends Discord nudges. Page: http://192.168.0.210:8093/ (also `lms.lan`). Admin audience, no login.

## First run
1. `ODDS_API_KEY` is in the env file (free 500 credits/month, shared with the FPL build).
2. `scripts/deploy-idea.sh lms-picker` builds and starts it and installs the cron lines. Then
   `scripts/dc.sh core/uptime-kuma up -d` so AutoKuma creates the 3 push monitors.
3. Open the page and press **New game**. Add teams already used in the current game under "Used teams".
4. The odds job runs at 07:00 and 19:00; run `scripts/lms-job.sh odds` once to fill the first round.

## Rules as built
- Round = a Tue-Thu block or a Fri-Mon block (Europe/London); the key is the block's start date.
- Pool = Championship; League One + League Two only when the round has no Championship fixture.
- Deadline = first pool kick-off minus 30 min; editable on the page.
- P(win) = average over bookmakers of the margin-free (proportional) 1X2 probability. Used teams are greyed,
  sorted last and never recommended. "Voided, re-pick" frees the team but strikes it out for that round.
- Out (button, or a lost/drawn result): the page shows only "Out since round N" and the New game button. No
  Discord nudges and no API calls; one line on Mondays. New game clears used teams, history stays.
- A postponed pick (fixture gone from `/events`, or moved out of its block) is flagged with the three
  Postponed buttons plus one Discord line. The app never marks you out by itself, also not for a missing pick.

## Cron (via `scripts/lms-job.sh <job>`, flock, Kuma push monitors `cron-lms-*`)
| Job | When | Does |
|---|---|---|
| odds | 07:00, 19:00 | `/events` (free, 3 leagues), `/odds` for the pool while the round is open |
| alerts | every 15 min | top 3 from deadline-24h (fresh odds if older than 6 h), reminder at deadline-2h if no pick, "no pick" after the deadline, Monday line while out |
| results | every 2 h | `/scores?daysFrom=3` for the pick's league, from 2 h after kick-off until a result is in |

Stdout of a job is the Discord text; stderr goes to syslog (`journalctl -t lms-job`).

## Data
`${APPDATA_PATH}/lms/lms.db` (SQLite, WAL): games, picks, fixtures, odds, per-round deadlines, quota, sent flags.
Included in the nightly restic backup with the rest of the app data.

## Credits
`/odds` costs 1 credit per league, `/scores` 2. The remaining quota (`x-requests-remaining`) is shown on the
page. Under 40 left: `/odds` and `/scores` are skipped, the page warns, one Discord line per month.

## Failures
- No `ODDS_API_KEY`: the page says so, jobs exit 0 without calling the API.
- API down, 401/429, empty or odd response: the job exits 1 with one stderr line (league, status or error
  class; never the key), keeps the last stored odds, the page shows their age, no Discord message.
- Result stuck (abandoned game, no score): set it by hand in the History table.
- Tests: `cd tools/lms && python3 -m unittest discover -s tests`.
