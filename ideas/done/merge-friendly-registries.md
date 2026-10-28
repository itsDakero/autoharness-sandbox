# Merge-friendly registries: new cron jobs and scripts no longer conflict between idea branches

Depends on: lms-picker (deploy it first, or this branch conflicts with it on the same lines)
Value: 3   (stops the recurring "merge main into idea/<slug>" chore; the FPL chain will hit it every stage)
Effort: 2  (install-cron.sh reads a folder, a few files split, docs)
Risk: 2    (touches install-cron.sh, which rewrites Dan's crontab, and the Kuma compose labels)
Score: 12
Source: Dan 2026-10-26 (session with Claude, after merging main into morning-brief and lms-picker twice)

## Problem
Every idea that adds a cron job edits the same few shared spots, so once one idea branch is deployed,
every other waiting branch conflicts in `scripts/deploy-idea.sh` ("merge conflict; nothing deployed"):
- `scripts/install-cron.sh`: the `ENTRIES="..."` string; new jobs append at its end, and the closing `"`
  sits on the last entry.
- `CLAUDE.md`: the `scripts/` bullet packs many scripts into one very long line.
- `core/uptime-kuma/compose.yaml`: each cron job's `kuma.cron-<name>.push.*` labels are appended at the
  same place, just before `homelab.external.cron.*`.
- `.env.example`: new keys appended at the end.
Every conflict so far was "keep both sides". Splitting lines alone is not enough: two branches inserting
at the same spot still conflict, line by line or not.

## Proposal
- **Cron entries, one file per job**: `scripts/cron.d/<name>.cron`, one crontab line each, in the same
  `$R <name> <timeout> ...` form (or the expanded form; planner decides). `install-cron.sh` builds
  `ENTRIES` from the folder sorted by name, so `--check`, drift detection, the Discord drift note and
  `deploy-idea.sh`'s reinstall all behave as today. Move every current entry over; the installed crontab
  must come out the same (compare `crontab -l` before and after, with only the order allowed to change).
- **Kuma push monitors**: find a layout where a new cron job's monitor is added without editing lines
  next to other jobs' monitors. Options for the planner to check: an extra compose file per job merged
  with `-f`/`include`, a label block generated from `scripts/cron.d/` (the push token and interval could
  live in the `.cron` file's comment), or a `.gitattributes` `merge=union` on a file holding only these
  labels. A plain `merge=union` on the whole compose file is not OK (it would duplicate changed lines).
- **`CLAUDE.md` scripts list**: one script per line, in alphabetical order, so new entries land at
  different places. Same for the cron-job list in docs if there is one.
- **`.env.example`**: new keys go in the section of the service they belong to, not at the end (note the
  rule in `templates/` or `docs/m5-pipeline.md` so the builder follows it).
- Update `docs/m5-pipeline.md` (and the builder/planner agent notes only if they don't sit under
  `.claude/`; if they do, list the change for Dan instead) so new ideas use the folder.

## Done when
- Two test branches off main that each add a cron job + Kuma push monitor + script line merge into main
  one after the other without conflicts (try it with `git merge-tree`, then throw the branches away).
- `scripts/install-cron.sh --check` reports no drift right after deploy.

## Plan
Goal: Each cron job and its Kuma push monitor go in their own files, and the shared lists get one entry per line, so idea branches that add jobs merge without conflicts.
Kind: change to install-cron.sh, dc.sh, deploy-idea.sh, core/uptime-kuma, docs
(Depends on lms-picker. It is deployed: ideas/done/lms-picker.md exists and the lms-* cron entries and labels are on main.)

Files:
- scripts/cron.d/<name>.cron: new, one file per current ENTRIES line (25 files: qbit-watchdog, idea-actions, seerr-route,
  ops-actions, ha-backup-check, scrutiny-check, disk-space-check, arr-missing-search, storage-cleanup, image-check,
  card-prices, self-check, morning-brief, fitness-weekly, fpl-bootstrap, fpl-fixtures, fpl-odds, fpl-odds-deadline,
  fpl-gameweek, fpl-understat, lms-odds, lms-alerts, lms-results, fpl-solve, fpl-deadline). Filename = the
  cron-run name. Each file has optional `#` comment lines plus exactly one entry line, copied as written today
  without the trailing ` # homelab`, e.g. `* * * * * $R qbit-watchdog 300 $REPO/scripts/qbit-watchdog.sh`
  (`$R` and `$REPO` stay as literal text).
- scripts/install-cron.sh: drop the inline ENTRIES string. Build ENTRIES from `$REPO/scripts/cron.d/*.cron` in glob
  (name) order. Per file: skip blank lines and `#` lines. There must be exactly one entry line. Swap in the literal
  `$REPO` first, then `$R`, using bash pattern replacement (no eval), then append ` # homelab`. Errors go to stderr
  and exit 2, before any crontab read or write: no .cron files, a file with 0 or 2+ entry lines, a filename that
  doesn't match `^[a-z0-9][a-z0-9-]*\.cron$`, or an entry whose 7th field (the name) differs from the filename.
  The error check runs in both install and --check modes. check(), the CRON_LIST override and --notify stay the
  same. Update the header comment.
- core/uptime-kuma/compose.d/cron-<name>.yaml: new, one per job. Move that job's 4 `kuma.cron-<name>.push.*` labels
  out of compose.yaml, values unchanged, as `services: uptime-kuma: labels: [...]`. Put a 1-line comment on top
  pointing at scripts/cron.d/<name>.cron.
- core/uptime-kuma/compose.yaml: remove every `kuma.cron-*` label. Keep the two comment lines about the
  dead-man's switch and the token, plus "per-job labels live in compose.d/". Keep `homelab.external.cron.*`.
- scripts/dc.sh: after `-f "$dir/compose.yaml"`, add `-f` for each existing `"$dir"/compose.d/*.yaml` in glob
  order. Do nothing when the folder is missing or empty: guard the glob with `[[ -e $f ]]` or nullglob. All
  other dirs behave exactly as today.
- scripts/deploy-idea.sh: in post_merge, map changed files under `<dir>/compose.d/` to `<dir>`, e.g.
  `| sed 's#/compose\.d$##'` after dirname, before `sort -u`. A branch that only adds a fragment then still
  runs `dc.sh core/uptime-kuma up -d`.
- scripts/idea-actions.py: add `scripts/cron\.d/.*` to AUTO_PROTECTED. A new cron job is not auto-deployed today,
  because install-cron.sh is protected; this keeps that true.
- .env.example: add one comment line under the top "Copy to .env" line: new keys go in their service's
  section, not at the end. Move nothing.
- CLAUDE.md: rewrite the `scripts/` bullet in Layout as nested sub-bullets, one script per line, alphabetical by
  filename. Keep each script's current text. Update the `install-cron.sh` text to "entries from scripts/cron.d/".
  Change nothing else.
- docs/m1-core.md: rewrite the "Add a job" bullet (line ~92). It becomes `scripts/cron.d/<name>.cron` (one line)
  plus `core/uptime-kuma/compose.d/cron-<name>.yaml` (the 4 labels). Say core/uptime-kuma must only be run
  through dc.sh, or the cron labels are dropped and AutoKuma (ON_DELETE=delete) deletes the monitors.
- docs/m5-pipeline.md: add a short "Merge-friendly registries" section with 4 rules: the cron.d file, the
  compose.d fragment, CLAUDE.md scripts one per line in alphabetical order, and .env.example keys in the service's
  section. Mention that deploy-idea maps compose.d to its service.

New service: none
New env vars: None

Checks the builder must run (WT = the worktree):
- `bash -n scripts/install-cron.sh scripts/dc.sh scripts/deploy-idea.sh`; `python3 -m py_compile scripts/idea-actions.py`
- `scripts/dc.sh $WT/core/uptime-kuma config -q`
- Labels unchanged: `git show main:core/uptime-kuma/compose.yaml | grep -o 'kuma\.cron-.*' | sort` must equal
  `cat core/uptime-kuma/compose.d/*.yaml | grep -o 'kuma\.cron-.*' | sort`, and compose.yaml has no `kuma.cron-`.
- Same crontab: `crontab -l | sed "s#/home/dan/homelab/#$WT/#g" > <scratch>/cur` (read only). Then
  `CRON_LIST=<scratch>/cur $WT/scripts/install-cron.sh --check` prints "cron: in sync". Never run install-cron.sh
  without --check.
- Every cron.d name has a compose.d/cron-<name>.yaml and the reverse (a one-line ls/diff).
- Error paths: copy scripts/install-cron.sh and a cron.d with a 2-line file, an empty file and a name mismatch
  into a scratch REPO layout. --check must exit 2 for each.
- Merge test: from this branch make temp branches t1 and t2. Each adds a cron.d file, a compose.d fragment, a
  CLAUDE.md scripts line in its alphabetical spot and an .env.example key in a different section. Use
  `card-test` and `ops-test`. `git merge-tree --write-tree t1 t2` exits 0. Then `git branch -D t1 t2`.

Review focus:
- cron.d empty, missing or holding a bad file -> exit 2 with the file named, crontab untouched (no install that
  wipes every job). The daily self-check goes down in Kuma instead of a silent pass.
- A literal `$REPO` must be replaced before `$R` -> no entry ends up with `/…/cron-run.shEPO/scripts/…`. The
  in-sync check above proves it.
- compose.d not loaded (core/uptime-kuma run without dc.sh, or a glob bug) -> AutoKuma deletes the 25 cron monitors.
  dc.sh must always add the fragments, and config -q plus the label diff must pass.
- dc.sh on a dir without compose.d -> exactly the same command as today (no stray `-f` and no literal `*.yaml`).
- A branch that changes only a fragment -> deploy-idea restarts core/uptime-kuma, not nothing.

Docs: CLAUDE.md scripts list (one per line, alphabetical); docs/m1-core.md "Add a job"; docs/m5-pipeline.md new
section; .env.example rule comment. docs/README.md unchanged.

## Manual steps
- Deploy with `scripts/deploy-idea.sh merge-friendly-registries`. It recreates uptime-kuma, because its compose
  files changed. Then check:
  - `scripts/install-cron.sh --check` prints "cron: in sync".
  - `scripts/kuma-status.py cron` still lists all 25 cron-* monitors, with no deletes in
    `scripts/dc.sh core/uptime-kuma logs --tail 50 autokuma`.
- Kit notes under `.claude/` to update by hand, so this plan stays out of the terminal queue:
  - `.claude/agents/idea-builder.md`, near line 19 ("New env vars: ... `.env.example`"): add "in that service's
    section, not at the end; new cron jobs = scripts/cron.d/<name>.cron + core/uptime-kuma/compose.d/cron-<name>.yaml;
    CLAUDE.md scripts list one per line, alphabetical".
  - `.claude/agents/idea-planner.md`, line 86: the same pointer, in one line.
  - Optional: `.claude/hooks/compose-check.sh` only re-checks `compose.yaml` edits. You could extend it to
    `compose.d/*.yaml`.
- Branches already waiting that add cron jobs, or edit the old ENTRIES/labels block, will conflict once more
  against this change. Move their entries into the new files when you merge.

## Review notes
1. `/home/dan/homelab/.worktrees/merge-friendly-registries/scripts/install-cron.sh:26`: if a `.cron` file has a CRLF line ending, the `\r` passes the name check and ends up in the crontab line. `--check` then reports drift; it does not fail with exit 2. This is unlikely to happen, since editors here write LF. Stripping `\r` when the file is read would close it.
2. `AUTO_PROTECTED` in `/home/dan/homelab/.worktrees/merge-friendly-registries/scripts/idea-actions.py:51` covers `scripts/cron.d/` but not `core/uptime-kuma/compose.d/`. That means a Risk 1 auto-deploy could change or drop a monitor fragment, and AutoKuma would then delete that monitor. This matches what happened before with labels in `compose.yaml`, so it is not a regression.
3. The CLAUDE.md rule "One compose file per service" now has an exception for `compose.d/` fragments. The rule line itself was not updated, because the plan said to change nothing else in CLAUDE.md. Dan may want to add a short qualifier.
4. `.claude/hooks/compose-check.sh` only checks `compose.yaml` edits, so a fragment that mounted `docker.sock` would slip past the PostToolUse check. `guard.py` still checks commands, though. The plan already lists extending the hook as an optional manual step for Dan.
5. I did not run the merge test myself: making scratch branches and commits was denied by permissions. My reasoning says it passes. The new files are all separate, and the CLAUDE.md inserts for `card-test` and `ops-test` land far apart in the alphabetical list, so a 3-way merge will not conflict.

## Declined to judge
- Validating the uptime-kuma compose fragments against an already-running container (no recreate/delete check live): outside reviewer permissions; the plan covers it in the manual post-deploy checks.
- Whether other branches already waiting will conflict once more: the plan accepts this as a one-time cost and tells Dan in the manual steps.
