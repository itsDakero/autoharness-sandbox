shellcheck 0.9.0 was already installed. It now reports nothing on all 23 files (22 `scripts/*.sh` plus `.claude/hooks/compose-check.sh`). At the start it flagged 12 items in 7 scripts. Most were deliberate patterns, so the actual code changes are small and behaviour is unchanged. The hook script was already clean and wasn't touched.

**Fixed by category**
- **Parse ambiguity (SC1010):** `scripts/idea.sh` `waiting_taken` loops over the word `done`, which shellcheck reads as the loop keyword. I quoted it as `"done"`. Bash already ran it correctly, so this only makes the intent clear.
- **Needless `sed` subprocess (SC2001):** in `scan_ok` in both `scripts/idea.sh` and `scripts/deploy-idea.sh`, the `| sed 's/;/; /g'` step is now `f="${f//;/; }"`. The output is the same.
- **False positive from a function name (SC2032/SC2033):** in `scripts/loop.sh`, shellcheck mistook the `attach` in `tmux attach` for a call to the script's own `attach()` function. I renamed the function to `attach_session` and updated both callers.

**Suppressed on purpose** (each has a one-line reason on the comment line above the directive)
- **SC2015 (`A && B || C`)**, 3 places, all correct as written because the fallback is meant to run when either step fails:
  - the clean-tree check in `deploy-idea.sh` (`die` never returns)
  - the waiting-note check in `idea.sh` (`continue`)
  - `mkdir && chmod || { log; exit 0; }` in `loop-alert.sh`
- **SC2001 (`sed 's/^/  /'`)**, 3 places: these indent every line of a multi-line string, which a parameter expansion can't do neatly. One is in `deploy-idea.sh`'s sensitive-files list; the other two only showed up after I split a `;` line in each `scan_ok`.
- **SC2064 (trap expands now):** in `secret-scan.sh`, expanding `$tmp` when the trap is set is intended, because `tmp` is a local variable.
- **SC1090/SC1091 (can't follow `source`):** `backup.sh` (`/etc/restic/b2.env`, root-only) and `core-up.sh` (`.env`, git-ignored) load files that aren't in the repo.

A shellcheck directive only covers the next command, not the rest of a line. So in `backup.sh` and `core-up.sh` I split `set -a; . file; set +a` into separate lines. In `secret-scan.sh` I put `trap` on its own line, and in both `scan_ok`s I split the `echo …; sed …` line in two.

**Checks**
- `shellcheck scripts/*.sh .claude/hooks/*.sh` exits 0.
- `bash -n` passes on all 7 changed files: `backup.sh`, `core-up.sh`, `deploy-idea.sh`, `idea.sh`, `loop-alert.sh`, `loop.sh`, `secret-scan.sh`.
- `python3 -m unittest discover -s scripts/tests` passes.

**Not done:** nothing is committed. The changed scripts were only syntax-checked, not run, because they need tmux, git push, restic or Docker. The `.claude/autoharness/` and `.sidecar.json` changes in `git status` were already there and aren't mine.