# immich

Immich (pinned in `compose.yaml`, v3.3.5) backs up the family's phone photos and videos and makes them
searchable (faces, places, "smart search"). Family tile: http://192.168.0.210:8097 (also http://immich.lan).
Four containers, one compose file, based on Immich's own `docker-compose.yml` for v3.3.5:

| Container | Image | Job |
|---|---|---|
| `immich` | `immich-server` | web UI + API on 2283 inside, 8097 outside; background jobs |
| `immich-machine-learning` | `immich-machine-learning` (CPU) | faces, smart search, OCR; port 3003, not published |
| `immich-postgres` | `ghcr.io/immich-app/postgres` (VectorChord) | the database; never swap for stock Postgres |
| `immich-redis` | `valkey/valkey` | job queue; no data worth keeping |

Only `immich` is on the `proxy` network; the rest talk to it on the project's own `immich` network.
Differences from upstream: our names (`immich-*` instead of `immich_*`, hostnames passed via `DB_HOSTNAME`,
`REDIS_HOSTNAME`, `IMMICH_MACHINE_LEARNING_URL`), `environment:` instead of `env_file: .env`, bind mounts
under APPDATA instead of the `model-cache` volume, `restart: unless-stopped`, explicit healthchecks, the
logging cap, and an exact Valkey tag (upstream uses `valkey:9` by digest).

## Where things live
- `/srv/homelab/immich/library` (`/data` inside): `upload/`, `library/` (originals), `thumbs/`,
  `encoded-video/`, `profile/`, `backups/` (Immich's database dumps). Each has a `.immich` marker file;
  Immich refuses to start if one is missing, so never delete a subfolder. Not on `/mnt/media`.
- `/srv/homelab/immich/postgres`: live database files. Excluded from restic (`scripts/backup-excludes.txt`):
  a copy taken while Postgres runs isn't consistent. The dumps in `library/backups` are the DB backup.
- `/srv/homelab/immich/model-cache`: ML models, downloaded on first use (a few hundred MB). Excluded from restic.
- `.env`: `IMMICH_DB_PASSWORD` (compose refuses to start without it). DB user `postgres`, database `immich`.

## First start
1. Space: the library lives on the disk behind `/srv/homelab`. Check `df -h /srv/homelab` against the
   family's phone libraries before the first upload (`disk-space-check.sh` warns at 85% on the system disk).
2. Password, letters and digits only (Immich's rule):
   `echo "IMMICH_DB_PASSWORD=$(openssl rand -hex 24)" >> .env`. Set it before the first start: Postgres
   only reads it when it creates the database.
3. `scripts/dc.sh tools/immich up -d`. The first start runs migrations; wait until `scripts/dc.sh tools/immich ps`
   shows all four healthy (up to ~5 min).
4. Open http://192.168.0.210:8097 and create the admin account (the first user is the admin; no default login).
5. Administration > Settings:
   - **Database Dump Settings**: check it's on (default: daily 02:00, keep 14). 02:00 runs before the 04:00
     restic backup, so each nightly snapshot holds the newest dump.
   - **Machine Learning Settings**: the URL is `http://immich-machine-learning:3003` (from the environment).
   - **Server Settings > External domain**: `http://192.168.0.210:8097`, so shared links work on the LAN.
6. Administration > Users: one account per family member (optionally a storage quota each).
7. Phones: install the Immich app, server URL `http://192.168.0.210:8097`, log in, pick the albums to back up
   and turn on background backup. Away from home it only works over Tailscale (`http://100.78.185.81:8097`;
   the app's "automatic URL switching" can use the LAN URL on home Wi-Fi). Never forward the port on the router.
8. First sync of a big library: the ML container is busy for hours (faces, smart search, CPU only), and the
   next nightly restic run plus the B2 copy carry the whole library, so they take longer once.

## Health
- `immich`: the image's own `immich-healthcheck` (GET `/api/server/ping`); Kuma checks
  `http://<LAN_IP>:8097/api/server/ping` (unauthenticated, `{"res":"pong"}`).
- `immich-machine-learning`: `python3` urllib on `:3003/ping`. `immich-postgres`: `pg_isready`.
  `immich-redis`: `redis-cli ping`. The server waits for Postgres and Valkey to be healthy.

## GPU (why ML is on CPU)
Checked against Immich's ML hardware-acceleration docs and the v3.3.5 ML Dockerfile: CUDA needs compute
capability 5.2+ and driver >= 545, and the `-cuda` image is built on CUDA 12.2. The GTX 970 is compute 5.2 on
driver 580, so on paper it is *just* supported, not too old. It stays on CPU anyway:
- Immich's ML `pyproject.toml` pins the last onnxruntime for CUDA 12 with a TODO to move to CUDA 13, and CUDA 13
  drops Maxwell. A future release will likely stop working on the 970, and ML can't be held back on its own:
  server and ML must run the same version.
- 4 GB (3.5 GB fast) VRAM, shared with Jellyfin's NVENC transcodes.
- For a family-sized library, CPU is fine: slow on the first import, then a few photos a day.

To try CUDA anyway: tag `v3.3.5-cuda` plus a `deploy.resources.reservations.devices` block for one `nvidia` GPU
(as in Immich's `hwaccel.ml.yml`), the same NVIDIA runtime Jellyfin uses. Re-check the CUDA base image in the
release notes on every upgrade. Never upgrade the driver branch for it (CLAUDE.md: 580 stays).

## Upgrades
`scripts/image-check.py` flags new tags. Before bumping: read every release note in between (Immich lists
breaking changes at the top), run a dump by hand (Administration > Job Queues > Create job > Create Database Dump),
bump `immich-server` and `immich-machine-learning` to the same tag, and only change the Postgres image when the
release notes or the new upstream `docker-compose.yml` change it. Then `scripts/dc.sh tools/immich up -d`.

## Restore
1. Restore `/srv/homelab/immich/library` whole from restic (`docs/restore-runbook.md`; the dumps come with it).
2. Database still fine: nothing more. Database broken or lost: stop the stack, move `immich/postgres` aside,
   `scripts/dc.sh tools/immich up -d` (Postgres creates an empty DB with the `.env` password), open the web UI
   and choose **Restore from backup** on the welcome screen, then pick the newest dump. On a working install
   the same list is under Administration > Maintenance > Restore database backup.
3. Photos uploaded between the dump (02:00) and the snapshot (04:00) are files without DB rows; re-run the
   phone backup to pick them up.
