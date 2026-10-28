# Reject button for parked ideas

The Parked tab has Answer and Requeue but no Reject, and `scripts/deploy-idea.sh reject <slug>` only
handles a reviewed `idea/<slug>` branch or a plan in `ideas/terminal/`. So a parked idea Dan doesn't want
can only leave by hand (discord-hermes-agent, 2026-10-16: moved to `ideas/rejected/` manually).

- `deploy-idea.sh reject <slug>`: also accept `ideas/parked/<slug>.md` (no branch, no build to drop). File it
  under `ideas/rejected/` the same way (date + reason appended, `ideas: reject <slug>` commit, push,
  Discord "Rejected: ..."). Keep the existing branch/terminal paths as they are.
- Dashboard Parked tab: a Reject button next to Answer/Requeue, with a reason field (required, like the
  Deploy tab's Reject). It queues the existing `reject` action for `scripts/idea-actions.py`, so no new
  action type; check idea-actions.py doesn't refuse a parked slug.
- Update the usage comment at the top of deploy-idea.sh, idea-actions.py's docstring and docs/m5-pipeline.md.

_Added by Claude in a terminal, 2026-10-16._

## Plan
Goal: Add a Reject button to the Parked tab, and make `deploy-idea.sh reject <slug>` accept a parked note (no branch, no build), so Dan can file it under `ideas/rejected/` with a reason.
Kind: change to scripts/deploy-idea.sh, scripts/idea-actions.py, the dashboard (core/dashboard)
Files:
- scripts/deploy-idea.sh: in the `reject` branch, the lookup order becomes: branch `idea/<slug>` (must be reviewed, unchanged), then `ideas/terminal/<slug>.md` (unchanged), then `ideas/parked/<slug>.md` (new; set `hand=1` so `drop_build` is skipped). The die message becomes "no branch idea/$s, no ideas/terminal/$s.md and no ideas/parked/$s.md". After `lock`, where `note` is picked, add `[[ -f ideas/parked/$s.md ]] && note="ideas/parked/$s.md"`, but only when there is no branch, so the branch's done note still wins. The existing copy, append, `git rm`, commit, push and Discord steps are reused as they are. The final echo says "the build is gone" only when a build was dropped; otherwise it says "Rejected $s: the note is in $rej." Add a line about parked notes to the usage comment at the top.
- scripts/idea-actions.py: update the docstring's `reject` line to say it also files a parked note (ideas/parked/, from the Parked tab). No code change. `run()` already accepts "reject" for any valid slug, and `reject()` pipes the reason on stdin.
- core/dashboard/app/ideas.py:
  - `request()`: for action "reject", accept the slug when `IDEAS_DIR/"parked"/f"{slug}.md"` is a file; otherwise keep the current check against `deploys()["ready"]`. Keep the reason rules as they are (one line, required, at most REASON_MAX=300).
  - `parked()`: the `actions` filter becomes `("answer", "requeue", "reject")`, so the Parked card shows the queued, running or failed state of its reject.
  - Update the `request()` docstring.
- core/dashboard/app/static/index.html: in `renderParked`, add `btn("Reject", "btn ghost danger")` to `acts` after Requeue and Save. Set it to `disabled = busy`, with the title "Don't build it: files the idea under ideas/rejected/ with your reason". On click it behaves like the Deploy tab's Reject: a `prompt()` for the reason; cancel does nothing; an empty reason sets `d.errors[slug] = "Not rejected: give a short reason."` and redraws; otherwise it calls `send(d, it.slug, { action: "reject", text: why.trim().slice(0, 300) }, [requeue, save, no])`. The answers textarea is not used for the reason.
- docs/m5-pipeline.md: in the Parked tab bullet (around line 115-117), add **Reject** (reason prompt, files the note under ideas/rejected/, no build to drop). Next to the reject command (around line 105), note that it also takes a parked or terminal note. Update the "Reject" bullet (around line 130) to match.
New service: None
New env vars: None
Checks the builder must run:
- bash -n scripts/deploy-idea.sh
- python3 -m py_compile scripts/idea-actions.py core/dashboard/app/ideas.py core/dashboard/app/main.py
- scripts/dc.sh <worktree>/core/dashboard config -q
- Extract the inline <script> of index.html to the scratchpad and run `node --check` on it, if node is present.
- grep that renderParked's Reject sends action "reject" and that parked()'s filter includes "reject".
Review focus:
- Slug has both a parked note and an `idea/<slug>` branch -> the branch path wins as today (must be reviewed; the build's done note is copied); the parked path is used only when there is no branch.
- Note requeued or removed between the dashboard request and the runner -> deploy-idea dies with "no note"/"no branch…" and leaves main clean; the card shows "Reject failed: …".
- `ideas/rejected/<slug>.md` already exists -> refused with the existing message, and the parked note is untouched.
- Commit failure -> the existing rollback restores `ideas/parked/<slug>.md` and removes the half-written rejected file.
- Empty or whitespace-only reason, or one over 300 characters -> refused in the browser and in ideas.py.request(); nothing is queued.
Docs: docs/m5-pipeline.md only (Parked tab bullet, reject command, Reject bullet). The CLAUDE.md scripts line is unchanged.

## Manual steps
None. The deploy rebuilds core/dashboard. idea-actions.py runs from the repo via cron.

## Review notes
1. My throwaway-repo test of `deploy-idea.sh reject` was refused by the permission system. I checked these paths by reading the code instead: the happy path, an existing rejected file, a missing note, commit-failure rollback, and a branch alongside a parked note. They all match the review focus:
   - Branch present: the branch check runs first and still needs the reviewed trailer. The parked `note=` override only applies when there's no branch, so the done note from `done_note` still wins.
   - Note gone before the runner picks it up: it dies with "no branch idea/$s, no ideas/terminal/$s.md and no ideas/parked/$s.md" before `lock`, so main isn't touched. idea-actions.py reports that last line as "Reject failed: …", using `DONE.reject` in `actionStatus`.
   - `ideas/rejected/<slug>.md` already exists: `die` runs before anything is written, and the parked note isn't touched.
   - Commit fails: the existing rollback (`git reset` + `git checkout -- "$note"` + `rm "$rej"`) restores `ideas/parked/<slug>.md`, which is tracked.
2. A slug with both a terminal note and a parked note but no branch files the parked note and leaves the terminal one in place. This shouldn't happen in practice.
3. `/home/dan/homelab/.worktrees/parked-reject/docs/m5-pipeline.md:134`: the added sentence makes that bullet line much longer than its neighbours. Cosmetic only.
4. A browser reason over 300 characters is cut to 300 by `.slice(0, 300)` rather than refused. That matches the Deploy tab's Reject, and ideas.py's REASON_MAX=300 check rejects anything longer that skips the page.
5. The worktree changes are uncommitted (the builder's diff is in the working tree, with no commits on `idea/parked-reject` yet). `scripts/idea.sh diff` shows them correctly.

## Declined to judge
- The page JS syntax: no node on the host. I checked by reading instead. The new block in `renderParked` uses only identifiers already in scope (`busy`, `requeue`, `save`, `send`, `drawDeck`, `d.errors`).
- What the Discord message says for a parked reject: it reuses the existing "Rejected: <title> (<reason>)" line, as the plan says.
