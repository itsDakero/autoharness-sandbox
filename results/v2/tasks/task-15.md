I reviewed the 16 commits after ebbaa66 against the CLAUDE.md rules, using the rules-audit skill. The work holds up. I found one small issue and fixed it, and `scripts/check.sh` passes.

**Fixed**
- `scripts/service-catalog.py` wasn't marked executable (`100644`), even though it starts with a shebang and the README says to run it directly. I ran `chmod +x` and `git update-index --chmod=+x`, so the change is staged for the parent session to commit.

**Checks run, all passed**
- **New services** (`tools/beszel`, `tools/immich`):
  - Every image is pinned to an exact version; immich-postgres is also pinned to a digest.
  - Each service has its own healthcheck and the 10m×3 log cap.
  - Each web service publishes exactly one port (beszel 8089, immich 8097). Both ports are in the CLAUDE.md Ports table and carry the full Traefik, dashboard and Kuma labels.
  - App data is under `${APPDATA_PATH}/<service>/`.
- **docker.sock**: the Beszel agent reaches Docker through `docker-socket-proxy` on the `socket-proxy` network. The proxy still allows only GET requests (`POST: 0`) and is still the only place `docker.sock` is mounted.
- **`/mnt/media`**: mounted `:ro`.
- **Core-service ask rule**: no new core service was added. Both new services are in `tools/`, which the wildcard covers.
- **`.env.example`**: the new keys (`IMMICH_DB_PASSWORD`, `BESZEL_AGENT_KEY`, `BESZEL_AGENT_TOKEN`) are listed with comments. No `.env` was committed.
- **Backup excludes**: Immich's live Postgres files and model cache are excluded, and its nightly database dump is kept.
- **Scripts**: every script in `scripts/` is executable now. The new ones (`check.sh`, `compose-lint.py`, `docs-index-check.sh`, `restore-drill.sh`, `service-catalog.py`) all have a bullet in `scripts/README.md` in alphabetical order. The tests in `scripts/tests/` are `100644`, the same as the existing `test_guard.py`.
- **Cron job `docs-index-check`**: it has a `scripts/cron.d` entry run through `cron-run.sh` with `--ok 0,1`, and a matching Kuma push monitor with an 8-day interval and a 16-character token suffix. Its `--dry-run` reports every doc indexed.
- **Restore drill**: it runs from systemd units (service, timer, failure alert) rather than cron because it needs root. `bootstrap.sh` installs and enables them, and the change stays idempotent.
- **Docs**: all new docs are indexed in `docs/README.md`. The material cut from CLAUDE.md was moved into `scripts/README.md` and `docs/claude-kit.md`, not lost.
- **Tests**: `scripts/check.sh` ran before and after the fix. All six stages passed, including 126 unit tests. shellcheck ran and wasn't skipped.

**Left undone (proposed fixes)**
1. `.claude/settings.json` has no `permissions` block and doesn't wire up `guard.py`, but CLAUDE.md and `docs/claude-kit.md` still describe both. This isn't a regression in the range: the seed commit ebbaa66 ("drop guard and permission rules") removed them on purpose. If this work goes back to the real repo, the real settings should be kept. Otherwise add a note that the sandbox runs without them.
2. The `rules-audit` skill points to a `cron-job-setup` skill that doesn't exist; it should say `add-cron-job`. I left it alone because autoharness manages that skill file, so the fix should go through autoharness.

I couldn't run anything against real containers or hosts (no Docker daemon or `.env` in the sandbox), so this review is static.