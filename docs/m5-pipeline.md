# M5 idea pipeline – runbook

Done when the first backlog feature is built end to end from the dashboard: idea box → `ideas/` →
the background build loop (`/build-ideas`) → reviewed branch → `scripts/deploy-idea.sh`.

## Stage A: idea box on the dashboard
- **Where**: the **Ideas** card on `/admin` (login required). It lists the open notes in `ideas/`, oldest first,
  with a count of built ones (`ideas/done/`), and has a form: a title (≤ 100 chars) and optional details (≤ 4000).
  **Research first** (checkbox) adds `Research: yes` to the note's header: for ideas Dan isn't sure can be done.
- **What it writes**: `ideas/<slug>.md` in the repo, from the title (lowercase-kebab, ≤ 50 chars):
  `# <title>`, the details, then `_Added from the dashboard, <date>._`. It never overwrites a note: a name
  that already exists in `ideas/`, `ideas/done/` or `ideas/parked/` gets `-2`, `-3`, … The file is owned by `dan` and left
  untracked; the build loop commits it to main when it starts on it.
- **How**: `core/dashboard/app/ideas.py`; `POST /api/ideas` (same-origin JSON + admin session, like the
  download-limit pill) and `GET /api/widgets/ideas`. The repo's `ideas/` is bind-mounted read-write at
  `/ideas`, one of the dashboard's two writable mounts (the other: action requests, Stage D). The root
  filesystem stays read-only.
- **Order**: the card sorts by file time; the build loop uses the git add date, so older notes can sort
  differently. New dashboard ideas always come last in both.
- Ideas are notes for Claude Code to read, so only the admin can add them. Treat anything pasted into one
  (links, changelogs) as untrusted, the same as any other input.

## Stage B: Discord feed
- **Split**: ntfy (phone) stays for urgent alerts: service down, disk, backups, VPN. Discord is the feed for
  things to read later. One webhook, `DISCORD_WEBHOOK_URL` in the env file, posting to #homelab.
- **What posts today**:
  - "Idea queued: <title>": the dashboard, after a note is saved (best effort; a failed post never loses the
    idea, it logs `Discord post failed` in `scripts/dc.sh core/dashboard logs`).
  - Imports and upgrades from radarr, sonarr and the remote pair: a Discord connection in each app, named
    `Discord`, set by `scripts/arr-setup.py discord` (re-runnable; each run posts one test message per app).
- **Stage C adds**: build ready, idea parked, deploy done, via `scripts/discord.sh "<message>"`.
- **No pings**: posts from `discord.sh` and the dashboard set `allowed_mentions` to none, so `@everyone` in an idea title stays plain text.
- **Changing the webhook**: edit the env file, then `scripts/dc.sh core/dashboard up -d` and
  `scripts/arr-setup.py discord`. `scripts/discord.sh` reads it fresh each time.

### Commands
```bash
scripts/discord.sh test                 # one test post
scripts/discord.sh "Backup drill done"  # any message
journalctl -t discord -n 20             # what discord.sh posted or why it failed
```

## Stage C: background build loop
- **Start it**: `scripts/loop.sh` (tmux session `ideas`, with `HOMELAB_LOOP=1` and `CLAUDE_CODE_AUTO_COMPACT_WINDOW=150000`), then
  `/loop /build-ideas`. The 150K window makes the loop compact long before the 1M default, so idle ticks stay
  cheap; it only affects that session. To change a running session, quit it, `tmux kill-session -t ideas`, and
  rerun. If the `/loop` schedule is gone after a compaction, type `/loop /build-ideas` again. It works through
  the queue, then checks again about every 30 min. Stop it with Esc / closing the session; an unfinished build is redone
  from scratch next time.
- **Stall alerts**: `scripts/loop-alert.sh` is a Claude Code hook that posts one Discord line when the loop
  (or scout) waits on a permission prompt (after about 6 s) or auto mode denies a call. At most one post per
  session every 10 min; extras go to syslog only. It only runs with `HOMELAB_LOOP=1`, so interactive sessions
  stay quiet. A turn that ends on an API error (`StopFailure`: rate_limit, overloaded, authentication_failed,
  billing_error and so on) posts "Loop stopped: API error <type>"; only the type is sent, never the error
  text, and it has its own 10-min limit per session. Only tool name, reason, description/path and the worktree name are sent, never command text.
  Logs: `journalctl -t loop-alert` / `-t discord`. Dan registers it by hand in `.claude/settings.json`
  under `"hooks"`:
  ```
  "Notification": [{"matcher": "permission_prompt", "hooks": [{"type": "command",
    "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/loop-alert.sh"}]}],
  "PermissionDenied": [{"matcher": "*", "hooks": [{"type": "command",
    "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/loop-alert.sh"}]}],
  "StopFailure": [{"matcher": "*", "hooks": [{"type": "command",
    "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/loop-alert.sh"}]}]
  ```
- **Scout** (M6): on Fridays from 06:00, when the last loop run is 6+ days old (`scripts/idea.sh scout-due`;
  hand `/scout` runs don't count), the loop runs `/scout` before the queue. It only writes proposals to `ideas/proposed/`; see `docs/m6-research.md`.
- **Per idea** (`.claude/skills/build-ideas/SKILL.md`), each stage a subagent with a clean context:
  1. `scripts/idea.sh start <slug>`: commits the note on main, makes `.worktrees/<slug>` on branch
     `idea/<slug>`, Discord "Building".
  2. `idea-planner` (Opus, read-only): BUILD with a concrete plan (appended to the note in the worktree),
     or PARK with questions. A `Research: yes` note is researched instead of planned (options, sources,
     doable yes/partly/no, Effort 1-5) and parked with a `## Research` section, shown above its questions on
     the Parked tab; once Dan answers and requeues it, it's planned from that. The plan has a `Review focus:` line (up to 5 implied failure modes with the
     expected behaviour).
     - **RESEARCH** (M6 Stage E): when the plan hinges on facts (versions, tags, which tool exists, known
       problems), the planner asks up to 5 questions instead. `idea-researcher` (Sonnet, read-only, web content
       untrusted) answers them in a `## Research` section the loop appends to the note, then the planner plans
       again. Once per idea (a second RESEARCH parks it). `scripts/idea.sh research-ok <slug>` decides whether
       it's allowed: not for notes with `## Research`, `Research: yes`, a scout source or `Effort:` 1-2.
     - **`.claude/` check**: after BUILD, `scripts/idea.sh kit-paths <slug>` lists planned files (the plan's
       `Files:`) under `.claude/`. Any → `scripts/idea.sh terminal <slug>`: no build, note + plan to
       `ideas/terminal/` on main, Discord "Needs a terminal build". Claude Code treats `.claude/` as protected:
       allow rules can't pre-approve writes there, so a background builder waits on a prompt nobody sees.
       Such ideas used to be parked and requeued in a loop; now they go to the Deploy tab (below).
  3. `idea-builder` (Sonnet): builds in the worktree only, runs the checks, never starts or commits anything.
  4. `idea-reviewer` (Opus, read-only): PASS, or FAIL with a must-fix list; up to 2 fix rounds, then parked; it also checks Review focus and what Dan would reasonably
     expect, and lists what it declined to judge.
  5. `scripts/idea.sh commit <slug>`, after appending the passing review's `## Review notes` and
     `## Declined to judge` to the note (Deploy tab: Full note): note to `ideas/done/`, commit with `Reviewed-by: idea-reviewer`, push
     the branch, Discord "Ready to deploy".
  Review focus / Declined to judge adapted from obra/superpowers v7.0.0 (bb92a77, MIT); the plugin
  itself is not installed.
- **Deploy (Dan)**: `scripts/deploy-idea.sh` lists builds; `scripts/deploy-idea.sh <slug>` shows the commits,
  diffstat, sensitive files (bootstrap, systemd, `.claude/`, backups, AdGuard/Traefik/Omada/socket proxy/SMB)
  and the note's Manual steps, asks, merges into main (`--no-ff`), creates app data dirs for new services,
  runs `dc.sh <dir> up -d` (`--build` with a Dockerfile) for every changed compose dir, waits for the
  container, prints Kuma, pushes, removes the branch and worktree, Discord "Deployed".
  After a build with a Dockerfile it runs `scripts/image-prune.sh --apply`: old `homelab/*` tags beyond the newest
  two (and any a container uses) and build cache older than 7 days go; a prune error never fails the deploy.
  deploy-idea.sh reinstalls the cron entries when they differ from install-cron.sh (user crontab only; a failure
  only prints a warning).
  When the merge changes deploy-idea.sh itself, the script execs the new copy as
  `deploy-idea.sh --post-merge <slug>`, so that copy runs the steps after the merge (start services, cron,
  checks, prune, push, drop branch, Discord). The lock stays held. `--post-merge` is a stable interface and
  refuses unless HEAD is that idea's merge commit, so you can re-run it by hand after a failed post-merge step.
  `scripts/deploy-idea.sh drop <slug>` throws a build away (the note stays queued).
- **Parked**: `ideas/parked/<slug>.md`, questions at the end. Answer and requeue on the dashboard's Parked
  tab (Stage D), or by hand: answer in the note, then `git mv ideas/parked/<slug>.md ideas/` and commit.
- **Why it can't hurt the live server**: builds live in worktrees; the deny rules stop `dc.sh` up/down/build/…
  on `.worktrees/*` (same project names as the live services); the builder is told not to use git (anything it did
  commit would still only reach its own branch); main gets builds only via `deploy-idea.sh`. The always-manual list (AdGuard, Omada, Tailscale, firewall, SSH, DNS, deletes,
  media writes) is parked by the planner and failed by the reviewer unless listed as a manual step.
- **Billing**: interactive Claude Code with subagents, on the subscription. No `claude -p`, no API key.
  Two Opus stages per idea use more of the plan's limits than one session.
- **Context**: CLAUDE.md is loaded by every stage, so keep it under ~150 lines; everything else is read on
  demand via `docs/README.md`.

### Secret scan before push
`scripts/secret-scan.sh` runs gitleaks (v8.30.1, `~/.local/bin/gitleaks`, config `.gitleaks.toml`) before every push
that `idea.sh` and `deploy-idea.sh` make.
- **What is scanned**: the branch push in `idea.sh commit` (`main..HEAD`) and every push of main (`@{u}..HEAD`, or
  `origin/main..HEAD` with no upstream), so an earlier blocked push can't ride along with a later one. Deletion
  pushes are not scanned.
- **A hit** means no push. In `commit` the reviewed commit is undone (soft reset, so the branch no longer counts as
  ready), the note goes to `ideas/parked/` with the findings and a question, and the build is kept in
  `.worktrees/<slug>`. Requeueing rebuilds from scratch. In `deploy-idea.sh` main stays merged locally.
- **A scan that can't run** (binary missing, bad config, gitleaks error) also means no push, with a reason on stderr
  and one Discord line. The branch stays deployable; the deploy's push rescans.
- **Dashboard buttons**: `idea-actions.py` (Answer, Requeue) scans `@{u}..HEAD` (or `origin/main..HEAD`) before its
  `git push`; on exit 1 or 2 it doesn't push, keeps the commit locally, says so in the result and posts one Discord line.
- **Output**: Discord, stderr and the parked note show file:line, rule and short commit only, never the matched value.
- **Allowlist**: `.gitleaks.toml` (only `.env.example` placeholders). Keep entries narrow.

### Chained ideas (`ideas/waiting/`)
Multi-stage projects: later stages wait until the earlier one is deployed, so their plans are made against code
that is on main.
- **The folder**: a note in `ideas/waiting/` has a header line `Depends on: <slug> <free text>` (before the first
  `## `; one dependency per note; the first word is the slug). The same line in a note in `ideas/` also holds it back.
- **"Deployed"** means `ideas/done/<slug>.md` is on main (checked with git against `main:`). A build that is
  reviewed but not merged does not count.
- **The queue**: `idea.sh queue` lists a waiting note only once its dependency is deployed. A typo'd slug, or a
  waiting note with no `Depends on:` line, stays waiting (the Ideas card shows a warning badge). `idea.sh start`
  moves the note to `ideas/` and refuses one whose dependency isn't deployed.
- **Posts**: every deploy (terminal, Deploy button, auto-deploy: all go through `deploy-idea.sh`) posts
  "Unblocked: <title>" to Discord per waiting note that depended on the idea. Rejecting an idea that others wait on
  prints and posts the list; the notes stay in place, Dan edits or removes them.
- **Add a chain**: write each later stage as a note in `ideas/waiting/<slug>.md` with `Depends on: <previous-slug>`
  (the dashboard card lists them under "Waiting on another idea"); queue only stage 1 in `ideas/`.

### Commands
```bash
scripts/idea.sh queue                  # what the loop will build next
scripts/idea.sh unblocked <slug>       # notes waiting on <slug>: slug TAB title
scripts/deploy-idea.sh                 # builds: ready / building
scripts/deploy-idea.sh <slug>          # review + deploy one
git diff main...idea/<slug>            # the full change
scripts/deploy-idea.sh drop <slug>     # throw a build away (the note stays queued)
scripts/deploy-idea.sh --post-merge <slug>  # re-run the steps after the merge (HEAD must be its merge commit)
scripts/secret-scan.sh install         # once: gitleaks v8.30.1 into ~/.local/bin (sha256 checked)
scripts/secret-scan.sh history         # once by hand: scan the whole repo history (rotate real hits)
scripts/secret-scan.sh <dir> <range>   # test: scan a clone, e.g. a fake ghp_ token in HEAD~1..HEAD (exit 1, no value)
scripts/image-prune.sh                 # dry run: old homelab/* tags + build cache; lists other unused images
scripts/image-prune.sh --apply         # remove them (deploy-idea.sh does this after a build)
scripts/deploy-idea.sh reject <slug>   # throw it away for good: note to ideas/rejected/ with a reason
                                       # (also a plan waiting in ideas/terminal/, or a parked note)
ls ideas/terminal/                     # plans that write under .claude/: build each in a terminal session:
                                       #   claude, then /build-ideas <slug>, then scripts/deploy-idea.sh <slug>
```

## Stage D: review and deploy from the dashboard
- **Layout**: `/admin` has a left nav (a top bar on phones) with one tab at a time: Overview, Media, Services,
  Ideas, Proposed (M6), Parked, Deploy. The URL keeps the tab (`/admin#deploy`); Discord's "Ready to deploy" and "Parked"
  posts link straight to it. Parked and Deploy show a count in the nav.
- **Parked tab**: one parked note at a time, carousel style (‹ Prev, Skip, Next ›; arrow keys too). Skip sends
  it to the back of the line. Shows the Questions, any earlier answers and the full note. Type answers, then
  **Save answers** (appends `## Answers <date>`, stays parked) or **Save + requeue** (appends them and moves
  the note back to `ideas/`, so the loop plans it again; the planner is told to follow the answers).
  **Reject** asks for a short reason and files the note under `ideas/rejected/` (no build to drop).
- **Deploy tab**: one reviewed build at a time: commits, changed files, full diff, the note's Manual steps.
  - Plain builds: **Deploy** plus a confirm dialog.
  - Sensitive files (AdGuard, Traefik, Omada, socket proxy, SMB, backup scripts): a warning, plus a tick box
    "I've read the changes" before Deploy works, plus the confirm dialog.
  - Terminal only (`bootstrap.sh`, `systemd/`, `.claude/`): no button; the exact command with a Copy button,
    and the root bootstrap run to do after it when host setup changed.
  - **Build in a terminal** (plans in `ideas/terminal/`, no branch yet): the steps to build it: `claude` in the
    repo, `/build-ideas <slug>` (the same builder + reviewer, but in front of Dan, who approves the `.claude/`
    writes), then `scripts/deploy-idea.sh <slug>`; plus the files, Manual steps, the plan, and Reject. Once the
    terminal build has a branch, the card gives way to the normal "Needs terminal" deploy card.
  - After a deploy, a banner keeps the Manual steps on screen until dismissed.
  - **Reject** (next to Deploy, or under the terminal command): asks for a short reason, then
    `deploy-idea.sh reject <slug>` throws the build away and files the note (the build's copy, plan included)
    as `ideas/rejected/<slug>.md`, ending in `## Rejected <date>`, `Status: rejected`, `Reason: …`; commit,
    push, Discord "Rejected". It also takes a parked or terminal note (no build to drop). From a terminal: `scripts/deploy-idea.sh reject <slug>` (asks for the reason).
- **Rejected ideas**: hidden from the Ideas card's list; **Show rejected (n)** under it lists them with date and
  reason. The planner reads `ideas/rejected/` and parks an idea that repeats a rejected one unless the note
  or the facts say what changed (M6's scout and assistant follow the same rule). A new idea box note never
  reuses a rejected note's name.
- **How the buttons work**: the dashboard can't run git or docker, and shouldn't. A button writes a request
  to `${APPDATA_PATH}/dashboard/actions/requests/` (mounted at `/actions`, its second writable mount;
  `POST /api/ideas/actions`, same-origin + admin login). `scripts/idea-actions.py` runs from dan's crontab
  every minute: it checks the slug and the action, carries it out (`deploy-idea.sh --yes [--sensitive-ok]`
  for deploys), writes `results/<id>.json`, and rewrites `status.json` (the ready builds, for the Deploy tab).
  Request text (answers, a reject reason) only ever goes into the note. So a button takes up to a minute to start; the card shows
  Queued, then Running, then the result, and the next item slides in.
- **Guarantees live in the scripts, not the page**: `deploy-idea.sh --yes` refuses terminal-only builds itself
  and refuses sensitive ones without `--sensitive-ok`. A failed answer/requeue puts main back as it was.
  `idea.sh` start/park, `deploy-idea.sh` and the runner share a lock (`.git/homelab-ideas.lock`), so the build
  loop and a dashboard deploy never write to main at the same time.
- **Auto-deploy (Risk 1)**: after the requests, the runner deploys at most one ready build per run without a
  click, only when ALL hold: the note's header (before the first `## `) has `Risk: 1` (not `1-2`, not `12`; no
  Risk line = never, so idea-box notes don't qualify); the note has the dashboard's `_Approved on the dashboard,
  <date>._` line; `deploy-idea.sh check` shows no terminal/sensitive files; Manual steps are empty or None; no
  changed file is the env template, `deploy-idea.sh`, `idea-actions.py`, `idea.sh` or `install-cron.sh`; and
  that branch commit wasn't tried before. It runs `deploy-idea.sh --yes` (no `--sensitive-ok`). Discord posts
  "Auto-deploying (Risk 1)" and, on failure, "Auto-deploy failed" once (no retry until a new push); a result
  file `auto-<slug>-<epoch>` shows in the result history. State:
  `${APPDATA_PATH}/dashboard/actions/auto-deploy.json`. Pause: `touch` `auto-deploy.off` in the same dir;
  delete it to resume.
- **Runner not running**: the tabs show a warning (no `status.json`, or older than 3 min).

### Commands
```bash
scripts/install-cron.sh                 # installs the runner (every minute)
scripts/install-cron.sh --check         # crontab vs the repo (daily 09:15, Discord on drift)
journalctl -t idea-actions -n 20        # what it did, and why something failed
scripts/idea-actions.py --status        # refresh the Deploy tab's list now
scripts/idea-actions.py --auto-dry-run  # what auto-deploy would do (writes nothing)
touch /srv/homelab/dashboard/actions/auto-deploy.off  # pause auto-deploy
scripts/deploy-idea.sh check <slug>     # terminal / sensitive files of a build
```

## Merge-friendly registries
Shared lists are split so idea branches that add jobs or scripts merge without conflicts:
1. A cron job is one file, `scripts/cron.d/<name>.cron` (one crontab line); `install-cron.sh` builds the crontab from the folder.
2. Its Kuma push monitor is one fragment, `core/uptime-kuma/compose.d/cron-<name>.yaml`; `scripts/dc.sh` merges every
   `compose.d/*.yaml` of a service dir. `deploy-idea.sh` maps a changed fragment to its service dir, so it still restarts the service.
3. The `scripts/` list in `CLAUDE.md` has one script per line, in alphabetical order.
4. New keys in `.env.example` go in their service's section, not at the end.
