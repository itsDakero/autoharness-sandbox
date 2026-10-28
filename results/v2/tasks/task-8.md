Immich is added under `tools/immich`, and all local checks pass. Nothing was started or deployed, since the sandbox has no Docker and no `.env`.

**The GPU isn't too old for Immich on paper.** Immich's v3.3.5 docs ask for compute capability 5.2 or higher and a driver of 545 or newer. The GTX 970 is exactly 5.2 and you're on driver 580, so it just qualifies. I kept ML on CPU anyway, and the README's GPU section explains why:
- Immich's ML code pins the last onnxruntime release built for CUDA 12, with a note about moving to CUDA 13. CUDA 13 drops Maxwell cards, so the 970 will probably stop working after some future upgrade. You can't hold ML back on its own, because the server and ML must run the same version.
- The card has only 3.5 GB of fast memory, and Jellyfin already uses it for transcoding.
- The README also has the steps to try CUDA, without touching the driver.

**What changed:**
- **`tools/immich/compose.yaml`**: four containers, based on Immich's official compose file for v3.3.5 (the current release):
  - `immich`, the server, on port **8097**, family audience, with the template's labels.
  - `immich-machine-learning`, the CPU image.
  - `immich-postgres`, Immich's VectorChord Postgres image, pinned to the exact tag and digest from the official file.
  - `immich-redis`, Valkey pinned to `9.0.7`. Upstream uses the floating `valkey:9` by digest, and I couldn't match that digest to a version.

  Every container has the logging cap and a healthcheck. Only the server publishes a port. The library is at `${APPDATA_PATH}/immich/library`, and the ML model cache is also under appdata.
- **Backups**: `backup.sh` doesn't need a pre-dump hook. Paperless and Mealie have none; they're simply backed up while running. Immich makes its own database dump every night at 02:00 into `library/backups`, which is before the 04:00 restic run. So I excluded only the live Postgres files and the model cache in `backup-excludes.txt`. The thumbnail and transcoded-video folders stay in the backup: Immich won't start if any data folder loses its marker file.
- **`tools/immich/README.md`**: first-run steps for Dan (a letters-and-digits DB password, admin account, checking the dump schedule, family accounts, the phone app over LAN or Tailscale), plus where data lives, health checks, the GPU section, upgrades and restore.
- **Other docs**: a CLAUDE.md layout line and a port row for 8097; `IMMICH_DB_PASSWORD` in `.env.example`; a line in `docs/README.md`; four not-yet-run healthcheck rows in `docs/m1-core.md`; an Immich row and note in `docs/restore-runbook.md`.

**Checks:** `compose-lint.py` finds nothing repo-wide or on the new file. `scripts/check.sh` passes everything: bash -n, py_compile, shellcheck, compose-lint, and 63 unit tests.

**Not done:**
- The healthchecks haven't been run in live containers, so they're marked "not yet run live".
- The monthly restore drill's list is full (one service per month), so I didn't add Immich to it.
- `.claude/autoharness/last_run.json` shows as deleted and there are new session files there. The session tooling did that, not my edits, so leave them out of the commit.