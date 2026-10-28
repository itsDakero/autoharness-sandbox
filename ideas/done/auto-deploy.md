# Auto deploy

I think if I approve a low risk 1/5 idea and it doesnt need terminal to deploy we can auto deploy those ideas as 1/5 risk is very low anything higher should still come to me to deploy

_Added from the dashboard, 2026-10-19._

## Plan
Goal: auto-deploy reviewed builds of proposals Dan approved that carry `Risk: 1`, when nothing in them needs a terminal, a sensitive-file confirm or a manual step. Everything else still waits for Dan on the Deploy tab.
Kind: change to scripts/idea-actions.py (the every-minute runner). Nothing changes in deploy-idea.sh or `.claude/`.
Files:
- scripts/idea-actions.py: add `auto_deploy()`. main() calls it after the requests and before write_status(). Add a `--auto-dry-run` flag and update the docstring.
- docs/m5-pipeline.md: add a Stage D bullet "Auto-deploy (Risk 1)" (the rules below, how to pause it, the state file) and a `--auto-dry-run` line under Commands.
- CLAUDE.md: in the `idea-actions.py` layout entry, add "; auto-deploys approved Risk 1 builds (see m5)".

Eligibility. A ready build (reviewed, same test as write_status) is auto-deployed only if ALL of these hold. Read the note from `git show idea/<slug>:ideas/done/<slug>.md`:
1. Header (the text before the first `^## `, same rule as ideas.header in the dashboard): a `Risk:` line whose first integer is exactly 1. If there is no Risk line, the build isn't eligible. Dan's own idea-box notes have no Risk line, so they never auto-deploy.
2. The note has a line matching `^_Approved on the dashboard, \d{4}-\d{2}-\d{2}\._$`. The Proposed tab's Approve adds it (core/dashboard/app/ideas.py decide()), so this proves Dan approved it.
3. `deploy-idea.sh check <slug>` prints no `terminal` or `sensitive` lines. Reuse build_info().
4. Manual steps are empty or "None". Reuse build_info()["manual"] == "".
5. No changed file matches `^(\.env\.example|scripts/(deploy-idea\.sh|idea-actions\.py|idea\.sh|install-cron\.sh))$`. A new env var or a change to the deploy pipeline itself always goes to Dan.
6. The branch tip sha is not already in the state file (see Review focus).
Deploy at most one build per runner run, oldest `built` first. Run it with the existing `deploy(slug, sensitive_ok=False)`, which calls `deploy-idea.sh --yes`, so the script's own terminal/sensitive refusals still apply.

State and pause:
- State file `ACTIONS/auto-deploy.json` = {slug: {"sha": tip, "at": iso, "result": "done"|"failed", "message": str}}. Write it atomically with write_json, and record the sha BEFORE starting the deploy. Drop entries whose `idea/<slug>` branch no longer exists.
- Pause: if `ACTIONS/auto-deploy.off` exists, skip auto_deploy entirely and log it once per run to syslog.
- Discord: post "Auto-deploying (Risk 1): <title>" before the run. deploy-idea.sh posts "Deployed: ..." itself on success. On failure post "Auto-deploy failed: <title> (<last line>); it's on the Deploy tab".
- Result file: write `RESULTS/auto-<slug>-<epoch>.json` with action "deploy", so the dashboard's result history shows the auto-deploy like a button deploy. Log to syslog as `auto-deploy <slug>: <state>: <msg>`.
- `--auto-dry-run`: prints one line per ready build, `<slug> eligible` or `<slug> skip: <first failed rule>`. It writes nothing (no mkdir, no state, no lock, no deploy) and exits.

New service: None
New env vars: None
Checks the builder must run:
- python3 -m py_compile <worktree>/scripts/idea-actions.py
- <worktree>/scripts/idea-actions.py --auto-dry-run (must run without error with zero or more ready builds, and write nothing)
- git -C <worktree> diff --stat (only the 3 files above)
Review focus:
- deploy fails (merge conflict, container not up) -> the sha is recorded as failed, there is one Discord post and no retry every minute. A new push to the branch (new sha) can be tried once more.
- Dan clicks Deploy or Reject in the same minute -> the requests run first. If the branch is gone, auto_deploy skips it quietly; there is never a second deploy.
- the note has `Risk: 1` only below a `## ` heading (e.g. inside the plan or a Research section), or has `Risk: 1-2`/`Risk: 12` -> not eligible (header only, first integer exactly 1).
- several eligible builds -> one per run, so the runner lock isn't held across many deploys and button requests aren't stuck behind them for long.
- missing/corrupt auto-deploy.json -> treated as empty; it never crashes the runner (status.json must still be written).

Docs: m5-pipeline.md Stage D gets the new bullet plus the Commands lines `scripts/idea-actions.py --auto-dry-run` and `touch /srv/homelab/dashboard/actions/auto-deploy.off  # pause auto-deploy`. CLAUDE.md gets the one-line layout addition. No port table change.

## Manual steps
None (the cron entry already exists). To pause auto-deploy: `touch /srv/homelab/dashboard/actions/auto-deploy.off`; delete the file to resume.

## Review notes
1. /home/dan/homelab/.worktrees/auto-deploy/scripts/idea-actions.py, auto_deploy(): `skip` only covers the current pass. If Dan's button Reject or Deploy fails, for example because the lock is held or a container doesn't come up, the build can still be auto-deployed in the next minute. That is a rare case and outside what the plan asks for. A possible follow-up is to record the failed button action in auto-deploy.json against the tip sha.
2. A corrupt auto-deploy.json is treated as empty, as the plan says. The runner doesn't crash, but a sha that already failed can be tried one more time. That is acceptable.
3. `Risk: 1, low` and `Risk: 1.5` are not eligible, while `1`, ` 1`, `1/5` and `1 (low)` are. This leans conservative, which is fine.
4. The branch cleanup reads the same for-each-ref list as reviewed_slugs(), so it runs git one extra time. This is only a nit.

## Declined to judge
- Behaviour when the cron job's REPO is the main checkout rather than the worktree: deployment takes care of that, and this change doesn't affect it.
