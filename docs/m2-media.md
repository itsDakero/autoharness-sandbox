# M2 media stack – runbook

## Stage A: GPU
- GTX 970 (Maxwell GM204). Driver branch **580** is the last that supports it: never install a newer
  branch. `bootstrap.sh` installs `nvidia-headless-no-dkms-580` + `linux-modules-nvidia-580-generic`
  (Ubuntu's prebuilt signed modules, follow kernel updates, no DKMS), `nvidia-utils-580`,
  `libnvidia-encode-580`, `libnvidia-decode-580`, and `nvidia-container-toolkit` with the Docker
  `nvidia` runtime (`/etc/docker/daemon.json`).
- After a first install: reboot. Check:
  - host: `nvidia-smi`
  - container: `docker run --rm --gpus all -e NVIDIA_DRIVER_CAPABILITIES=compute,video,utility ubuntu:24.04 nvidia-smi`
- Containers need `NVIDIA_DRIVER_CAPABILITIES` to include `video` to get NVENC/NVDEC
  (`libnvidia-encode`, `libnvcuvid`).
- `bootstrap.sh` also sets owner `dan:dan` on `/mnt/media/downloads` (the dir only, not its contents;
  it was `130:138`) and creates `temp`, `movies`, `tv`, `movies-remote`, `tv-remote` in it.

## Stage B: VPN + downloads (`media/qbittorrent`)
- **gluetun** (`qmcgaw/gluetun`): NordVPN WireGuard/NordLynx, `SERVER_COUNTRIES=United Kingdom`, key in
  `.env` (`NORDVPN_WIREGUARD_PRIVATE_KEY`). Its firewall is the kill switch (always on). Publishes the
  qBittorrent Web UI on **8083** and is on `proxy`, so other containers use `http://gluetun:8083`.
- **qbittorrent** (`linuxserver/qbittorrent`): `network_mode: service:gluetun`, Web UI 8083, also bound
  to `tun0`. Mounts only `/mnt/media/downloads` (read-write, same path as the arr apps → hardlinks).
- Settings: `scripts/qbit-setup.py seed` (qbittorrent stopped: Web UI login from `.env`, PBKDF2-hashed)
  and `scripts/qbit-setup.py apply` (running: idempotent, reads back and reports mismatches):
  - default save `/mnt/media/downloads`, temp `/mnt/media/downloads/temp`, automatic torrent management
  - categories `movies`, `tv`, `movies-remote`, `tv-remote` → `/mnt/media/downloads/<category>`
  - alternative limits 5 KiB/s down/up, scheduled daily 19:00–23:59
  - queueing: 10 active torrents, 5 active uploads, 3 active downloads (default)
  - ratio 1.0, 14 days seeding or 3 days inactive → **stop**. Radarr/Sonarr ("Remove Completed" on their qBittorrent client) then delete
    torrent **and files** once imported; the library keeps its hardlink. qBittorrent removing them itself
    races the import, and the arr apps refuse that setup. Torrents added by hand stay stopped.
  - Web UI host header validation on; allowed names `homelab`, `*.lan`, `qbittorrent.lan`, `gluetun`,
    `LAN_IP`, `TAILSCALE_IP`, `localhost` (this script). Anything else gets 401.
- NordVPN has no port forwarding: no incoming peers, so seeding to 1.0 can be slow on rare torrents (hence the time limits).
- "Unauthorized" when opened from the dashboard tile (fixed 2026-10-04): not the host check but
  qBittorrent's CSRF check, which answers a request whose `Referer` (`http://homelab/`) is another
  origin than the target (`homelab:8083`) with 401 (log: "Referer header & Target origin mismatch").
  The dashboard page now sets `<meta name="referrer" content="no-referrer">`; CSRF protection stays on.
  Verified: 200 on `192.168.0.210:8083`, `homelab:8083`, `100.78.185.81:8083`, `qbittorrent.lan`,
  `gluetun:8083` from radarr; `Host: evil.example` → 401; all four arr download-client tests pass.
- qBittorrent 5.x login returns 204 and a `QBT_SID_<port>` cookie (not 200 "Ok." / `SID`).

### Verified (2026-10-04)
- Exit IP from inside qbittorrent is NordVPN UK (`api.nordvpn.com/v1/helpers/ips/insights` →
  `protected: true`); the host itself is Virgin Media.
- Tunnel down (`docker exec gluetun ip link set tun0 down`): every request blocked until Gluetun's
  healthcheck reconnected (~45 s) on a new NordVPN IP; the home IP never appeared.
- Gluetun container stopped: qbittorrent has only `lo`, no network.

### Control server auth (2026-10-05)
- Gluetun's control server (`gluetun:8000`, `proxy` network only, not published) answered every legacy
  route without auth by default (v3.41.3 logs "unprotected by default"), including routes that change state.
- `scripts/gluetun-auth.py` writes `${APPDATA_PATH}/gluetun/auth/config.toml` (mode 600, key from
  `GLUETUN_API_KEY` in `.env`, never printed): one role `dashboard`, API key, routes `GET /v1/vpn/status`
  and `GET /v1/publicip/ip` only. Every other route is denied. Gluetun reads it at start, so apply with
  `scripts/dc.sh media/qbittorrent up -d --force-recreate` (Gluetun, then qbittorrent rejoins) when no
  download is running.
- New key: generate one into `.env` (see `.env.example`), re-run the script, recreate the dashboard and
  Gluetun as above.
- Verified: no key / wrong key → 401 on all routes; the key → 200 on the two routes, 401 on others
  (`/v1/dns/status`, `/v1/openvpn/portforwarded`); no "unprotected" warnings since. After the recreate:
  exit IP NordVPN UK (`protected: true`; host is Virgin Media), Web UI 200 on 192.168.0.210:8083,
  homelab:8083, qbittorrent.lan and gluetun:8083 from radarr, all four arr download-client tests OK,
  qBittorrent settings 24/24, torrents intact, Kuma never saw it down, VPN widget "Protected".

### Gotcha: Gluetun restarted outside compose
qbittorrent lives in Gluetun's network namespace. If Gluetun restarts on its own (crash, `docker
restart`, restart policy), qbittorrent keeps the dead namespace: **no leak, but no Web UI or downloads**.
Kuma's `qbittorrent` monitor goes down and alerts. Compose-driven restarts (`scripts/dc.sh
media/qbittorrent up -d` after an image bump) handle it via `depends_on: restart: true`.

### Watchdog (`scripts/qbit-watchdog.sh`, cron)
- Runs every minute from dan's crontab (`scripts/install-cron.sh` installs it, idempotent; lines tagged
  `# homelab`). If qbittorrent is running without `eth0` while Gluetun is `running/healthy`, it runs
  `docker restart qbittorrent` and posts a **normal-priority** ntfy message ("qBittorrent healed", or
  "restart didn't help"). Never touches Gluetun.
- Does nothing while qbittorrent or Gluetun is stopped on purpose, or Gluetun isn't healthy yet.
- At most one restart per 10 min (`~/.local/state/homelab/qbit-watchdog.last`), flock against overlap.
- ntfy topic: `NTFY_ALERT_TOPIC` in `.env` (the same secret topic as Kuma's `ntfy-urgent`); posts to
  `http://localhost:8081`. Without it, it still heals and logs, just no message.
- Log: `journalctl -t qbit-watchdog`. Expect Kuma's urgent "qbittorrent down" first, then the heal message.
- Manual fix if needed: `scripts/dc.sh media/qbittorrent restart qbittorrent`.
- Tested 2026-10-04: `docker restart gluetun` orphaned qbittorrent; cron healed it ~50 s later, egress
  back on NordVPN, settings intact.

### VPN-down alert (Kuma qbittorrent-vpn)
- The `qbittorrent` monitor stays green with the tunnel down, because Gluetun still serves 8083.
- `qbittorrent-vpn` is a Kuma Docker monitor on the `gluetun` container through docker-socket-proxy.
  It is down when the container is unhealthy or stopped, and pending while it is starting or restarting.
- It checks every 60 s and goes down after 5 failures in a row (about 5 min), then sends an urgent
  ntfy alert.
- It needs no Gluetun key.
- It shows on the qbittorrent dashboard tile (worst status).
- Test: `docker exec gluetun ip link set tun0 down`. Expect at most one or two pending beats, then up,
  with no alert.

## Stage C: arr apps (`media/prowlarr`, `radarr`, `sonarr`, `radarr-remote`, `sonarr-remote`)
| App | Port | Root folder | qBittorrent category | Quality profile |
|---|---|---|---|---|
| prowlarr | 9696 | – | – | – |
| radarr | 7878 | `/mnt/media/movies` | `movies` | Up to 2160p |
| sonarr | 8989 | `/mnt/media/tv` | `tv` | Up to 2160p |
| radarr-remote | 7879 | `/mnt/media/movies-720p` | `movies-remote` | HD-720p |
| sonarr-remote | 8990 | `/mnt/media/tv-720p` | `tv-remote` | HD-720p |

- linuxserver images, fresh configs in `/srv/homelab/<name>`. The four arr apps mount all of
  `/mnt/media` read-write at the same path as qbittorrent (one filesystem, device checked inside the
  containers) → imports are hardlinks (`copyUsingHardlinks` on). Prowlarr has no media mount.
- Containers talk over `proxy`: arr → `gluetun:8083`; Prowlarr → `http://<name>:<container port>`
  (remote pair: 7878/8989 inside, 7879/8990 published).
- `scripts/arr-setup.py` (idempotent; API keys read from each `config.xml`, never printed): root folders,
  qBittorrent client per app (connection-tested, Remove Completed/Failed on), quality profiles,
  hardlinks, Prowlarr applications (full sync, connection-tested). `scripts/arr-setup.py auth` sets
  Forms login on all five from `ARR_USERNAME` / `ARR_PASSWORD`.
- **Up to 2160p** (main pair): HDTV/WEB/Bluray at 720p, 1080p, 2160p; upgrades on, cutoff Bluray-2160p.
  No Remux, BR-DISK or Raw-HD (disc-sized files). **HD-720p** (remote pair): built-in, 720p only.
  Arr apps have no server-side default profile: pick it when adding, or set it in Seerr (Stage E).
- **2160p size cap (main pair, 2026-10-04):** HDTV/WEBDL/WEBRip/Bluray-2160p preferred **100**, max **140
  MB/min** (≈ 20 GB for a 2h20 film, ≈ 6.3 GB for a 45-min episode) in Radarr and Sonarr; min unchanged
  (Radarr 0, Sonarr 35). Releases above the max are rejected, so a film with only bigger 4K releases
  falls back to 1080p. Quality sizes are per app, not per profile; the remote pair (720p) is untouched.
  `MAIN_SIZES` in `scripts/arr-setup.py`; `scripts/arr-setup.py sizes` applies just these.
  Not capped: Remux (excluded from the profile).
  Before: Radarr no preferred/max; Sonarr preferred 95, no max (HDTV-2160p max 199.9).
- Ownership: everything in the libraries is `dan:dan` = PUID/PGID 1000. Only the old macOS `._*` /
  `.DS_Store` files in `downloads/` are `130:138` (unused).
- Indexers: add in Prowlarr; full sync pushes them to all four. Until then every app shows a
  "no indexers" health error.
- 2026-10-04: The Pirate Bay + YTS. YTS is movies-only → Radarr pair only (expected). TPB's **Top100**
  must be **Movies/TV**, not the default All: the arr apps test (and run RSS) with a keyword-less query,
  which TPB answers from that list; when "All" held no movies, both Radarrs rejected TPB ("no results
  in the configured categories", Prowlarr logs "Validation failed") and silently lacked it. After the
  change: Radarr pair TPB + YTS, Sonarr pair TPB, all health checks clear.
- Login: Forms auth on all five (`scripts/arr-setup.py auth`, from `ARR_USERNAME` / `ARR_PASSWORD`).
  `/ping` stays open for Kuma.

### Library Import (`scripts/arr-import.py`, 2026-10-04)
- Dry run by default; `--apply` imports in place (folder = path, nothing moved or renamed), monitored,
  **no searches**. Matching uses the app's own parser + lookup; title and year must match. A clean
  `Title (Year)` folder wins over release-named folders of the same title (those were hardlinked
  seeding copies from the old setup and stay where they are, unmanaged).
- Result: radarr 37 movies (22 with a file), sonarr 12 series (158 episode files), radarr-remote 7/7,
  sonarr-remote 5 series (50 files).
- Not imported, needs a decision: 15 Radarr folders are empty shells (only macOS `._*` stubs and
  tracker `.txt`; the films aren't anywhere on the disk) → imported as monitored + missing, so Radarr
  will grab them once indexers exist. 8 loose movie files and 36 loose episode files sit directly in
  the roots; 41 Sonarr release/episode folders (season packs, single episodes) sit next to the series
  folders. Arr apps only manage files inside the movie/series folder.
- Rivals: Sonarr's lookup also returns an older "Rivals" with no year; the import prefers the
  year match (tvdb 429920, Disney+).

### Naming (new imports)
- Radarr folder `{Movie CleanTitle} ({Release Year}) [tmdbid-{TmdbId}]`, file = folder name +
  ` - {edition-…} [Quality][HDR][Audio][Codec]-Group` (Jellyfin groups versions by the folder-name prefix).
- Sonarr folder `{Series TitleYear} [tvdbid-{TvdbId}]`, `Season 01`, file
  `{Series TitleYear} - S01E01 - {Episode CleanTitle} [Quality]…`, multi-episode `S01E01-E02`.
- Set by `scripts/arr-setup.py`. Existing files are untouched until Rename is run;
  `scripts/arr-rename.py` previews (default) or applies (`--apply`). Rename never moves folders.
- 2026-10-04: file renames applied in all four apps (`arr-rename.py --apply`); folders unchanged.
  Sonarr sorted episodes into `Season NN/` inside each series folder. The 15 empty-shell Radarr movies
  are unmonitored (no automatic grabs).

### Weekly missing search (`scripts/arr-missing-search.py`, cron)
Radarr and Sonarr search once when a title is added, then only watch RSS. On 2026-10-05 titles were added
before Prowlarr synced indexers to the remote pair, so the add-time search ran with 0 indexers and nothing
searched again. This script re-searches in all four apps, Sundays 02:30 (outside the qBittorrent limit
window, before the 04:00 backup).
- Selection: monitored, released (Radarr: `isAvailable`, so the minimum availability counts; Sonarr: air date
  passed), no file, not in the queue, not searched in the last 7 days (`lastSearchTime`).
- Cap: 10 per app per run (movies for Radarr, units for Sonarr), never/oldest searched first; the rest waits.
- Sonarr: 2+ missing episodes of one season become one `SeasonSearch`; a single one an `EpisodeSearch`.
- Posts to Discord only when something was searched or an app failed. Logs to
  `journalctl -t arr-missing-search`.
- `scripts/arr-missing-search.py --dry-run` prints the plan and starts nothing; app names as arguments
  (`radarr sonarr-remote`) limit the run.
- Results (grabs, rejections) stay in each app's History. It never changes monitoring, profiles or indexers.

### Watched-media cleanup report (scripts/storage-cleanup.py, cron)
Part A of a four-part cleanup (A report, B apply, C Seerr clear, D recycle bin). **A is read-only**: only HTTP
GETs against Jellyfin, Seerr and the four arr apps; the one POST is the ntfy message. Sundays 10:00 (after the
missing search). `report` writes `${APPDATA_PATH}/cleanup/storage-report-YYYY-MM-DD.txt`, posts to ntfy
(low priority, "Storage cleanup report (dry run)") and logs to `journalctl -t storage-cleanup`;
`report --print` only prints.
- Constants in the script: GRACE_DAYS 30, KEEP_LATEST 3, FULL_PCT 85, CAP_EPISODES 20, CAP_MOVIES 5,
  STALE_DAYS 90, PROTECT_TAG `keep`. Drop GRACE_DAYS to 14 once the report is trusted.
- Candidate: has a Seerr requester; the requesters and anyone who started it have all watched it (Jellyfin
  users dan, emily, sylvia, matched by exact file path); latest watch + 30 days has passed; no `keep` tag in
  the arr app; not a Jellyfin favourite (episode, season, series or movie); an episode is not among the 3 most
  recent aired ones. No requester (pre-Jellyfin content) means never a candidate.
- Order: oldest due first; first 20 episodes and 5 movies across all four apps are "would delete", the rest
  "over cap". Below 85% disk the report says nothing would be deleted but still lists candidates.
- Stale list: titles with no plays for 90 days (added 90+ days ago), tagged "no requester" or "requested by".
  For Dan's approval, never deleted.
- Later parts: B apply (delete the episode/movie file through the arr API, unmonitor, keep the series and
  Monitor New Items; test Erasarr against this rule first), C clear Seerr's "Available" after deletion,
  D recycle bin in the arr apps (path `.recycle` under the media root, approved by Dan), emptied after 30 days.

## Stage D: Jellyfin (`media/jellyfin`, 8096, family)
- `jellyfin/jellyfin` 12.2, server name **Danflix** (set in the wizard). Runs as PUID/PGID, media
  read-only at `/mnt/media` (same paths as the arr apps), config/cache in `/srv/homelab/jellyfin/`.
  GPU via compose `deploy.resources.reservations.devices` (nvidia) + `NVIDIA_DRIVER_CAPABILITIES=compute,video,utility`.
- `scripts/jellyfin-setup.py` (API key `JELLYFIN_API_KEY`, idempotent; `status` = read-only):
  libraries Movies `/mnt/media/movies`, TV `/mnt/media/tv`, Movies (Remote) `/mnt/media/movies-720p`,
  TV (Remote) `/mnt/media/tv-720p`; transcoding NVENC, hardware decode H.264/MPEG-2/MPEG-4/VC-1 only,
  no 10-bit decode, H.264 output (no HEVC/AV1 encoding), tone mapping on.
- Intro Skipper plugin (skip intro/credits button): `scripts/jellyfin-setup.py plugins` adds the repository
  `https://intro-skipper.org/manifest.json`, installs the pinned 12.0.5.0 (stable), clears the plugin
  auto-update task's triggers (pinned like the images) and sets the analysis tasks to daily 02:00, max 4h.
  Steps: run `plugins`, `scripts/dc.sh media/jellyfin restart` (needs approval), run `plugins` again
  (the night window needs the loaded plugin), check `status` shows 12.0.5.0 Active. Data in
  `/srv/homelab/jellyfin/config` (backed up); media stays `:ro`. A Jellyfin major bump via `/update-stack`
  must check plugin compatibility (targetAbi). Infuse shows no skip prompt; web and Jellyfin apps do.
- GTX 970 (GM204) limits, tested in the container: NVENC H.264 ✓, HEVC 8-bit ✓, HEVC 10-bit ✗;
  NVDEC H.264 ✓, HEVC ✗ (any bit depth), no VP9/AV1.
- Transcode tests (2026-10-04, forced 4 Mbit/s H.264):
  - H.264 1080p SDR: NVDEC → NVENC, 11.4× realtime (274 fps), host CPU ~50%.
  - HEVC 4K 10-bit HDR10: CPU decode → scale → `tonemap_cuda` → NVENC, 3.7× realtime, host CPU ~98%.
    Expect about two simultaneous 4K HDR transcodes; direct play (TVs that handle HEVC/HDR) costs nothing.
- Check a live transcode: Dashboard → Playback shows "Transcoding (HW)"; `nvidia-smi` lists ffmpeg;
  logs in `/srv/homelab/jellyfin/config/log/FFmpeg.Transcode-*.log`.

## Library tidy-up (2026-10-04)
- `scripts/arr-organise.py` (dry run by default, `--apply`, `--skip "Title"`): loose files and
  release/season-pack folders in the Radarr/Sonarr roots → Manual Import (move + rename) into their
  movie/series folder; adds missing titles first (no search). Skips hardlinks of files already in the
  library, and anything the app rejects (not an upgrade, sample).
  Applied: added Frankenstein (2025) and One Battle After Another (2025); 15 Peacemaker episodes moved
  in. FROM and Rooster were test downloads: not added (`--skip`), deleted instead.
- `scripts/media-cleanup.py`: `plan duplicates` / `plan paths …` write a manifest to
  `/srv/homelab/cleanup/` (read-only); **`apply <manifest>` is run by the user** (the guard blocks
  Claude from deleting media). Apply re-checks each row first: duplicates must still be the same
  inode as the library copy, files the same size; folders go only once empty.
  Subtitles are never junk: folders holding them are kept.
- Run 2026-10-04: test downloads 18 removed (10.35 GB); duplicates 358 removed, 10 skipped. The skips
  were release folders left holding an empty `Sample/`, `Screens/` or `S01/` subfolder: the planner
  listed only the top folder (fixed: subfolders now go first, deepest first). Nothing was lost.
- After the cleanup: arr apps track radarr 39 movies (24 with a file), sonarr 12 series / 173 files,
  radarr-remote 7, sonarr-remote 5 series / 50 files; every tracked file exists. Jellyfin still lists
  the release folders that only hold subtitles (Only Murders S01/S02, Gilded Age S01) as extra series.
- Final manifest `/srv/homelab/cleanup/20261004-134828-paths.tsv` (user-run): Spider-Man 3 720p,
  The Pitt S01E01_Fixed, the whole Spider-Man 2002 release folder (41 MB stub + nfo/jpg/txt), both
  root `.DS_Store`, the 3 subtitle-only release folders (442 `.srt` named after deleted releases, so
  unusable by Jellyfin), and the 10 empty leftover folders: 451 files, 6.62 GB, 56 folders.

## Stage E: Seerr (`media/seerr`, 5055, family)
- `ghcr.io/seerr-team/seerr` v3.5.1, runs as PUID/PGID (`init`, `no-new-privileges`, all caps dropped),
  config in `/srv/homelab/seerr/config`. Sign-in with Jellyfin accounts (Danflix, `http://jellyfin:8096`
  over `proxy`; external URL `http://192.168.0.210:8096` for Play links). Owner = Jellyfin `dan`.
- `scripts/seerr-setup.py` (`SEERR_API_KEY`, arr keys from `config.xml`; idempotent; `status` = read-only):

  | Seerr server | Arr | Profile | Root folder | Default |
  |---|---|---|---|---|
  | Radarr | `radarr:7878` | Up to 2160p | `/mnt/media/movies` | yes |
  | Sonarr | `sonarr:8989` | Up to 2160p | `/mnt/media/tv` | yes |
  | Radarr (Remote) | `radarr-remote:7878` | HD-720p | `/mnt/media/movies-720p` | no |
  | Sonarr (Remote) | `sonarr-remote:8989` | HD-720p | `/mnt/media/tv-720p` | no |

  Also: Jellyfin library sync **Movies + TV only**, imports all Jellyfin users, default permissions for
  new users = Request (no auto-approve: pending until approved or the setup is re-run), application URL
  `http://192.168.0.210:5055`, then starts the Jellyfin/Radarr/Sonarr scans.
- Users: `dan` owner/admin; `sylvia` (parents) Request + Auto-Approve → main pair; `emily`
  (`SEERR_REMOTE_USERS`) Request only → routed to the remote pair.

### Why a router: Seerr can't pick a server per user
Checked in the v3.5.0 source: requests go to the default server, or to the one an "Advanced Requests"
user picks in the modal (which starts on the default every time). Override rules can match users, but
only change profile/root folder/tags **on the default server**, never the server. No per-user default.
Rejected alternatives: Emily picks Remote herself (one slip = 4K copy in the main library); Dan edits
each request when approving (manual); remote pair as Seerr's "4K" servers (labels 720p as 4K
everywhere, takes the real 4K slot).

### Router (`scripts/seerr-route.py`, cron)
- Every minute from dan's crontab (`scripts/install-cron.sh`). For each **pending** request by a
  `SEERR_REMOTE_USERS` user: set server Radarr/Sonarr (Remote) + its profile and root folder (read from
  Seerr's server settings), then approve; Seerr sends it to radarr-remote/sonarr-remote. If anything
  fails, the request stays pending: it never lands on the main pair. Up to a minute's delay.
- ntfy (normal priority, `NTFY_ALERT_TOPIC`): "Seerr router error" (API errors, missing server/user;
  at most hourly while it persists, then "Seerr router recovered"); "Seerr: request stuck" (a remote
  user's request pending > 15 min); "Seerr: request failed" (Seerr couldn't add it to the remote arr;
  retry in Seerr > Requests). Once per request. State in `~/.local/state/homelab/seerr-route.json`.
- Does nothing while the `seerr` container isn't running. Log: `journalctl -t seerr-route`.
- `scripts/seerr-route.py status` lists remote users' requests and their server (read-only);
  `scripts/seerr-route.py test` sends a test notification.
- Don't use "Request as another user" (admin) for a remote user: the **acting** user's auto-approve
  applies, so it goes straight to the main pair. Same if a remote user is ever given Auto-Approve,
  Manage Requests or Admin (`seerr-setup.py` strips those, plus Advanced Requests).

### Verified (2026-10-04)
- Emily requested Supergirl (2026) and The Rookie (2018) from her account; the router approved each
  within a minute onto Radarr (Remote) / Sonarr (Remote): both in radarr-remote/sonarr-remote with
  HD-720p under `/mnt/media/movies-720p` / `tv-720p`, monitored; neither in the main Radarr/Sonarr.
- `seerr-route.py test` notification arrived on the phone. `seerr-setup.py` re-run: no changes, no duplicates.

### Limit: one availability status per title
Seerr tracks one (non-4K) status per movie/series. A title already in the main library shows
Available, so a remote user can't request a 720p copy (she watches the main one; Jellyfin transcodes).
That's why the remote Jellyfin libraries are **not** synced: otherwise her 720p titles would show
Available to everyone else. Her requests are still tracked (Processing → Available) through the
radarr-remote/sonarr-remote sync.

### Adding another remote user
1. Create the Jellyfin user (Dashboard > Users) with access to the Remote libraries.
2. Add the Jellyfin username to `SEERR_REMOTE_USERS` in the repo env file (comma-separated, e.g. `emily,alex`).
3. Run `scripts/seerr-setup.py`: imports the user into Seerr and sets Request without auto-approve.
   (If they signed in to Seerr first they got the default Request permission, so their requests were
   pending anyway and nothing went to the main pair.)
4. `scripts/seerr-route.py status`: the user is found (no "not in Seerr" error).
5. Have them request one title; within a minute `status` shows it approved on the Remote server.

Removing one: take the name out of `SEERR_REMOTE_USERS`, then run `scripts/seerr-setup.py` (gives
them auto-approve → main pair).
