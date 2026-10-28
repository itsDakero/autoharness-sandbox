I've added the Stop hook in `.claude/hooks/stop-check.sh`. Piped tests with fake transcripts behave as intended, and `scripts/check.sh` passes.

**What changed**
- **`.claude/hooks/stop-check.sh`** (new, executable): when `git status` shows changes (untracked files included) under `scripts/`, `.claude/hooks/` or to any `compose.yaml`, it reads the transcript from `transcript_path`. If no Bash call ran `scripts/check.sh`, `unittest` or `compose-lint.py`, it blocks the stop once (`{"decision":"block","reason":…}`, listing up to 5 changed files) and asks Claude to run `scripts/check.sh`.
  - If `stop_hook_active` is true it never blocks, so it can't block twice in a row.
  - It fails open: an exit trap makes every path exit 0, covering a missing jq, transcript or git checkout and bad input. Broken transcript lines are skipped.
  - **One addition you didn't ask for:** a check run only counts if it comes after the last Edit/Write of a watched file, so a run from before the edits doesn't satisfy it. Changes made through Bash (`sed`, heredocs) don't count as edits.
- **`.claude/settings.json`**: added a `Stop` entry with a 10 s timeout. The existing plugin, marketplace and PostToolUse settings are unchanged.
- **Docs**: two lines in the Claude Code kit section of `CLAUDE.md`, and a fuller entry in `docs/claude-kit.md`.

**Checks**
- `bash -n` and `shellcheck` on the hook are clean.
- Piped hook-input tests, all exit 0:
  - **Blocks:** changes with no check run (a user message that only mentions `check.sh` doesn't count); a check run followed by a later edit; a new untracked `compose.yaml`.
  - **Allows:** `stop_hook_active` is true; a check run after the edit; a `unittest` run, with a junk transcript line skipped; a clean tree; a missing transcript; garbage or empty input; no jq on `PATH`; a directory that isn't a git checkout.
- `scripts/check.sh`: all passed (bash -n, py_compile, shellcheck, compose-lint, service-catalog, 126 unit tests).
- I removed the test files from the repo. The fake transcripts are in `/tmp/claude-0/-home-user-autoharness-sandbox/5dadb8f6-c15b-494d-932d-89439abbe293/scratchpad/`.

**Not done**
- I couldn't test the hook in a real Claude Code session, only with piped JSON.
- In this sandbox, `.claude/settings.json` only wires `compose-check.sh`. `docs/claude-kit.md` says `guard.py` (PreToolUse) and the `loop-alert.sh` hooks are wired too, but they aren't. That was outside this task, so I left it alone.
- Nothing is committed.