# Deal watch with changedetection.io (the deals half of books-deals-aggregator)

Value: 4   (Dan gets price-drop and restock alerts for LEGO, vinyl and running gear without custom scrapers)
Effort: 2  (one pinned container plus labels; watches are set up in its own UI)
Risk: 2    (an isolated new container; no media, no socket; only the existing Discord webhook)
Score: 16
Source: scout 2026-10-19

## Problem
Dan approved `books-deals-aggregator` on 2026-10-18 (V5 E4). It is now parked in `ideas/parked/` on five
questions. Three of them are about the deals half: which scrapers to write first (Q3), where the watchlist
and thresholds live (Q4), and Discord or ntfy (Q5). Writing and maintaining one scraper per shop is most
of that note's E4 effort, and shop pages change often.

## Proposal
Run changedetection.io instead of custom scrapers. It reads prices and restock state from a page's
product data. v0.60.9 (2026-10-12) fixed decimal-comma prices like "39,99", which matters for UK/EU
shops. It alerts through Apprise (Discord and ntfy both), set per watch.
- `tools/changedetection/compose.yaml`, image `dgtlmoon/changedetection.io:0.60.9` (pinned), host port
  **8087** (free; add it to the CLAUDE.md port table), data at `/srv/homelab/changedetection:/datastore`.
- Labels from `templates/compose.yaml`: Traefik, dashboard (`audience: admin`, icon `changedetection`),
  Kuma, and the json-file log cap. Turn on its built-in password, since the UI holds the webhook URL.
- Alerts: the Discord feed by default; ntfy only for watches Dan marks urgent. This answers Q4 (its UI)
  and Q5 (per watch). Q3 becomes "which URLs to add first", with no API keys needed.
- Stage 1 has no browser fetcher. Upstream's Chrome fetcher (`dgtlmoon/sockpuppetbrowser`) only ships as
  `:latest` in their compose. Add it later only with a pinned dated tag or digest, and only if a JS-heavy
  shop (LEGO.com) does not work with the plain fetcher.
- It may not touch `/mnt/media`, the Docker socket, or any secret except the Discord webhook (and the
  ntfy topic) it is given through `.env`.
- The parked note keeps its books half (see the Jelu line in the 2026-10-19 report). Dan answers or
  splits the parked note once this lands.

## Existing tools checked
- changedetection.io (https://github.com/dgtlmoon/changedetection.io): 0.60.9, last release 2026-10-12,
  35.1k stars, 401 open issues, Apache-2.0, pinned Docker Hub tags; covers price/restock watches with alerts
  out of the box, so we use it.
- Custom scrapers (the parked note's stage 2): one per shop, each one breaks when the shop changes its pages;
  not worth it when the above exists.

## Rough plan
1. Compose file, port 8087, labels, data dir; `scripts/dc.sh tools/changedetection up -d`; Kuma monitor
   via labels; CLAUDE.md port table + layout line.
2. Apprise notification URLs for the Discord feed and ntfy from `.env` (passed only to this container);
   UI password set; a test watch on one LEGO set and one vinyl page.
3. A short doc section (where watches live, how to add one, the urgent-to-ntfy convention, and whether
   the browser fetcher is needed), plus a line in `docs/README.md` if it becomes its own doc.

_Approved on the dashboard, 2026-10-19._

## Plan
Goal: Run changedetection.io as an admin tool for price-drop and restock alerts. It replaces the custom shop scrapers in the deals half of books-deals-aggregator.
Kind: new service
Files:
- tools/changedetection/compose.yaml: new, copied from templates/compose.yaml (details below)
- tools/changedetection/README.md: new, short runbook (details under Docs)
- CLAUDE.md: add port table rows `| 8086 | fitness |` (already in use by tools/fitness but missing from the table) and `| 8087 | changedetection |`, sorted; add `changedetection = price/restock watches` to the tools/ Layout line
- docs/README.md: one row for `tools/changedetection/README.md`, next to the fitness row

New service:
- name `changedetection`, dir `tools/changedetection/`
- image `dgtlmoon/changedetection.io:0.60.9`. Source: Docker Hub tags API, pushed 2026-10-12 and the newest numbered tag; https://hub.docker.com/r/dgtlmoon/changedetection.io
- ports `"8087:5000"`. 8087 is the lowest free port: 8082-8086 are taken, and 8087 is neither in the table nor listening.
- volumes `${APPDATA_PATH}/changedetection:/datastore`. No /mnt/media, no docker.sock.
- networks: `proxy` (external)
- environment: `TZ: ${TZ}` and `BASE_URL: http://${LAN_IP}:8087` (so alert links work). Nothing else.
  - No Discord webhook or ntfy topic goes into the container env. changedetection does not read notification URLs from env; they live in its datastore and are set in its UI. Passing them in would break the rule "only what they need". This differs from the note's step 2 on purpose.
- no browser fetcher (no sockpuppetbrowser, no PLAYWRIGHT_DRIVER_URL), as the note says
- logging: the json-file cap (10m x 3)
- labels:
  - Traefik: enable, `traefik.docker.network=proxy`, router `changedetection`, rule Host(`changedetection.${DOMAIN}`), entrypoint web, loadbalancer port 5000
  - Dashboard: name `Changedetection`, group `Tools`, icon `changedetection`, audience `admin`, description `Price-drop and restock watches`, port 8087
  - Kuma: `kuma.changedetection.http.name=changedetection`, url `http://${LAN_IP}:8087/` (with the password on, this redirects to the login page, which returns 200)
- .lan host: changedetection.lan

New env vars: None

Checks the builder must run:
- `scripts/dc.sh /home/dan/homelab/.worktrees/changedetection-deal-watch/tools/changedetection config -q`
- check the image line has no `:latest` and no docker.sock or /mnt/media appears in the file
- icon exists: `curl -s -o /dev/null -w '%{http_code}\n' https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/changedetection.svg` returns 200. If not, try `png/changedetection.png`; if that fails too, use the slug that does exist and say so.
- `ss -ltnH "sport = :8087"` is empty
- CLAUDE.md port table is still sorted

Review focus:
- Shop blocks the fetch (403/captcha) or the price element is missing -> the watch shows an error in the UI. The README tells Dan to leave "notify on filter not found" off, so a broken shop page does not spam Discord.
- First check of a new watch -> no alert; only a real price or stock change alerts.
- UI password not set yet at first start -> the UI is open on the LAN until Dan sets it. The README puts the password as manual step 1, before any webhook URL is pasted in.
- Container recreate or upgrade -> watches and history survive in /srv/homelab/changedetection. The README notes this data is under APPDATA, so restic backs it up.
- Snapshot history growing on the disk -> the README says to keep the check interval at 3h or more and to prune history in Settings. disk-space-check.sh already alerts on the system disk.

Docs: tools/changedetection/README.md covers:
- watches live in the UI and datastore at /srv/homelab/changedetection
- how to add a price/restock watch: "Re-stock & Price detection" processor
- Apprise URL formats: Discord `discord://<webhook_id>/<webhook_token>` (from DISCORD_WEBHOOK_URL), and ntfy `ntfy://192.168.0.210:8081/<NTFY_ALERT_TOPIC>`
- the convention: Discord as the global default; add the ntfy URL only on watches marked urgent (tag `urgent`)
- browser fetcher: not installed. Add it only with a pinned tag or digest if LEGO.com fails with the plain fetcher.
- the parked books-deals-aggregator keeps its books half
Plus CLAUDE.md and docs/README.md as listed under Files.

Note: nothing in the idea note asks to break the rules.

## Manual steps
1. Deploy: `scripts/dc.sh tools/changedetection up -d` (deploy-idea.sh). tools/* is already covered by the permission wildcards, so .claude/settings.json does not change.
2. At http://192.168.0.210:8087, Settings > General: set the UI password.
3. Settings > Notifications: add the Discord Apprise URL, built from the webhook in .env, as the global default. Leave "notify on filter not found" off.
4. Add test watches: one LEGO set and one vinyl page, using price/restock detection. Tag the ntfy-urgent ones and add the ntfy URL on those watches.
5. If LEGO.com fails with the plain fetcher, queue a follow-up idea for a pinned browser fetcher.
6. Answer or split the parked books-deals-aggregator note (Q3-Q5 are now answered by this service).

## Review notes
1. `scripts/idea.sh diff` also shows qbit-seeding-time-cap being undone: `scripts/qbit-setup.py`, `docs/m2-media.md`, and the note moving from `ideas/done/` back to `ideas/`. The builder didn't do this. The branch starts at 5df3514, before main merged 1a25182, and the diff compares against main's tip. `git status` in the worktree shows only the 5 files that belong to this idea. A normal merge keeps main's qbit changes, but check that deploy-idea.sh merges rather than resets or copies files over.
2. Manual step 6 in /home/dan/homelab/.worktrees/changedetection-deal-watch/ideas/changedetection-deal-watch.md is out of date: the reading-tracker half of books-deals-aggregator has since been built on `idea/books-deals-aggregator`. The README's "Related" line ("the parked `books-deals-aggregator` keeps its books half") will be out of date for the same reason. Dan should read step 6 as "close out the deals questions (Q3-Q5) on that branch's note."
3. "Notify on filter not found" mostly applies to the text/JSON-diff processor. For "Re-stock & Price detection" watches, the bigger spam risk is small price changes. The README could tell Dan to set the processor's price-change threshold (e.g. a %) or to alert on restock only. This doesn't block.
4. `/srv/homelab/changedetection` doesn't exist yet. Docker will create it as root on the first `up`. That works because the image runs as root, but other services' data dirs may be owned by dan.
5. Until Dan sets the password (manual step 2), the UI is open on the LAN and tailnet. The plan accepts this, and the README makes the password the first step, before any webhook is pasted in.

## Declined to judge
- UI open until the password is set: accepted in the plan (Review focus) and covered by the README's step order.
- No browser fetcher, so JS-heavy shops like LEGO.com may fail: deferred on purpose by the plan (manual step 5).
- Webhook and ntfy topic go in the UI, not `.env`: the plan chose this on purpose (changedetection doesn't read notification URLs from env).
