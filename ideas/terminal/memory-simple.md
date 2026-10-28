# Memory, stage 1: a plain-markdown memory store + /memory skill

Value: 5   (agents stop relearning the same fixes and gotchas; CLAUDE.md gets shorter)
Effort: 3  (CLAUDE.md audit, one script, one skill, a seed)
Risk: 2    (writes under .claude/ and edits CLAUDE.md, which every loop stage loads)
Score: 15
Source: Dan 2026-10-26 (M6 "Brain", phase 1 of 3; chain: memory-safe, memory-dream, memory-panel)

## Problem
What Claude learns about this server lives in three places: CLAUDE.md (166 lines, over the ~150 the
pipeline doc asks for, and loaded by every stage), docs/, and Claude Code's own auto-memory
(`~/.claude/projects/-home-dan-homelab/memory/`, 8 notes, invisible to the loop's worktrees and to Dan's
review). There is no single place an agent can search progressively, and no rule for what's worth keeping.

## Proposal
- **Store**: `~/homelab/memory/`, its own git repo, git-ignored by the homelab repo (restic still
  backs it up through the repo dir). Two folders:
  - `org/` = stable facts: hardware, network, conventions, security.
  - `team/` = working knowledge: fixes, gotchas, flaky things.
  - `README.md` = the note format (below), for humans.
- **Note format**: one fact per file, `<folder>/<slug>.md`, frontmatter:
  ```
  ---
  name: <slug>
  description: <one line, used for search>
  updated: YYYY-MM-DD
  source_session: <session id | manual | seed>
  confidence: high | medium | low
  ---
  ```
  Body: the fact, then `**Why:**` and `**How to apply:**`. No database, no index file that must be
  loaded whole.
- **`scripts/memory.sh`**:
  - `init`: creates the store, `org/`, `team/`, README, `git init`, first commit. Idempotent.
  - `search <words...>`: grep the frontmatter (`name:`/`description:`) first, then bodies; prints
    `path  description`, never file contents. Case-insensitive, all words must match.
- **`.claude/skills/memory/SKILL.md`** (`/memory`; its description also triggers it when a question
  touches server facts, past fixes or gotchas):
  - Read: `scripts/memory.sh search` (or `grep -l` on frontmatter) first, open only the matches, never
    the whole tree, at most ~5 notes per question. Treat `confidence: low` as a hint, check it.
  - Write: when something reusable is learned, above all a correction from Dan, write or update
    `team/<slug>.md` with the reason. Update an existing note rather than adding a duplicate (search
    first). Set `updated` and `source_session` (the current session ID).
  - Never store secrets, tokens, passwords, keys, webhook URLs, or the contents of the env file;
    refer to a variable by name only.
  - `/memory seed` (one-off): build the first notes from CLAUDE.md, docs/ and the 8 auto-memory notes.
    org/ gets hardware (GTX 970 + driver 580 pin, disks, Mac mini), network (LAN/Tailscale IPs, DNS
    model, ports policy), conventions (compose rules, labels, logging, healthchecks), security (socket
    proxy, no sudo, media read-only, forensics data out of restic). team/ gets the gotchas (guard
    matches text in commands/heredocs/commit messages, ccl blockfile bug, sda 187/188 exception,
    loop compaction, one command at a time when Dan runs commands, etc.).
- **CLAUDE.md audit** (target ~100 lines): the `scripts/` list moves to `docs/scripts.md` (same
  one-per-line format, alphabetical; indexed in `docs/README.md`), and CLAUDE.md keeps one line
  pointing there. Rules, access model, layout, ports and labels stay (every loop stage needs them).
  Hardware/network detail that isn't a rule moves into `org/` notes. Add a 3-line "Memory" section:
  where it is, search first with `scripts/memory.sh search`, write with `/memory`.
- Anything that says where the scripts list lives (add-service skill, build-ideas, docs) is updated.
- This writes under `.claude/`, so it is a terminal build.

## Manual steps
1. `scripts/memory.sh init`
2. In a terminal session: `/memory seed`, then review with `git -C memory log -p`.
3. Turn off Claude Code's auto-memory for this project: `"autoMemoryEnabled": false` in
   `.claude/settings.json` (Dan's decision 2026-10-26: migrate the 8 notes, keep one system).

## Test it
- New session: "which NVIDIA driver branch is pinned and why?" -> it runs the search, opens one
  org/ note, answers.
- Correct it on something -> a new or updated team/ note with a `**Why:**` line.
- `grep -rL '^confidence:' --exclude-dir=.git memory/` prints nothing (every note has frontmatter).
- `wc -l CLAUDE.md` is about 100.

## Chain
memory-safe (stage 2), memory-dream (3a) and memory-panel (3b) wait in `ideas/waiting/`. Dan tests
each stage before deploying it.

## Plan
Goal: one plain-markdown memory store (`memory/`, its own git repo) plus `scripts/memory.sh` and a `/memory` skill, and CLAUDE.md cut to about 110 lines.
Kind: change to the Claude Code kit + docs (terminal build: it writes under `.claude/`)
Files:
- .gitignore: add `memory/` with the comment "# Memory store: its own git repo (scripts/memory.sh init); the repo dir is in restic"
- scripts/memory.sh: new, bash, `set -euo pipefail`, executable. Usage text on no args or a bad subcommand (exit 2).
  - Store path: `MEMORY_DIR` env if set, otherwise `<main checkout>/memory`, where the main checkout is
    `dirname "$(git -C "$(dirname "$0")" rev-parse --path-format=absolute --git-common-dir)"`. This way a run
    from `.worktrees/<slug>` still finds the live store, because `memory/` is git-ignored and absent in worktrees.
  - `init`: mkdir `org/` and `team/` (each gets a `.gitkeep`) and write `README.md` (the note format below, the
    no-secrets rule, a pointer to /memory) only if it is missing. Run `git init` only if `.git` is missing, then
    commit "memory: init" only when something is staged. Running it a second time changes nothing and prints "memory store ok: <path>".
  - `search <words...>`: needs at least one word (exit 2). Searches `org/*.md team/*.md` only, never README or `.git`.
    It is case-insensitive and treats words as fixed strings (`grep -iF`). A file matches when every word appears.
    It does two passes: first files where all words are in the `name:`/`description:` lines, then files where all
    words are anywhere in the file. A file is printed once. Each line is `<path relative to store>  <description>`.
    It never prints a body. No match: print "no notes match" and exit 1. Missing store: say "run scripts/memory.sh init" and exit 2.
- .claude/skills/memory/SKILL.md: new. Frontmatter is `name: memory` and `argument-hint: [seed | <question>]`. The
  description should make the skill trigger on questions about this server's hardware, network, conventions, past
  fixes, gotchas or flaky things, and on corrections from Dan. It covers:
  - Read: run `scripts/memory.sh search <words>` first (no recursive grep: guard.py blocks it without
    --exclude). Open only the matches, at most 5 notes per question. Treat `confidence: low` as a hint to verify.
  - Write: search first, then update an existing note rather than adding a duplicate. A new reusable fact goes in
    `team/<slug>.md`. org/ notes are written only by seed or when Dan asks. Use the frontmatter exactly as in the note,
    set `updated: <today>` and `source_session: ${CLAUDE_SESSION_ID}`, and give the body the fact,
    `**Why:**` and `**How to apply:**`. One fact per file. Slugs are lowercase-kebab. After a write, run
    `git -C <store> add <file> && git -C <store> commit -m "memory: <slug>"`.
  - Never store secrets, tokens, passwords, keys, webhook URLs or env-file contents; refer to a variable by name.
    Write "the env file" rather than its filename (guard.py matches the text).
  - `seed` (when $ARGUMENTS is `seed`): build the notes from CLAUDE.md, docs/ and the 8 files in
    `~/.claude/projects/-home-dan-homelab/memory/` (not MEMORY.md itself). The org/ and team/ topics are as listed in
    the idea note. Use `source_session: seed`. Skip any note that already exists. Commit once ("memory: seed"), then
    print the list of notes.
- .claude/settings.json: allow `Bash(scripts/memory.sh *)`, `Edit(./memory/**)` and `Write(./memory/**)`.
  Do NOT add autoMemoryEnabled here; that is a manual step.
- docs/scripts.md: new. The whole `scripts/` list moves here from CLAUDE.md verbatim: one per line, alphabetical,
  with its intro rule (new cron jobs = cron.d + compose.d fragment). Add a `memory.sh` line in its spot.
- docs/claude-kit.md: new. The detail of CLAUDE.md's "Claude Code kit" section moves here verbatim: the skills
  list, the guard.py blocklist, the hooks, and the permissions paragraph.
- CLAUDE.md:
  - The `scripts/` bullet becomes one line: "scripts/ – one script per file; the list (one per line,
    alphabetical; new cron jobs = `scripts/cron.d/<name>.cron` + `core/uptime-kuma/compose.d/cron-<name>.yaml`) is in
    `docs/scripts.md`: add new scripts there".
  - The `tools/` layout bullet keeps every service name and its README pointer but loses the long descriptions.
  - The kit section shrinks to at most 6 lines: skills by name, "hooks/guard/permissions: docs/claude-kit.md", and
    keeps verbatim the sentence "a new core service must be added there (`media/*`, `tools/*` are wildcards;
    `games/*` still needs adding)" together with the ask-rule context it needs.
  - Add a 3-line "## Memory" section: `memory/` (own git repo, org/ = stable facts, team/ = fixes and gotchas);
    search first with `scripts/memory.sh search <words>`; write with `/memory`.
  - Rules, Access model, the Ports and Labels tables, and the GPU line stay word for word.
- docs/README.md: add rows for `docs/scripts.md`, `docs/claude-kit.md` and `memory/README.md` (the memory store's note format).
- docs/m5-pipeline.md: in Merge-friendly registries item 3, change "in `CLAUDE.md`" to "in `docs/scripts.md`".
  Change the Context bullet to "~110 lines; scripts list in docs/scripts.md, kit detail in docs/claude-kit.md".
- .claude/agents/idea-planner.md: in the reply template's Docs line, "scripts list" becomes "docs/scripts.md".
- .claude/agents/idea-reviewer.md: item 5 (Docs) adds "a new script has its line in docs/scripts.md".
New service: None
New env vars: None (MEMORY_DIR is an optional shell override, not a `.env` key)
Checks the builder must run:
- `bash -n scripts/memory.sh`
- `python3 -c 'import json;json.load(open(".claude/settings.json"))'`
- `MEMORY_DIR=<scratch dir> scripts/memory.sh init` twice: the second run makes no new commit
- Write two sample notes there and check:
  - `search GPU driver` lists the frontmatter match first
  - `search nosuchword` exits 1
  - output has no body lines
- From `.worktrees/memory-simple`, `scripts/memory.sh` (no MEMORY_DIR) resolves to `/home/dan/homelab/memory`
  (print the path on the "not initialised" error)
- `wc -l CLAUDE.md` is 115 or less
- `diff <(old CLAUDE.md scripts entries) <(docs/scripts.md entries)` shows only the added memory.sh line
- The port table is unchanged: `git diff main -- CLAUDE.md | grep '^[-+]| [0-9]'` prints nothing
Review focus:
- Run from a worktree, or the store not initialised -> it finds the main checkout's `memory/`, or clearly says
  to run init; it never creates a second store inside the worktree.
- Search words with regex characters, or a note without frontmatter -> fixed-string match, no crash, and the
  note is still found by body with an empty description.
- `init` re-run on a store with notes -> no overwrite of README or notes, and no empty commit.
- Seed or skill writes a secret or the env-file name -> the skill forbids it. No secret values are copied from
  CLAUDE.md or docs (variable names only).
- CLAUDE.md trim drops a rule the loop relies on (port table, ask-rule core-service sentence, GPU pin,
  forensics/media rules) -> all still present word for word.
Docs: CLAUDE.md (scripts list and kit detail moved out, Memory section, shorter tools/ bullet), new
  docs/scripts.md and docs/claude-kit.md, docs/README.md rows, docs/m5-pipeline.md (registries item 3, Context).

## Manual steps
1. `scripts/memory.sh init`
2. In a terminal session, run `/memory seed`. Review it with `git -C memory log -p`. Check
   `grep -rL '^confidence:' --exclude-dir=.git memory/org memory/team` prints nothing.
3. Only after the seed: turn off auto-memory with `"autoMemoryEnabled": false`. The planner could not confirm
   this key is honoured from the project `.claude/settings.json`, so the build doesn't set it there.
   - Put it in `.claude/settings.json` (or `~/.claude/settings.json`).
   - If `claude doctor` or `/status` reports it as ignored, set `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` in the `env`
     block instead.
   - The 8 old notes stay on disk. Delete them only once the seed looks right.
4. Test as in the note: ask "which NVIDIA driver branch is pinned and why?" in a new session.

## Build in a terminal 2026-10-26

Planned files under .claude/ (Claude Code asks before each write there, and
nobody sees that in the background loop):
- .claude/skills/memory/SKILL.md
- .claude/settings.json
- .claude/agents/idea-planner.md
- .claude/agents/idea-reviewer.md
