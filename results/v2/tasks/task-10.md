CLAUDE.md is down from **186 to 122 lines** (106 → 47 non-blank lines outside the tables). The full scripts list now lives in `scripts/README.md` and the Claude Code kit detail in `docs/claude-kit.md`. `scripts/check.sh` passes.

**Scripts list**
- **`scripts/README.md` (new, 56 lines):** all 48 script bullets, one per script, same text as before (I checked with a diff). Every `.sh`, `.py` and `.txt` file in `scripts/` is listed. The old list had one ordering mistake: `secret-scan.sh` came after `seerr-*`. It's now in its correct alphabetical spot.
- **What's left in CLAUDE.md's `scripts/` entry:** a pointer to `scripts/README.md` and three rules:
  - A new script gets its bullet in alphabetical order, in the same change.
  - Every cron job runs through `cron-run.sh <name> <timeout> [--ok codes] <cmd>` and is two files, `scripts/cron.d/<name>.cron` plus the Kuma `compose.d/cron-<name>.yaml` fragment, with a link to `docs/new-cron-job.md`.
  - `dc.sh` is used for compose and `check.sh` runs the local checks.

**Other reference sections moved out**
- **Claude Code kit:** the full section went to `docs/claude-kit.md` (29 lines, text unchanged). CLAUDE.md keeps a short version: the skill names, what `guard.py` blocks, and the permission rules, including "a new core service must be added there".
- **Layout `tools/` entry:** cut from 12 lines to 4. It now lists the service names and points to `docs/services.md` (which already has each tool's description) and `docs/README.md` (which indexes the per-tool READMEs). I kept Hermes's limits: no port, read-only, writes only to `ideas/proposed/`.
- **Kept as they were:** Rules, Access model, Dashboard labels, Ports, and the `ideas/` entry. The `ideas/` entry contains rules, such as "the loop never reads `ideas/proposed/`".

**References updated to `scripts/README.md`**
- **Skills:** `rules-audit`, `script-change-sync` and `claude-hook-maintenance`. The last one now compares the hooks against `docs/claude-kit.md`.
- **Agents:** the Docs line in `idea-planner`'s template, and `idea-reviewer`'s docs check.
- **Docs:** `docs/new-cron-job.md` (adding and removing a job), `docs/m5-pipeline.md` (merge-friendly registries) and `docs/README.md`. The index now has rows for `scripts/README.md` and `docs/claude-kit.md`.
- **Queued idea notes:** `ideas/jellyfin-watch-stats.md` and `ideas/terminal/pyright-lsp-for-build-loop.md` also said "add it to the CLAUDE.md scripts list", so I updated them too, although `ideas/` was outside the folders you named.
- **Unchanged on purpose:** `docs/m6-research.md:207` is a dated build record. `compose-lint.py`, `service-catalog.py` and the `add-service` skill read only the Ports table, which is unchanged.

**Checks:** `bash scripts/check.sh` passed all six stages: bash -n, py_compile, shellcheck, compose-lint, service-catalog `--check`, and 73 unit tests.

**Left undone:** `ideas/terminal/memory-simple.md` is a queued plan that does this same CLAUDE.md cleanup, but it moves the list to `docs/scripts.md` instead. I didn't change it. It needs re-planning (drop that part, or point it at `scripts/README.md`) before Dan builds it, or it will fight this change. Nothing is committed.