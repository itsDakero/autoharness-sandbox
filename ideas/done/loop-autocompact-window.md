# Cap the build loop's context with an auto-compact window

Value: 4   (Dan: the always-on loop stops eating the subscription usage limit his own sessions share)
Effort: 1  (one launcher script and a doc line)
Risk: 1    (only how the loop session is started; interactive sessions untouched)
Score: 20
Source: scout 2026-10-19

## Problem
The `/loop /build-ideas` session (auto mode, Opus, started 2026-10-16) has never compacted. Its context grows
by about 200K tokens a day: the largest prompt per day was 115K, 302K, 476K, then 693K (2026-10-19 15:24).
Cache-read tokens per day went 5.0M, 32.5M, 56.7M, 102.7M, roughly doubling. 99 of 108 ticks found the queue
empty, yet each made 3 Opus calls at about 680K tokens apiece (about 2M tokens per idle tick). Nothing stops
this before about 967K: 1M-context models only auto-compact there by default, and idle compaction
(2.1.299) needs about 54 minutes idle while the loop ticks every 30. The loop and Dan's own sessions share
one usage limit.

## Proposal
`scripts/loop.sh`: start (or attach to) a tmux session `claude` running
`HOMELAB_LOOP=1 CLAUDE_CODE_AUTO_COMPACT_WINDOW=150000 claude`, then Dan types `/loop /build-ideas` as today.
The env var beats every setting, needs no write under `.claude/` (so it stays in the background lane), and
leaves interactive sessions alone. Update the "Start it" line in `docs/m5-pipeline.md` and the `scripts/`
list in CLAUDE.md. No container, no port, no secrets.

## Existing tools checked
- Claude Code auto-compact window (https://code.claude.com/docs/en/model-config): `CLAUDE_CODE_AUTO_COMPACT_WINDOW` / `--autocompact` / `autoCompactWindow`, 100K-1M; installed 2.1.302, latest 2.1.303 (bug fixes only). Chosen: env var, scoped to the loop.
- Idle compaction and `CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS`, CHANGELOG 2.1.299 (https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md): never fires at a 30 min tick; not enough alone.
- `autoCompactWindow` subagent frontmatter (2.1.296): was noted this morning with "no compaction trouble seen"; the trouble is in the main loop session, not the subagents.

## Rough plan
1. `scripts/loop.sh` (idempotent: attach if the tmux session exists), executable, with a short usage header.
2. Check that a `/loop` schedule survives a compaction (force one with a small window in a test session);
   if it doesn't, note the fallback (re-issue `/loop` after compaction) in the doc.
3. Update `docs/m5-pipeline.md` "Start it" and CLAUDE.md's `scripts/` list. Optional: a lower tick rate
   when the queue is empty, only if it needs no `.claude/` write.

_Approved on the dashboard, 2026-10-19._

## Plan
Goal: Start the build loop's Claude session with a 150K auto-compact window, so it stops sending ~680K-token prompts on every idle tick.
Kind: script/cron (a launcher script plus docs)
Files:
- scripts/loop.sh: new, executable (chmod +x), bash with `set -euo pipefail`. It needs a usage header comment saying: it starts or attaches to the tmux session `claude`, which runs the loop's Claude with `HOMELAB_LOOP=1 CLAUDE_CODE_AUTO_COMPACT_WINDOW=150000`; then type `/loop /build-ideas`; the env only applies to a newly started session. Behaviour:
  - `command -v tmux` and `command -v claude` must succeed, otherwise print an error to stderr and exit 1.
  - Session name `claude`, start dir `/home/dan/homelab`. Put the repo path in a variable worked out from the script's own location: `$(cd "$(dirname "$0")/.." && pwd)`.
  - If `tmux has-session -t claude` succeeds: print to stderr "session 'claude' already exists; the compact window applies only to a new session. To restart: quit claude in it, `tmux kill-session -t claude`, then rerun scripts/loop.sh". Then attach. If `$TMUX` is set, use `tmux switch-client -t claude`; otherwise use `tmux attach -t claude`. Never kill or restart the session yourself.
  - Otherwise run `tmux new-session -d -s claude -c "$repo" "env HOMELAB_LOOP=1 CLAUDE_CODE_AUTO_COMPACT_WINDOW=150000 claude; exec bash"`. The trailing `exec bash` keeps the window open after claude exits, so errors stay readable. Then attach (or switch-client) as above, and print the hint "type: /loop /build-ideas" before attaching.
  - Optional `LOOP_COMPACT_WINDOW` env override (default 150000). Reject it unless it is an integer from 100000 to 1000000, with exit 1.
  - Pass no other flags: model and auto mode stay as they are today.
- docs/m5-pipeline.md: change the "Start it" bullet (line 44) to: `scripts/loop.sh` (tmux session `claude`, with `HOMELAB_LOOP=1` and `CLAUDE_CODE_AUTO_COMPACT_WINDOW=150000`), then `/loop /build-ideas`. Add one sentence: the 150K window makes the loop compact long before the 1M default, so idle ticks stay cheap; it only affects that session. To change a running session, quit it, `tmux kill-session -t claude`, and rerun. Also add the fallback: if the `/loop` schedule is gone after a compaction, type `/loop /build-ideas` again.
- CLAUDE.md: in the `scripts/` list, next to `loop-alert.sh`, add `loop.sh` (starts/attaches the loop's tmux session `claude` with HOMELAB_LOOP=1 and a 150K auto-compact window).
New service: None
New env vars: None for `.env` (`LOOP_COMPACT_WINDOW` is an optional shell override only)
Checks the builder must run:
- `bash -n scripts/loop.sh`, and `shellcheck scripts/loop.sh` if it is installed
- `test -x scripts/loop.sh`
- `LOOP_COMPACT_WINDOW=abc scripts/loop.sh; echo $?` must print an error and 1 without touching tmux. Do the validation before any tmux call. Do NOT run the script without the bad value: the live loop runs in session `claude`.
Review focus:
- session `claude` already exists (it does today, with the live loop) -> attach only and print the restart hint; never kill, respawn or send keys to it
- run from inside tmux -> switch-client, not a nested attach error
- claude exits or crashes in the new session -> the window stays open on a shell (exec bash), so the error stays readable
- bad LOOP_COMPACT_WINDOW -> exit 1 before any tmux action
- interactive sessions -> untouched: no settings.json or `.claude/` change, and the env var is set only on the loop's command
Docs: the m5-pipeline.md "Start it" bullet plus the fallback sentence; the CLAUDE.md `scripts/` list entry.

## Manual steps
1. After merging: in the current `claude` tmux session, stop the loop (Esc) and quit claude, then run `tmux kill-session -t claude`, `scripts/loop.sh`, and `/loop /build-ideas`.
2. After the first compaction (when context passes about 150K, within a day), check that the `/loop` ticks still run. If they stopped, re-issue `/loop` (the doc has this fallback). This replaces the note's step 2: a background builder can't drive an interactive test session.

## Review notes
1. /home/dan/homelab/.worktrees/loop-autocompact-window/scripts/loop.sh:28 and :22-24: `tmux has-session -t claude`, `attach -t claude` and `switch-client -t claude` use tmux's normal target matching, so they also match a session whose name starts with "claude" (e.g. `claude-test`) when no exact `claude` exists. In that case the script would attach to the wrong session and not start the loop. Using `-t =claude` forces an exact match. This doesn't happen with today's single session.
2. A value with leading zeros such as `LOOP_COMPACT_WINDOW=0150000` passes the check (`[` compares in decimal) and goes to claude unchanged. It's harmless and you'd have to set it on purpose.
3. shellcheck isn't installed on the host, so that optional check was skipped. `bash -n` passes and the file is executable.
4. The plan asked for the hint "type: /loop /build-ideas", and it goes to stdout while the other messages go to stderr. That's fine, just inconsistent.

## Declined to judge
- Whether a `/loop` schedule survives a compaction: it can't be tested from a background review. The plan moved this to manual step 2, and the doc has the fallback.
- Whether `CLAUDE_CODE_AUTO_COMPACT_WINDOW` is honoured by the installed Claude Code 2.1.302: that comes from the scout's docs research, and I didn't test it live.
