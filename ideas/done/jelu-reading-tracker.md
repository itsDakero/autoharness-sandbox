# Jelu reading tracker (the books half of books-deals-aggregator)

Value: 3   (Dan: read and to-read lists, progress and a yearly count without a custom build or Goodreads OAuth)
Effort: 2  (one off-the-shelf container plus a CSV import and trimming the queued note)
Risk: 1    (isolated new container with its own data dir; no media, no secrets beyond its own admin login)
Score: 12
Source: scout 2026-10-23

## Problem
`ideas/books-deals-aggregator.md` is still queued at Effort 4 / Risk 3 (Goodreads OAuth, which may change).
Its deals half already shipped as changedetection-deal-watch (57e4e22). The books half would have the loop
build a custom tracker and recommendation engine.

## Proposal
Run Jelu off the shelf instead: Goodreads CSV import (v0.88.2 fixes inconsistent Goodreads ISBNs, #355),
read/to-read lists, reading progress, an API, SQLite. No Goodreads API.
- `tools/jelu/compose.yaml`, image `wabayang/jelu:0.88.2` (pinned), data in `/srv/homelab/jelu` (restic
  already covers it), port **8089** (add to the CLAUDE.md port table), template labels (Traefik, dashboard
  with `homelab.audience=admin` or `family` as Dan prefers, AutoKuma), json-file log cap.
- No other mounts. First admin account made by hand; no open sign-up.
- Shrink `ideas/books-deals-aggregator.md` to what Jelu doesn't cover (or close it), so the loop doesn't
  build a custom tracker.
- Later, optional: a "books this year" dashboard widget from Jelu's API (separate idea).

## Existing tools checked
- Jelu (https://github.com/bayang/jelu): v0.88.2, last release 2026-10-07, about 750 stars, MIT, Docker Hub
  `wabayang/jelu`; fits: CSV import, SQLite, single container.
- changedetection.io (already running): covers the deals half.

## Rough plan
1. Compose from `templates/compose.yaml`, port 8089, data dir; confirm the container's data path and user
   from the Jelu docs; start and check Kuma.
2. Short `tools/jelu/README.md`: first login, Goodreads CSV export/import steps for Dan.
3. Edit the queued books-deals-aggregator note down to the remainder (or move it to done with a pointer).

_Approved on the dashboard, 2026-10-23._

## Plan
Goal: Run Jelu (an off-the-shelf reading tracker) as the books half of books-deals-aggregator, and park what's left of that note for Dan.
What changed: On 2026-10-19 Dan answered "Hardcover token + Goodreads CSV". On 2026-10-23 he approved this scout note, which uses Jelu with the Goodreads CSV import and no Hardcover, so the plan follows the newer approval. Nothing in ideas/rejected/ overlaps (only discord-hermes-agent and ntfy-auth are there).
Kind: new service (plus a note move)
Files:
- tools/jelu/compose.yaml: new, copied from templates/compose.yaml (details below)
- tools/jelu/README.md: new. Covers: admin only at http://192.168.0.210:8089 (also jelu.lan). Data lives in /srv/homelab/jelu (config, database, files/images, files/imports), which restic already backs up. First start: open the UI, create the first user (it becomes the admin) straight away, because until then anyone on the LAN can do it. Don't add other users. Goodreads: My Books > Import and export > Export Library, then in Jelu: Imports > upload the CSV. Imports are a one-off; re-export and re-import to refresh. Upgrades: bump the pinned tag.
- CLAUDE.md: add `| 8089 | jelu |` to the port table after 8088. In Layout `tools/`, add "jelu = reading tracker (Goodreads CSV import)".
- docs/README.md: add the line `| tools/jelu/README.md | Jelu reading tracker: first login, Goodreads CSV import, data paths |`
- tools/changedetection/README.md: change the "Related" line to say books-deals-aggregator is parked, its books half is Jelu (tools/jelu) and its deals half is this service.
- ideas/books-deals-aggregator.md -> ideas/parked/books-deals-aggregator.md (git mv). Keep all existing text and append:
  "## Parked 2026-10-23" with one line: "Books half: Jelu (tools/jelu, idea jelu-reading-tracker). Deals half: changedetection-deal-watch."
  Then "## Questions":
  1. Drop the Hardcover sync, now that Jelu holds the history?
  2. Still want Discord reading nudges and a weekly summary from Jelu's API (a small cron script), or a dashboard "books this year" widget instead?
  3. Queue concert-alerts (Ticketmaster key) as its own idea now, or later?
  4. Recommendations ("read X next"): drop, or a later idea?
  Do not touch any other idea note.

New service: jelu, dir tools/jelu
- image: wabayang/jelu:0.88.2 (newest stable tag, pushed 2026-10-07; https://hub.docker.com/v2/repositories/wabayang/jelu/tags?ordering=last_updated)
- container_name jelu, restart unless-stopped, logging json-file 10m x 3
- ports: "8089:11111" (8089 is not in the table and not listening; 11111 is the container port from https://github.com/bayang/jelu)
- volumes:
  - ${APPDATA_PATH}/jelu/config:/config
  - ${APPDATA_PATH}/jelu/database:/database
  - ${APPDATA_PATH}/jelu/files/images:/files/images
  - ${APPDATA_PATH}/jelu/files/imports:/files/imports
  - /etc/timezone:/etc/timezone:ro
  - no media mounts, no other mounts
- environment: TZ: ${TZ}, JELU_DATABASE_JOURNALMODE: wal
- networks: proxy (external)
- Traefik labels: traefik.enable=true, traefik.docker.network=proxy, router `jelu` with Host(`jelu.${DOMAIN}`), entrypoints=web, loadbalancer.server.port=11111
- Dashboard labels: homelab.name=Jelu, group=Tools, icon=jelu, audience=admin (Dan's own reading log; he can switch it to family later), description="Reading tracker: read, to-read, progress, yearly count", port=8089
- Kuma labels: kuma.jelu.http.name=jelu, kuma.jelu.http.url=http://${LAN_IP}:8089/
- Add a one-line comment at the top of the compose file, as in tools/changedetection/compose.yaml.

New env vars: None

Checks the builder must run:
- scripts/dc.sh /home/dan/homelab/.worktrees/jelu-reading-tracker/tools/jelu config -q
- grep -c 8089 /home/dan/homelab/.worktrees/jelu-reading-tracker/tools/jelu/compose.yaml (expect 3: the port, homelab.port, the Kuma URL)
- ss -ltnH "sport = :8089" (expect empty)
- git -C /home/dan/homelab/.worktrees/jelu-reading-tracker status: books-deals-aggregator shows as a rename into ideas/parked/
- Do not run up (deploy-idea.sh does that)

Review focus:
- Data dirs missing on first start -> Dan's manual step creates them as dan before deploy, so Docker doesn't create root-owned dirs in random places. All four mounts sit under /srv/homelab/jelu, inside restic's sources and not matched by backup-excludes.txt.
- Open first-user screen on the LAN -> the README says to make the admin account right after deploy and not to add other users. Audience is admin.
- Container recreated or upgraded -> the database stays on the /database bind mount (with WAL). Nothing app-related is stored in the image.
- The moved note's earlier Questions and Answers stay word for word. The new Questions sit under a new dated Parked heading, so the Parked tab shows them, and nothing remains in ideas/ for the loop to build as a custom tracker.
- No :latest tag, no docker.sock, and no /mnt/media anywhere in the compose file.

Docs: CLAUDE.md port table (8089 jelu) and the Layout tools/ line; a docs/README.md index line; the tools/changedetection/README.md Related line.

## Manual steps
1. Before deploy: mkdir -p /srv/homelab/jelu/{config,database,files/images,files/imports}
2. Deploy: scripts/deploy-idea.sh jelu-reading-tracker. Then check http://192.168.0.210:8089 and `scripts/kuma-status.py jelu`.
3. Create the first (admin) Jelu user straight away.
4. Export the Goodreads library CSV and import it in Jelu.
5. Answer the books-deals-aggregator questions on the Parked tab.

## Review notes
1. A build of the old idea is still waiting: branch `idea/books-deals-aggregator` (c6363ce, worktree `/home/dan/homelab/.worktrees/books-deals-aggregator`) holds a custom `scripts/reading-tracker.py` (Hardcover token, cron) and moves the same note to `ideas/done/`. Once this branch merges, deploying that one would hit a rename/rename conflict on `books-deals-aggregator.md` and add a second tracker next to Jelu. The plan didn't mention this branch. Dan should probably reject it with `scripts/deploy-idea.sh reject books-deals-aggregator` (or the Deploy tab), or else decide about it through Q1 on the Parked tab.
2. `/home/dan/homelab/.worktrees/jelu-reading-tracker/ideas/parked/books-deals-aggregator.md` now has two "## Parked" headings. The Parked tab (`core/dashboard/app/ideas.py:325`) takes its date from the first one, so it shows 2026-10-18, not 2026-10-23. It does show the newest Questions (`questions[-1]`), which is what matters. This is cosmetic.
3. `tools/jelu/compose.yaml:39`: the description reads "Reading tracker - read, ..." with a dash where the plan had a colon. Harmless, and probably done on purpose to avoid YAML colon quoting.
4. The Kuma URL has a trailing slash (`http://${LAN_IP}:8089/`) and the template's doesn't. Both work.

## Declined to judge
- The `/etc/timezone:/etc/timezone:ro` host mount: the plan lists it and Jelu's README asks for it. It is read-only and not media.
- The open first-user screen until Dan signs up: Jelu's docs confirm the first user becomes admin. The plan accepts this and covers it with a README warning and manual step 3. Admin audience, LAN/tailnet only.
- What user the container runs as and who owns the dirs: Jelu's docs don't cover it. Manual step 1 creates the dirs as dan beforehand, as the plan says.
