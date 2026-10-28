# Install the missing cron jobs and let deploy-idea.sh re-run itself after a self-update

Value: 5   (removes a real risk: disk alerts, the image digest and the drift check have never run on a schedule)
Effort: 1  (one install-cron.sh run plus a small re-exec step in deploy-idea.sh)
Risk: 1    (dan's crontab and one script; no containers, no secrets)
Score: 25
Source: scout 2026-10-16

## Problem
`scripts/install-cron.sh --check` (2026-10-16 10:12 UTC) reports 5 of its 10 entries missing from dan's
crontab: disk-space-check (daily 09:10), arr-missing-search (Sun 02:30), storage-cleanup report (Sun 10:00),
image-check (Mon 09:10) and the daily `install-cron.sh --check --notify` itself. The crontab was last
replaced 2026-10-14 15:11:27 (`journalctl _COMM=crontab`). All five jobs were merged after that.
`journalctl -t` shows 0 lines for image-check, arr-missing-search, storage-cleanup and install-cron.
disk-space-check's 91 lines all come from build-time tests (Oct 15 22:27-22:28). So the Disk Space Alert in
`ideas/done/` has never protected anything, Monday's image digest won't run, and the drift check can't
report that it is missing.

Cause: install-cron-on-deploy (34a9a66) added the cron step to deploy-idea.sh. But bash kept running the
old copy of the script after `git merge` replaced the file, so the deploy that brought the step in ran
without it.

## Proposal
- Runbook step for Dan: run `scripts/install-cron.sh` once, then `--check` to confirm all 10 entries.
- `scripts/deploy-idea.sh`: after the merge, if `scripts/deploy-idea.sh` is in the merged diff, `exec` the
  new copy in a post-merge mode (cron install, checks, image prune, push, Discord). A self-update then takes
  effect in the same deploy. Guard against an exec loop (an env flag or an explicit `--post-merge` arg).
- Optional: add a "cron: in sync / N missing" line to the dashboard status file, so the admin view and
  Hermes see drift too.
Touches only `scripts/deploy-idea.sh`, the docs and the optional status line. No new ports or containers.

## Existing tools checked
- scripts/install-cron.sh (git log 16fe391, 08a4fcd, 6a89b00, 3cbc9fc, bf8ed6d): the installer works; it
  just never ran after these merges.
- scripts/deploy-idea.sh lines 160-210: the cron step exists, but the running process loads it too late.

## Rough plan
1. Dan runs install-cron.sh. Verify with `--check` and, the next day, with `journalctl -t disk-space-check`.
2. Split deploy-idea.sh into a merge part and a post-merge part. Re-exec the new file when it changed in the
   merge, and test with a dummy branch that touches deploy-idea.sh.
3. Optional: add the cron-drift line to the status file and the dashboard admin view.
4. Document it in docs/m5-pipeline.md.

_Approved on the dashboard, 2026-10-16._

## Plan
Goal: make deploy-idea.sh run its post-merge steps from the newly merged copy when a deploy changes the script itself, so a self-update takes effect in the deploy that brings it in.
Kind: change to scripts/deploy-idea.sh
Status of step 1 in the note: done already. `crontab -l` (checked 2026-10-16) has all 10 `# homelab` entries that match install-cron.sh, so nothing to install. The optional status-file line is left out: the daily `install-cron.sh --check --notify` Discord already reports drift. Dan can queue it as its own idea.
Files:
- scripts/deploy-idea.sh: changes listed below
- docs/m5-pipeline.md: in the Deploy bullet (after the cron sentence, about line 95), add one sentence. When the merge changes deploy-idea.sh, the script execs the new copy as `deploy-idea.sh --post-merge <slug>`, so that copy runs the steps after the merge (start services, cron, checks, prune, push, drop branch, Discord). The lock stays held. `--post-merge` is a stable interface, and you can re-run it by hand after a failed post-merge step. Also add `scripts/deploy-idea.sh --post-merge <slug>` to the command block near line 112, with a short comment.
deploy-idea.sh changes:
1. Option loop: add `--post-merge) POST=1 ;;`. Initialise `POST=0` next to YES/SENSITIVE_OK. Add a usage line to the header comment: `--post-merge <slug>  the steps after the merge (internal: re-exec after a self-update; or by hand)`.
2. Move lines 165-215 (from the "Start or update" comment to the final echo) unchanged into a function `post_merge()`. Use locals for dirs/services/built/d/svc/state. Before the function runs, set `$s`, `$name` and `$changed`. Put the function above the arg dispatch, near drop_build.
3. Post-merge entry, placed before the main `s="$1"` deploy path (after the reject block):
   `if (( POST )); then` check that `s="${1:-}"` matches `^[a-z0-9][a-z0-9-]*$`. Do NOT call `lock` when `DEPLOY_IDEA_REEXEC=1`: fd 9, which holds the flock, is inherited across exec, and running `exec 9>` again would release the lock. Call `lock` otherwise (a run by hand). Then require HEAD on main and `git log -1 --format=%s HEAD` starting with `Merge idea/$s: `, else `die "HEAD is not the merge of idea/$s"`. Set `name` = that subject with the `Merge idea/$s: ` prefix removed and `changed="$(git diff --name-only HEAD^1 HEAD)"`, then call `post_merge` and `exit 0`.
4. Normal path: right after the `git merge` line (163), add:
   `if grep -qx 'scripts/deploy-idea.sh' <<<"$changed" && [[ -z ${DEPLOY_IDEA_REEXEC:-} ]]; then echo "== deploy-idea.sh changed: continuing with the new copy"; DEPLOY_IDEA_REEXEC=1 exec "$REPO/scripts/deploy-idea.sh" --post-merge "$s"; fi`
   After that, call `post_merge`. The env flag guards against an exec loop: the new copy never execs again.
New service: none
New env vars: None (DEPLOY_IDEA_REEXEC is internal, not in .env.example)
Checks the builder must run:
- `bash -n scripts/deploy-idea.sh` and `shellcheck scripts/deploy-idea.sh` (installed at /usr/bin/shellcheck; no new warnings compared with `git show main:scripts/deploy-idea.sh | shellcheck -`)
- Throwaway test in the scratchpad, never on the real repo or crontab:
  - Make a bare repo B and `git clone` the worktree branch into C, with origin = B, on branch main.
  - In C, replace scripts/install-cron.sh, scripts/discord.sh and scripts/image-prune.sh with `echo stub-<name> "$@"` stubs, and commit.
  - Make branch idea/t that appends a comment to scripts/deploy-idea.sh and adds ideas/done/t.md (`# Idea: T`). The commit message must include the line `Reviewed-by: idea-reviewer`.
  - Run `scripts/deploy-idea.sh --yes t` in C. Expect "continuing with the new copy", exactly one `stub-install-cron.sh --check`, "Deployed t", branch idea/t gone and B updated.
  - Repeat with a branch u that doesn't touch deploy-idea.sh: no re-exec line, same end result.
  - Then run `DEPLOY_IDEA_REEXEC=1 scripts/deploy-idea.sh --post-merge nope`: it must die with "HEAD is not the merge".
Review focus:
- Re-exec loop -> the new copy, run with DEPLOY_IDEA_REEXEC=1, never execs again, and post-merge steps run exactly once.
- Lock across exec -> fd 9 stays open through exec, and the re-exec'd copy doesn't reopen it, so the dashboard runner and the loop can't get onto main mid-deploy.
- `--yes` via idea-actions.py (no TTY) -> the post-merge copy never prompts.
- `--post-merge` run by hand or with a wrong slug -> it refuses unless HEAD is that idea's merge commit, and doesn't push or drop anything.
- Behaviour unchanged when deploy-idea.sh isn't in the diff -> same output and order as before (services, cron, checks, prune, push, drop, Discord).
Docs: docs/m5-pipeline.md Deploy bullet + command block. No CLAUDE.md change.

## Manual steps
None. The crontab is already in sync (`scripts/install-cron.sh --check` prints "cron: in sync"). Optional next-day check: `journalctl -t disk-space-check --since today`. This deploy is the one that adds the re-exec, so it still runs the old copy for its own post-merge steps. That is expected, and those steps haven't changed.

## Review notes
1. The plan's scratch-repo test (re-exec run, a branch that leaves deploy-idea.sh alone, and `--post-merge nope`) was never run. The permission system denied it, and it denied my scratch git repo too. I traced those paths by reading the code instead. Dan may want to watch the first deploy that changes deploy-idea.sh.
2. shellcheck is not installed (`which shellcheck` finds nothing), even though the plan says it is at /usr/bin/shellcheck. Only `bash -n` was run, and it passes.
3. /home/dan/homelab/.worktrees/install-missing-cron-jobs/scripts/deploy-idea.sh:195. If the done note has no title, `name` is empty. Git's `-m` cleanup then trims the subject to "Merge idea/<slug>:" with no trailing space. The `"Merge idea/$s: "*` match fails, so a re-exec'd post-merge would die after the merge: nothing started, nothing pushed, and the branch is kept. This is an unlikely edge case, because notes always get a title. Matching `"Merge idea/$s:"*` and then stripping the leading space would cover it.
4. deploy-idea.sh:190-199. Running `--post-merge <slug>` by hand after a post-merge that already completed runs every step again. It then fails at `git branch -D` inside drop_build because the branch is gone, so it exits non-zero with no Discord line. That does no harm, but the docs call the command something you can safely re-run.
5. Option parsing accepts `--post-merge drop x` or `--post-merge check x`, and those go to the drop/check paths with POST ignored. This is cosmetic.

## Declined to judge
- The optional cron-drift line in the status file: the plan leaves it out on purpose and suggests it as a separate idea.
- Running install-cron.sh once (step 1 of the idea): the plan records that the crontab is already in sync, so there was nothing to build.
- `--post-merge` doesn't check for uncommitted changes on main: the plan doesn't ask for it, and on the re-exec path the old copy has already checked.
