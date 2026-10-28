# Weekly Image-Freshness Digest

Value: 4
Effort: 2
Score: 16
Source: scout 2026-10-15 (audit sweep, top of "Also spotted")

## Problem
Pinned images only get checked when Dan runs `/update-stack`, so security fixes can sit unnoticed (the
Traefik fix in `apply-pending-image-upgrades` was found by the scout, not by a check). Diun was dropped in M4
because it needs the Docker socket (`IMAGES: 1` on the proxy).

## Proposal
`scripts/image-check.py`, cron Mondays via `scripts/install-cron.sh`. No container, no socket.
- Read the pinned `image:` lines from the tracked `*compose.yaml` files (skip `templates/` and the locally
  built `homelab/*`).
- Look up newer tags with the same queries and rules as `.claude/skills/update-stack/SKILL.md` step 1:
  Docker Hub / GHCR, same tag flavour, skip pre-releases and moving tags, highest semver.
- One digest to Discord via `scripts/discord.sh`: service, current, newest, patch/minor/major. Silent week =
  one "all current" line.
- A release whose GitHub release notes mention security / CVE / GHSA also goes to ntfy (high).
- Notes in the repo that pin a line on purpose (e.g. Omada stays on 6.2.x, GPU driver 580) are listed as
  "held", not as pending.
- Read-only. Applying upgrades stays with `/update-stack`; the digest says which `/update-stack <name>` to run.
- Unauthenticated API limits: GitHub allows 60 requests/hour, so cache release lookups and stop cleanly
  when rate limited (the digest says which ones it couldn't check).

## Checks
`py_compile`, a `--print` mode (no Discord, no ntfy) run against the real compose files, and the output
matches what `/update-stack` would list. Docs: `docs/m1-core.md` or m4 next to the Diun note, CLAUDE.md
scripts list.

_Added by Claude in the terminal for Dan, 2026-10-15._

## Plan
Goal: A weekly read-only cron script that checks every pinned image for newer tags, posts one digest to Discord, and sends a high-priority ntfy alert once per security release.
Kind: script/cron
Files:
- scripts/image-check.py: new, Python stdlib only (urllib, json, re, syslog). Header docstring in the style of scripts/arr-missing-search.py. Usage:
  - `scripts/image-check.py`: what cron runs.
  - `scripts/image-check.py --print`: prints the digest to stdout. No Discord, no ntfy, and the "alerted" list is not written.
  - `scripts/image-check.py [--print] <service>...`: checks only those services.
  How it works:
  - Images: `git -C REPO ls-files '*compose.yaml'`, skipping `templates/`. Read each file line by line. The service name is the last line matching `^  ([a-z0-9-]+):\s*$` before `^\s*image:\s*(\S+)`. Strip `#` comments from the image line. Skip `homelab/*`. Look up each image once; services sharing it (radarr + radarr-remote, sonarr + sonarr-remote) are listed together.
  - Tags: use the same queries as `.claude/skills/update-stack/SKILL.md` step 1.
    - Docker Hub: `https://hub.docker.com/v2/repositories/<ns>/<repo>/tags?page_size=100&ordering=last_updated` (`library/` for images with no namespace). If page 1 has no tag with the current tag's flavour, also read page 2 (from `next`).
    - GHCR: anonymous token from `https://ghcr.io/token?scope=repository:<o>/<r>:pull`, then `/v2/<o>/<r>/tags/list?n=10000`.
    - Timeout 15 s per request.
  - Flavour rule: skeleton = the tag with every digit run replaced by `N`. A candidate must have the current tag's skeleton. This keeps `v`, `-rootless`, `-omnibus`, `-lsN` and `_vN` flavours, and drops `latest`, `12`, `12.2`, `develop-*` and `rc`/`beta` tags. Compare the digit runs as an int tuple and take the highest that is greater than the current tag.
  - Type: the first differing component among the first 3 gives major/minor/patch. If only later components differ (e.g. `-ls318` to `-ls321`), the type is `build`.
  - HOLDS dict in the script, as `service: (allowed regex on the candidate, reason)`:
    - `omada`: `^6\.2\.`, "stay on 6.2.x (docs/m3-omada.md)"
    - `autokuma`: `^2\.`, "major must match Uptime Kuma 2.x"
    If the highest candidate fails its regex, pick the highest candidate that matches as the pending one, and list the newest tag that doesn't match as "held: <tag> (<reason>)".
  - Security check: GITHUB dict mapping image repo to GitHub repo:
    - adguard/adguardhome→AdguardTeam/AdGuardHome
    - tecnativa/docker-socket-proxy→Tecnativa/docker-socket-proxy
    - dockurr/samba→dockur/samba
    - binwiederhier/ntfy→binwiederhier/ntfy
    - traefik→traefik/traefik
    - louislam/uptime-kuma→louislam/uptime-kuma
    - bigboot/autokuma→BigBoot/AutoKuma
    - linuxserver/prowlarr→Prowlarr/Prowlarr
    - linuxserver/radarr→Radarr/Radarr
    - linuxserver/sonarr→Sonarr/Sonarr
    - qmcgaw/gluetun→qdm12/gluetun
    - seerr-team/seerr→seerr-team/seerr
    - amir20/dozzle→amir20/dozzle
    - analogj/scrutiny→AnalogJ/scrutiny
    - nousresearch/hermes-agent→NousResearch/hermes-agent
    Unmapped images (omada, jellyfin, qbittorrent) show "notes not checked".
    Only images with a pending candidate whose upstream version differs get a lookup. Upstream version = tag without a leading `v`, cut at the first `-` or `_`.
    Fetch `https://api.github.com/repos/<r>/releases?per_page=30`. Keep non-prerelease releases whose tag_name digit tuple is greater than the current upstream version and at most the candidate's. A release is security if its body matches `(?i)security|CVE-\d|GHSA-`.
  - Cache: `~/.cache/homelab/image-check.json` holds `{"github": {repo: {"etag", "releases": [...]}}, "alerted": ["<image>:<tag>", ...]}`. Send `If-None-Match` with the stored etag; a 304 reuses the cached releases and doesn't count against the 60/h limit. Write the file to a temp file, then `os.replace` it.
  - Discord message:
    - Line 1: "Image check <date>: N pending, M current, H held, E not checked".
    - Then one line per pending image: `<services>: <current> -> <candidate> (<type>)[ SECURITY] - /update-stack <service>`.
    - Then the held lines, then the "couldn't check: <image> (<reason>)" lines.
    - With nothing pending or failed, it's one line: "Image check <date>: all N images current (H held)".
    - Post via `subprocess.run([REPO/"scripts/discord.sh", msg])`. Split into several posts at line boundaries if the message is over 1900 chars.
  - ntfy: for each security candidate not yet in `alerted`, POST to `http://localhost:8081/<NTFY_ALERT_TOPIC>` with headers `Title: Security update: <service>`, `Priority: high`, `Tags: warning`. The body is current -> candidate, the matching release tag(s) and `/update-stack <service>`. Read the topic the way `scripts/storage-cleanup.py` `env()` does: never printed or logged. Add the key to `alerted` only after a successful POST.
  - Logging: syslog ident `image-check` for each run summary and each failure; also echo to stdout when it's a tty.
  - Exit codes: 0 when it ran, even if some lookups failed; 1 only if no image could be checked at all.
- scripts/install-cron.sh: add the line `10 9 * * 1 $REPO/scripts/image-check.py # homelab` (Mondays 09:10).
New service (if any): None
New env vars: None. It reuses NTFY_ALERT_TOPIC, and DISCORD_WEBHOOK_URL via discord.sh.
Checks the builder must run:
- `python3 -m py_compile scripts/image-check.py`
- `scripts/image-check.py --print` in the worktree against the real compose files.
- Compare the --print result for traefik, linuxserver/radarr and ghcr.io/seerr-team/seerr with the update-stack step-1 curl/jq queries run by hand. The newest same-flavour tag must match.
- `scripts/image-check.py --print omada autokuma` shows the held lines.
- `bash -n scripts/install-cron.sh`
Review focus:
- GitHub rate limit (403/429 with `X-RateLimit-Remaining: 0`) -> stop GitHub lookups for the rest of the run, use cached notes where they exist, and mark the others "notes not checked (GitHub rate limit)". No traceback, and the digest still posts.
- A registry is down, slow, returns non-JSON, or has no tags of the current flavour -> that image is listed under "couldn't check" with a reason. It never counts as "current", so it can't silently pass.
- A security release still unapplied on the following Monday -> ntfy is not sent again (the `alerted` set). It still shows as SECURITY in the Discord digest every week.
- The cache file is missing or corrupt -> start with an empty cache and rewrite it. Don't crash.
- --print mode -> no Discord post, no ntfy, and `alerted` is not changed. Running it by hand must never use up a real alert.
Docs:
- CLAUDE.md scripts list: add `image-check.py` (cron Mondays: Discord digest of newer image tags; ntfy on security releases; read-only).
- docs/m4-backups.md: under "### Diun (skipped)", add a short "Instead: scripts/image-check.py" paragraph covering the schedule, the flavour rule, HOLDS, the security ntfy-once behaviour, the cache path, `--print`, and `journalctl -t image-check`.
- docs/restore.md line ~379: add "image check" to the list of cron jobs.

## Manual steps
- Run `scripts/install-cron.sh` once after deploy.
- Optional: run `scripts/image-check.py --print` to see this week's digest.

## Review notes
1. /home/dan/homelab/.worktrees/image-freshness-digest/scripts/image-check.py:231-236: unmapped images (qbittorrent, jellyfin, omada) get "[notes not checked]" even on a build-only bump, because the GITHUB lookup runs before the `lo == hi` check. Putting the `lo == hi` check first would remove that noise.
2. image-check.py:370: the `alerted` list only ever grows (one entry per security image:tag). It stays small in practice, but it could be pruned to the keys that are still pending.
3. image-check.py:365-367: if NTFY_ALERT_TOPIC is unset, the security alert only goes to syslog. That's acceptable, since the digest still says SECURITY in Discord.
4. In `--print` mode the GitHub ETag/releases cache is still written. Only `alerted` is left alone, which is what the plan asks for.

## Declined to judge
- Broad `security` keyword match in release notes could flag releases that aren't really security fixes: the plan specifies this regex.
- A new candidate tag that carries the same older security release triggers a fresh ntfy: the plan keys `alerted` on image:tag.
