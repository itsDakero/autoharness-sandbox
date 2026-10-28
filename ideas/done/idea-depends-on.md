# Chained ideas: a note in ideas/waiting/ joins the queue once the idea it depends on is deployed

Value: 4   (multi-stage projects run on their own: Dan deploys stage N, the loop builds stage N+1)
Effort: 2  (queue filter + one move in idea.sh, an unblock post, a waiting list on the Ideas card)
Risk: 1    (changes only which notes the loop picks and when; no services, no secrets)
Score: 16
Source: Dan 2026-10-25 (session with Claude: FPL model built in stages, see `reports/FPL points prediction model.md`)

## Problem
Big projects are split into stages, but each stage has to be queued by hand after the one before it is
deployed. If all stages are queued at once, the loop builds them back to back, before the earlier stages are
reviewed and merged, so later plans are made against code that isn't on main yet. The existing
`Depends on:` header line only works if the planner notices it and parks the note.

## Proposal
- **New folder `ideas/waiting/`**: notes that must wait for another idea. Each has a header line
  `Depends on: <slug>` (first word after the colon is the slug; the rest of the line is free text, the same
  form older notes already use).
- **"Deployed" means** `ideas/done/<slug>.md` exists on main. `idea.sh commit` moves the note to
  `ideas/done/` on the `idea/<slug>` branch, so it only reaches main when deploy merges it (by
  `scripts/deploy-idea.sh` or the dashboard Deploy button / auto-deploy in `scripts/idea-actions.py`).
  Check it with git against main, not the working tree.
- **`scripts/idea.sh queue`**: also lists `ideas/waiting/*.md` whose dependency is deployed, sorted by
  the same date rule as now. A note in `ideas/*.md` with a `Depends on:` slug that isn't deployed yet is
  skipped too, so the line means the same thing wherever the note sits.
- **`scripts/idea.sh start <slug>`**: a slug that is only in `ideas/waiting/` is moved to `ideas/` first
  (git mv when tracked, plain mv + git add when not), then everything goes on as today. It refuses
  a note whose dependency isn't deployed (`/build-ideas <slug>` can't skip the chain by accident).
- **`scripts/idea.sh unblocked <slug>`** (new): prints the waiting notes that depend on `<slug>`. Both
  deploy paths call it after a successful merge and post one Discord line each via `scripts/discord.sh`:
  "Unblocked: <title>. The loop picks it up on its next pass".
- **`deploy-idea.sh reject <slug>`** (and the dashboard Reject): if waiting notes depend on the rejected
  idea, print them and post a Discord line, so a chain never waits forever without Dan knowing. Leave the
  waiting notes in place; Dan decides.
- **Dashboard Ideas card** (`core/dashboard/app/ideas.py` + its page): a "Waiting" list with each note's
  title and "waits on <slug>" (or "ready" once unblocked and not yet started). The slug collision check
  includes `waiting/`. The `/ideas` mount already covers the folder.
- **Docs**: `docs/m5-pipeline.md` (how chains work, how to add one), and the `ideas/` line in `CLAUDE.md`.

Already waiting in `ideas/waiting/` when this ships: FPL stages 2-5 (`fpl-dashboard`, `fpl-team-model`,
`fpl-player-model`, `fpl-backtest`), chained to `fpl-collector`. They are untracked notes, like new
dashboard ideas. Don't change them; they are the first real test.

Out of scope: more than one dependency per note, and any change under `.claude/` (the skill already
asks `scripts/idea.sh queue` for its work, so it needs no change).

Review focus ideas: a waiting note whose dependency is built but not merged must stay out of the queue;
a typo'd dependency slug must stay waiting (and show on the card), not crash `queue`; the loop's
`queue` output must not change for notes without `Depends on:`; the unblock post must fire from both
deploy paths, exactly once per note.

## Plan
Goal: Notes in `ideas/waiting/` with `Depends on: <slug>` join the loop's queue only once `ideas/done/<slug>.md` is on main. Deploy posts an "Unblocked" line, reject warns when other notes wait on the idea, and the dashboard lists the waiting notes.
Kind: change to the idea pipeline (idea.sh, deploy-idea.sh, dashboard Ideas card)
Files:
- scripts/idea.sh: add the helpers `dep_of`, `deployed`, `unblocked`, `waiting_taken`; change `queue`, `note_of` and `start`; update the usage header
- scripts/deploy-idea.sh: post Unblocked lines at the end of post_merge; warn on reject when notes depend on the idea
- core/dashboard/app/ideas.py: queue() returns a `waiting` list and an `on` field per queued note; `_taken` includes "waiting"
- core/dashboard/app/static/index.html: renderIdeas shows a "Waiting" list, plus a "waits on" badge on queued notes
- docs/m5-pipeline.md: new subsection "Chained ideas (ideas/waiting/)" under Stage C
- CLAUDE.md: the `ideas/` layout line and the `idea.sh` scripts entry

Details:
- Dependency line: look only at the header, i.e. the lines before the first `## `. Use the first line matching
  `^Depends on:` (case-insensitive). The slug is the first word after the colon and must match
  `^[a-z0-9][a-z0-9-]*`. A trailing `,`, `.` or `)` is stripped. The rest of the line is ignored. No line, or no
  valid first word, means no dependency. Do the same in bash (`dep_of <file>`, prints the slug or nothing) and in
  Python (`_depends_on(text)`).
- Deployed means `git cat-file -e "main:ideas/done/<dep>.md"`, never the working tree, so a branch that is built
  but not merged does not count. In the dashboard, deployed means `(IDEAS_DIR/"done"/f"{dep}.md").exists()`. That
  is correct there because the /ideas mount is the main checkout, and `idea.sh`'s on_main makes sure of it.
- `queue`:
  - ideas/*.md: unchanged, except a note whose dep is set and not deployed is skipped.
  - Then ideas/waiting/*.md, with the same reviewed-branch skip and the same date rule (git add date, else
    mtime). A waiting note is listed only if it has a dep and the dep is deployed. A waiting note with no
    `Depends on:` line never goes into the queue.
  - Skip a waiting note whose slug already exists as ideas/<s>.md or in done/, parked/, rejected/ or terminal/.
    That is a collision: it stays put and the card shows it.
  - Merge both sets into the one existing `sort -n` pipe. Nothing goes to stdout except slugs.
  - `dep_of` errors (an unreadable file) never abort the loop: use `|| true`.
- `note_of`: after ideas/<s>.md and ideas/terminal/<s>.md, also check ideas/waiting/<s>.md.
- `start <slug>`:
  - After lock and on_main, if the note has a dep that is not deployed, die with
    "<slug> waits on <dep>, which isn't deployed yet".
  - If the note is ideas/waiting/<s>.md, die if the slug collides as above. Otherwise move it to ideas/<s>.md:
    `git mv` if tracked, else plain `mv`.
  - Set note=ideas/<s>.md and keep the old path. The existing "ideas: queue" commit must include the old path in
    its pathspec when the note was tracked, otherwise the deletion is left staged. The existing
    add/commit/push/worktree steps then run as today.
- `unblocked <slug>` (new; slug_ok; read-only, no lock): print `<slug>\t<title>` for every ideas/waiting/*.md and
  ideas/*.md whose dep equals `<slug>`, sorted by name. Prints nothing and exits 0 if there are none.
- deploy-idea.sh post_merge: after the "Deployed:" post, call
  `"$REPO/scripts/idea.sh" unblocked "$s" || true`. For each line, post `discord.sh "Unblocked: <title>. The loop
  picks it up on its next pass"` and echo the same line. This is the only place it fires. The terminal deploy and
  idea-actions.py (Deploy button and auto-deploy) both reach it through `deploy-idea.sh --yes`, so idea-actions.py
  is not changed. There is one post per note per deploy.
- deploy-idea.sh reject: after the rejection is committed and pushed, run `idea.sh unblocked "$s"`. If it prints
  anything:
  - echo "Waiting on $s (left in place): <titles>";
  - post one Discord line: "Rejected <name>: <n> waiting idea(s) depend on it (<titles, comma-joined, cut to 300
    chars>). Edit or remove them in ideas/waiting/".
  - Do not move any notes.
- ideas.py queue():
  - Each item gets `"on": dep` when its dep is set and not deployed, else "".
  - New `"waiting"` key: a list of {file, title, on, state} sorted by title, where state is one of:
    - `ready`: deployed dep;
    - `waiting`: the dep exists as a note anywhere under IDEAS_DIR (ideas/, waiting/, terminal/, parked/), or an
      unmerged build is pending (it can't see branches);
    - `rejected`: rejected/<dep>.md exists;
    - `unknown`: no note with that slug anywhere;
    - `no-dep`: no Depends on line.
  - If waiting/ is missing, return []. Read errors fall back to state "no-dep" with the file stem as the title.
- index.html renderIdeas:
  - After the Parked block, if `d.waiting.length`, add an h4 "Waiting on another idea" and an `ul.ideas`. Each
    `li` holds the title (tooltip `ideas/waiting/<file>`) and a status:
    - ready: span "s" "ready";
    - waiting: span "s" "waits on <on>";
    - rejected: badge warn "waits on <on> (rejected)";
    - unknown: badge warn "waits on <on>: no such idea";
    - no-dep: badge warn "no Depends on: line".
  - Queued items with `i.on` get a span "s" "waits on <on>" instead of the age.
  - Use `el()` and textContent only, never innerHTML.

New env vars: None
Checks the builder must run:
- `bash -n scripts/idea.sh scripts/deploy-idea.sh`, plus `shellcheck` on both if it is installed
- `python3 -m py_compile core/dashboard/app/ideas.py`
- `scripts/dc.sh core/dashboard config -q`
- Scratch test in the session scratchpad. Run `git init -b main` there, copy scripts/idea.sh into `scripts/`, put
  a `discord.sh` stub that does `exit 0` next to it, then commit notes:
  - ideas/a.md: no dep
  - ideas/b.md: `Depends on: a`
  - ideas/waiting/c.md: `Depends on: a (free text)`; leave it untracked
  - ideas/waiting/d.md: `Depends on: typo-slug`
  - ideas/waiting/e.md: no Depends line

  Assert, in order:
  1. `queue` prints exactly `a`.
  2. On a branch `idea/a`, commit ideas/done/a.md. `queue` still prints only `a`: the build is not merged.
  3. Merge into main. `queue` now prints `b` and `c`, never `d` or `e`, with no error output.
  4. `unblocked a` prints b and c.
  5. `start c` (with a bare remote set, or with the push failures accepted) leaves ideas/c.md committed and
     ideas/waiting/c.md gone, with nothing left staged (`git status --porcelain` is clean apart from the untracked
     `d`/`e`).
  6. `start d` fails with the "waits on" message.
- A Python one-off that calls `ideas.queue()` with IDEAS_DIR pointed at the scratch ideas dir, checking the states
  ready, unknown and no-dep.

Review focus:
- A dep that is built on idea/<dep> but not merged -> the note stays out of `queue` and `start` refuses it, because
  the check is against `main:`, not the worktree.
- A typo'd or nonexistent dep slug, or a waiting note with no Depends line -> it stays waiting. `queue` prints
  nothing for it and does not exit non-zero. The card shows a warn badge.
- Notes without `Depends on:` -> `queue` output is byte-identical to before, in the same order.
- A deploy through the terminal, the Deploy button or auto-deploy -> exactly one Unblocked post per dependent note.
  If discord.sh or `idea.sh unblocked` fails, the deploy still succeeds.
- `start` on an untracked waiting note -> the note is committed at ideas/<s>.md in a single "ideas: queue" commit,
  with no stray staged rename or deletion that would block the next deploy's "uncommitted changes" check.
Docs:
- docs/m5-pipeline.md: a "Chained ideas" subsection covering:
  - the waiting/ folder and the `Depends on: <slug> <free text>` form, one dependency per note;
  - "deployed" meaning ideas/done/<slug>.md is on main;
  - the Unblocked and reject posts;
  - how to add a chain;
  - `idea.sh unblocked` under Commands.
- CLAUDE.md: add `ideas/waiting/` (notes with `Depends on: <slug>`, queued once that idea is deployed) to the
  `ideas/` layout line, and `unblocked` to the idea.sh entry.

## Manual steps
None. The four FPL notes already in ideas/waiting/ (untracked) are the first real test: once fpl-collector is
deployed, fpl-dashboard should be announced as Unblocked and picked up. The builder must not touch them. The
worktree doesn't contain them anyway.

## Review notes
1. scripts/idea.sh:108 (start): the reviewed-branch `die` runs after the waiting note has been moved (`git mv` or `mv`), so in that case the move is left in the working tree, staged if the note was tracked. `queue` skips reviewed branches, so this only happens on a manual `start`. Doing the move after the has_branch block would avoid it.
2. scripts/idea.sh start: a waiting note with no `Depends on:` line is not refused. I ran `start e` in the scratch repo and it moved and started the note. `queue` never lists such a note, so only a manual `/build-ideas <slug>` reaches it. The plan only asked `start` to refuse an undeployed dependency, so this follows the plan.
3. core/dashboard/app/ideas.py waiting(): a waiting note whose slug collides with an existing note shows "ready" on the card, but `queue` never picks it up. The plan says "the card shows it" for collisions, but its own list of states has no collision state. A "collides" warn badge would make this visible.
4. `idea.sh start` exits 1 on success for non-terminal notes, because its last line `[[ $note == ideas/terminal/* ]] && echo ...` returns 1. This was already on main and this change doesn't touch it. Worth fixing separately.
5. A note in `ideas/` with a free-text first word after `Depends on:` (for example "Depends on: the ...") is held back silently until an idea called "the" is deployed. The card shows "waits on the" in place of the age. This follows the plan; the current notes all use real slugs (hermes-discord-voice and morning-brief in parked/ depend on ideas already in done/).

## Declined to judge
- More than one dependency per note: out of scope per the plan.
- Changes under .claude/ (the build-ideas skill): out of scope. The skill reads the note at `<wt>/ideas/<slug>.md` after `start`, and that path is correct because `start` moves the note first.
- The dashboard counting "deployed" from the working tree of the /ideas mount: this is what the plan decided (the mount is the main checkout).
