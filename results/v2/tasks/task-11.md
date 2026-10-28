I wrote the `/add-cron-job` skill and used it to add the weekly `docs-index-check` job. Everything ran locally and passes; nothing has run on the server yet.

**The skill** (`.claude/skills/add-cron-job/SKILL.md`, 92 lines) is built from `docs/new-cron-job.md`, `cron-run.sh`, `install-cron.sh` and the omada-ap-check example pair. It covers everything you listed. When loaded, it also shows every cron time already in use, so a free minute is easy to pick. Two choices to check:
- I left out `disable-model-invocation`, which `add-service` sets. That lets Claude use the skill when a task needs a scheduled script. Add the flag if you want it only when you type `/add-cron-job`.
- Its section on testing without a server includes a `docker compose ... config -q` command that uses `.env.example`, because `dc.sh` needs the real `.env`.

**The new job:**
- `scripts/docs-index-check.sh` lists every file in `docs/` except `README.md`. A file counts as listed if `docs/README.md` names it, or names a folder it sits in (so `docs/fitness-analysis/` covers its notes).
- If any are missing, it posts one Discord line naming them and exits 1. It exits 2 if the Discord post fails or on bad arguments. `--dry-run` prints without posting, and `-h` shows help.
- It keeps no state, so the Discord line repeats each week until the index is fixed.
- `scripts/cron.d/docs-index-check.cron` runs it Mondays at 09:35 with a 300 s timeout and `--ok 0,1`. 09:35 isn't used by any other job.
- `core/uptime-kuma/compose.d/cron-docs-index-check.yaml` is the Kuma monitor: token suffix `docsindexcheck00` (unique), interval 691200 (8 days).

**Docs updated:** a `scripts/README.md` bullet in its alphabetical spot, the weekly-jobs and `--ok 0,1` lines in `docs/m1-core.md`, the skill lists in `CLAUDE.md` and `docs/claude-kit.md`, and a pointer to the skill in `docs/new-cron-job.md`.

**Checks run:**
- `bash -n` and shellcheck on the script are clean.
- `--dry-run` on the real `docs/`: everything is listed, exit 0.
- A test `docs/` with a file listed by name, one covered by its folder, and two unlisted (one with a space in its name): only the two unlisted ones were reported, exit 1. A bad argument exits 2.
- Through `cron-run.sh` with no `.env`, the job's exit code (1) came back unchanged.
- `install-cron.sh --check` against a test crontab holding every other job: only the new job shows as `missing:`.
- Every cron entry has a Kuma monitor file and vice versa, and no token suffix is used twice.
- The Kuma `config -q` merge passed.
- `scripts/check.sh` passed all steps, including 73 unit tests.

**Not done:**
- No real Discord post or Kuma push, and no install from main. That deploy step is yours: run `install-cron.sh` from main, then `scripts/dc.sh core/uptime-kuma up -d`.
- No commit, as instructed.
- `git status` also shows `.claude/autoharness/last_run.json` as deleted. That isn't from this change.