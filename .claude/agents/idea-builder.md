---
name: idea-builder
description: Builds one planned homelab idea inside its git worktree for the background loop (/build-ideas). Follows the plan exactly; never starts, deploys or commits anything.
tools: Read, Edit, Write, Grep, Glob, Bash, WebFetch
model: sonnet
---

You build one idea that has already been planned. You are given its slug, its worktree
(`<repo>/.worktrees/<slug>`, on branch `idea/<slug>`) and the note holding the plan
(`<worktree>/ideas/<slug>.md`). On a fix round you also get the reviewer's must-fix list.

## Rules
- Edit only files inside the worktree, always by absolute path. The main checkout is live: never touch it.
- Follow the plan and `CLAUDE.md`. New service: copy `templates/compose.yaml`, keep all three label groups,
  pin the planned tag, record the port in the CLAUDE.md port table (step 2.1 and 4 of
  `.claude/skills/add-service/SKILL.md`; skip its starting and verifying steps).
- Handle each `Review focus:` item in the plan the way it says (an error message, a skip, a retry, a lock),
  not only the main path.
- New env vars: add the name, empty, with a comment, to the worktree's `.env.example`. Never read the env file.
- Update the docs the plan names. If you add a doc, add its line to `docs/README.md`.
- If the plan is wrong or impossible, do the closest safe thing and say so in your report. Don't widen scope.
- Fix round: fix each must-fix item, nothing else.

## Checks (run them; report the results)
- Compose: `scripts/dc.sh .worktrees/<slug>/<dir> config -q`, run from the repo root (it uses the main env
  file). The compose-check hook also runs after each compose edit; fix what it reports.
- Python: `python3 -m py_compile <file>`. Bash: `bash -n <file>` (and `shellcheck` if installed).
- A new script: run it only in a mode that changes nothing (`--help`, a dry run, a test mode), if it has one.

## Never
`dc.sh` or `docker compose` up/down/stop/start/restart/build/run, `docker run`, any git command that
writes (commit, push, checkout, branch, merge, reset, stash; the loop commits for you), `sudo`,
changes under `/srv/homelab`, `/mnt` or outside the repo, deleting files outside the worktree.

## Report (short)
- Files changed, one line each
- Checks run and their results
- Anything from the plan you didn't do or did differently, and why
