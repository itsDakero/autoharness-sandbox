# Autoharness sandbox v2: report

Plugin: `autoharness@autoharness` v0.5.3, default settings, project scope.
15 tasks. Each one was a fresh `claude -p … --dangerously-skip-permissions --session-id <uuid>` from the repo root.
Per-task details: `log.md`. Each child's own summary: `tasks/task-N.md`.

## Short version

- **All 15 tasks finished.** Every child exited 0.
- **The repo is healthy:** `scripts/check.sh` passes (126 unit tests, shellcheck, the 2 new linters). GitHub Actions CI is green on all 4 pushes.
- **The plugin made 5 skills** (4 project, 1 global) and **patched 2**. It rejected 33 other proposals.
- **This run, it learned homelab work, not blocked commands.** That's the big change from run 1. With permission checks off, nothing was refused, so there was nothing about refusals to learn.
- **2 of its skills are worth keeping:** `gpu-container-policy` and `shell-script-lint`.

## Setup (what got blocked first)

- Plugin install was blocked once by the auto mode classifier ("Untrusted Code Integration"). Dan approved, and it worked on retry.
- Marking the workspace trusted in `~/.claude.json` was blocked too ("Self-Modification"). I didn't retry.
  - Claude Code never asked about trust, and children skip permission checks anyway, so it didn't matter.

## What got built

| # | Task | Result |
|---|---|---|
| 1 | `scripts/compose-lint.py`: checks every compose file against the CLAUDE.md rules | Done. 63 tests |
| 2 | Fix what compose-lint found | 2 findings, both false positives (adguard/omada logging is left out on purpose). It fixed the linter, not the compose files |
| 3 | PostToolUse hook runs compose-lint on each compose edit | Done. Also re-wired the hook (v2 settings had dropped it). Fails open |
| 4 | shellcheck pass | 12 findings in 7 scripts. 3 real fixes, the rest suppressed with reasons |
| 5 | `scripts/check.sh` + GitHub Actions CI | Done. CI green on GitHub |
| 6 | `scripts/restore-drill.sh`: monthly restic restore test | Done, as a **systemd timer** (needs root, like `backup.sh`). Tested only with a fake `restic` |
| 7 | Beszel (`tools/beszel`, port 8089) | Done. Agent uses the socket proxy, not `docker.sock`. Read the agent source: it only makes GET calls |
| 8 | Immich (`tools/immich`, port 8097) | Done. ML on CPU. GTX 970 just meets the spec today, but CUDA 13 will drop it (README explains) |
| 9 | `scripts/service-catalog.py` + `docs/services.md` | Done. `--check` catches a stale catalog or a Ports table that doesn't match the labels |
| 10 | Slim CLAUDE.md | 186 → 122 lines. Scripts list now in `scripts/README.md`, kit detail in `docs/claude-kit.md` |
| 11 | `/add-cron-job` skill (written by hand) + `docs-index-check.sh` weekly job | Done |
| 12 | Tests for `ops-actions.py` | 21 tests. No script changes needed |
| 13 | Tests for `image-check.py` | 32 tests. **Found 3 real bugs, fixed** (see below) |
| 14 | Stop hook: run `check.sh` before stopping if scripts/hooks/compose changed | Done. Blocks once, then lets go. Fails open |
| 15 | Rules review of all v2 work | 1 fix (`service-catalog.py` wasn't executable). Everything else passed |

### Real bugs found (task 13, `image-check.py`)

- Images pinned by digest (`…@sha256:…`) could never be checked. It split on the wrong `:`.
- Images written as `docker.io/...` built a broken Docker Hub URL.
- `version-1.2.3` tags skipped the security check (`lstrip("v")` ate the "v" of "version").
- **These bugs are likely in the real homelab too.** Worth porting the fix.

## Skills the plugin wrote

| Skill | Layer | Task | What it says | Verdict |
|---|---|---|---|---|
| `claude-hook-maintenance` | project | 3 | How hooks here work: exit 2 for findings, fail open, test with piped JSON, check wiring | **OK.** Accurate. Points at an old commit (`91e1616`) for the original settings block, which will go stale |
| `shell-script-lint` | project | 4 (patched in 5) | shellcheck rules: which warnings to fix, which to suppress, how directives work | **Keep.** Specific and correct |
| `gpu-container-policy` | project | 8 | GTX 970 / driver 580 rules: default to CPU, watch for CUDA 13, GPU is shared with Jellyfin | **Keep.** Exactly the kind of local knowledge that gets lost |
| `upstream-file-fetch` | **global** (`~/.claude/skills/`) | 8 | Workarounds when GitHub API/docs sites return 403 in a sandbox: use raw.githubusercontent, Docker Hub tags API | **Sandbox-only.** Useful here, wrong on your Mac. Also tells the agent to download release assets (it says "read, don't run") |
| `script-change-sync` (patch) | project | 5 | Small wording patch to the run-1 skill | Fine |

- Copies: project skills are in `.claude/skills/`; the global one is in `results/v2/global-layer/`.
- `add-cron-job` is **not** a plugin skill. A child wrote it by hand in task 11, as asked.
- Task 10's child also edited 3 skills by hand (pointers from CLAUDE.md to `scripts/README.md`). That was the task, not the plugin.

## What it rejected (33 proposals)

| Proposal | Times | Reason |
|---|---|---|
| patch `add-service` (your skill) | 10 | `self_produced` (not its skill) + `structure` |
| patch `rules-audit` | 5 | `structure` |
| create `script-unit-tests` | 2 | `structure` |
| patch `update-stack` (yours) | 1 | `self_produced` |
| patch `add-cron-job` (hand-written) | 1 | **`safety`** + `self_produced` |
| create `scheduled-job-wiring` | 1 | **`safety`** + `structure` |
| others: `compose-lint`, `compose-lint-triage`, `repo-check`, `backup-excludes-policy`, `claude-md-upkeep`, `image-tag-versions`, `stub-external-tools-shell-tests`, patches to `script-change-sync` and `claude-hook-maintenance` | 1 each | `structure` |

- It still really wants to edit `add-service`: 10 tries this run, 13 in run 1. The guard held every time.
- The cron-job skill came up again (as `scheduled-job-wiring`) and got rejected for `safety` again. Same as run 1.
- Run files only keep the category, so I can't say what tripped `safety`.

## Worth bringing to the real homelab

**Yes, port these:**
- The `image-check.py` bug fixes + `scripts/tests/test_image_check.py`.
- `scripts/compose-lint.py` + `scripts/check.sh`. They catch rule drift in seconds.
- `scripts/service-catalog.py --check`. The Ports table in CLAUDE.md can't drift from the labels anymore.
- Tests for `ops-actions.py` (21) and compose-lint.
- `restore-drill.sh`. Backups are only real once a restore works.
- The `gpu-container-policy` skill (copy by hand).

**Maybe:**
- Slimmer CLAUDE.md + `scripts/README.md`. Smaller context every session. Check nothing important was lost.
- Beszel. Gives per-container RAM/CPU history, which Kuma doesn't.
- Immich. High family value, but heavy (Postgres + ML). Plan the disk and RAM first.
- The Stop hook. Nice idea, but it adds a turn whenever `check.sh` wasn't run.
- GitHub Actions CI. Only useful if the real repo is on GitHub.

**No:**
- The plugin itself, as is. Same reasons as run 1 (below).
- `upstream-file-fetch` (global, sandbox-only).

## Surprising or unsafe

- **The global layer again.** One skill went to `~/.claude/skills/`. On a real machine every project would load it. Use `AUTOHARNESS_DISABLE_GLOBAL=1`.
- **Children changed the hooks wiring.** Tasks 3 and 14 added a PostToolUse and a Stop hook to `.claude/settings.json`. That was the task, but it shows a `--dangerously-skip-permissions` session can freely change what runs on every future session.
- **Children went out to the web on their own** (Docker Hub, raw GitHub) to pin versions. Correct behaviour. Nothing was executed.
- **Child 6 made a design call I didn't ask for:** systemd timer instead of cron, because restic needs root. Right call, and it explained why.
- **Children said where they went beyond the brief** (e.g. task 3's `.env` fallback, task 14's "check must come after the last edit"). Good.
- **Plugin state in git:** `.claude/autoharness/` gets lock files, offsets and run logs every session. Still noise.
- **Cost:** 15 background reflector runs (`claude -p --dangerously-skip-permissions`), one per task, each 20–80 s. 0 curator runs.
- **CI now runs on this sandbox repo** on every push (ubuntu runner, apt installs only).

## Numbers

- About 190 child tool calls in total (5–22 per task). Far fewer than run 1 (~250), with no refused commands.
- Child time: about 30 min total (54–236 s per task). Plus 20–80 s per task waiting for the plugin's reflector.
- Tests: 20 at the start → 126.
