# Discord alert when the build loop waits on a prompt or auto mode denies a call

Value: 4   (Dan: learns within minutes that the background build loop or scout is stuck, not hours later)
Effort: 1  (one hook script plus two settings entries)
Risk: 1    (Claude Code hooks and the Discord feed only; protected path, so a hand build)
Score: 20
Source: scout 2026-10-16

## Problem
Nothing tells Dan when the tmux `/loop /build-ideas` session is stuck. idea-researcher stalled twice (builder
plus one retry, about 1.5 h) with no file changed; the parked diagnosis was "a permission prompt that nobody
saw". The scout has the same exposure: docs/m6-research.md notes unlisted WebFetch domains ask, so a
background run can wait on a prompt. The loop runs in auto mode, and a classifier refusal
("[Auto-Mode Bypass]") during the 2026-10-16 ai sweep went unreported. `.claude/settings.json` has only
PreToolUse and PostToolUse hooks. Claude Code here is 2.1.299, which has a `Notification` hook (matcher
`permission_prompt`, fires after a prompt has waited about 6 s) and a `PermissionDenied` hook (auto mode
only; gets `tool_name`, `tool_input`, `reason`).

## Proposal
- New `scripts/loop-alert.sh`: reads the hook JSON from stdin and posts one line via `scripts/discord.sh`:
  event, tool name, `reason`, plus `tool_input.description` or `file_path`. Never sends command text or file
  content, in case a secret is in it. Rate limit: one post per 10 min per session (state file in the
  scratch/tmp dir). Always exits 0 so it never blocks anything.
- Register it in `.claude/settings.json` for `Notification` (matcher `permission_prompt`) and
  `PermissionDenied`.
- Gate on `HOMELAB_LOOP=1` so Dan's interactive sessions stay quiet; add the var to the loop start command
  in docs/m5-pipeline.md.
- `.claude/` is a protected path: the loop can't write it, so Dan builds this in a terminal session.

## Existing tools checked
- Claude Code hooks reference (https://code.claude.com/docs/en/hooks): Notification, PermissionDenied,
  PermissionRequest events.
- CHANGELOG 2.1.292-2.1.301 (https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md);
  local `claude --version` 2.1.299.
- scripts/discord.sh: existing non-urgent feed, reused as is.

## Rough plan
1. Write loop-alert.sh (jq parse, field allow-list, rate limit, HOMELAB_LOOP gate) and test it by piping
   sample hook JSON.
2. Add the two hook entries to .claude/settings.json in an interactive session.
3. Trigger a test prompt in a loop-flagged scratch session; confirm one Discord line, then a quiet second one.
4. Document in docs/m5-pipeline.md and the kit section of CLAUDE.md.

_Approved on the dashboard, 2026-10-16._

## Plan
Goal: Post one Discord line when the background loop (or scout) is waiting on a permission prompt or auto mode denies a call.
Split: The builder makes the script and the docs, which are all outside `.claude/`. Dan adds the two hook entries to `.claude/settings.json` by hand (see Manual steps). The builder must not touch `.claude/`.
Kind: script (Claude Code hook) + docs
Files:
- `scripts/loop-alert.sh` (new, executable, bash, `set -uo pipefail`): the hook script. It reads the hook JSON on stdin and parses it with `jq`.
  - Gate: if `HOMELAB_LOOP` is not `1`, exit 0 silently.
  - Events:
    - `Notification`: only when `notification_type == "permission_prompt"`. Message: `Loop stuck: permission prompt waiting: <message>`.
    - `PermissionDenied`: message `Loop: auto mode denied <tool_name>: <reason>`, plus ` (<tool_input.description>)` or else ` (<tool_input.file_path>)` if one is present.
    - Any other event: exit 0.
  - Both messages add ` [<agent_type>]` if that field is present, and end with ` in <basename of cwd>` (shows which worktree).
  - Field allow-list: only `hook_event_name`, `notification_type`, `message`, `tool_name`, `reason`, `tool_input.description`, `tool_input.file_path`, `agent_type`, `cwd` (basename), `session_id`. Never `tool_input.command`, `content`, `url`, `prompt` or any other input field.
  - Each field has newlines/CRs turned into spaces and is cut to 200 chars.
  - Rate limit: state dir `${XDG_RUNTIME_DIR:-/tmp}/homelab-loop-alert/` (mkdir -p, mode 700). One file per `session_id`, with the id cleaned to `[A-Za-z0-9-]`; if the id is empty, use `nosession`. The file holds the epoch of the last successful post.
    - If that was less than 600 s ago, don't post. Write the suppressed line to syslog with `logger -t loop-alert` instead.
    - Hold `flock -w 5` on `<dir>/.lock` around the check-post-stamp step.
    - Stamp only after `discord.sh` exits 0.
  - Post: `"$(dirname "$0")/discord.sh" "<msg>"`.
  - Dry run: with `LOOP_ALERT_DRY=1`, print the message to stdout instead of posting (still rate-limited and stamped), so it can be tested in the worktree, which has no env file.
  - Always `exit 0`: no stdout except in dry-run, no `hookSpecificOutput` (never sets `retry`). If jq or the input is bad, log it and exit 0.
  - Header comment: purpose, hook events, gate var, dry-run var, and that `.claude/settings.json` registration is done by hand.
- `docs/m5-pipeline.md`: change the Stage C "Start it" line to `HOMELAB_LOOP=1 claude`, then `/loop /build-ideas`. Add a bullet "Stall alerts" covering:
  - what posts and when (prompt waits about 6 s; auto-mode denials);
  - at most one post per session every 10 min;
  - interactive sessions stay quiet;
  - `journalctl -t loop-alert` / `-t discord`;
  - the settings.json snippet from Manual steps.
- `CLAUDE.md`:
  - Layout scripts list: add `loop-alert.sh` (Claude Code hook: Discord line when the loop waits on a prompt or auto mode denies a call; only with `HOMELAB_LOOP=1`).
  - Kit section: one line "Hooks `Notification` (permission_prompt) and `PermissionDenied` run `scripts/loop-alert.sh`".
New service: None
New env vars: None. `HOMELAB_LOOP` is a shell var set on the loop's start command, not a `.env` var.
Checks the builder must run (in the worktree):
- `bash -n scripts/loop-alert.sh`; `test -x scripts/loop-alert.sh`
- Each test uses its own `XDG_RUNTIME_DIR=$(mktemp -d)`:
  1. Without `HOMELAB_LOOP`: `echo '{"hook_event_name":"Notification","notification_type":"permission_prompt","message":"Claude needs your permission to use Bash","session_id":"t1","cwd":"/x/y"}' | LOOP_ALERT_DRY=1 scripts/loop-alert.sh` gives no output, exit 0.
  2. With `HOMELAB_LOOP=1`: the same input prints one line. Running it again within 10 min prints nothing. Changing `session_id` to `t2` prints again.
  3. PermissionDenied sample with `tool_input` `{"command":"echo SECRET123","description":"Clean build"}` and reason `[Irreversible Local Destruction]` prints a line that contains "Clean build" and does not contain SECRET123.
  4. `idle_prompt` gives no output. Input `not json` gives exit 0. Every case exits 0.
Review focus:
- A secret in a command or file content -> never in the message; only allow-listed fields are sent.
- A denial loop, or a prompt re-firing many times -> one Discord post per session per 10 min; extras go to syslog only.
- Discord down, or the webhook unset -> exits 0 quickly (curl -m 10 inside discord.sh), no stamp, so the next event retries; the loop is never blocked.
- Two hooks firing at once (main agent + subagent) -> flock keeps it to one post.
- Dan's interactive sessions (var unset) -> silent, no state written.
Docs: CLAUDE.md scripts list and kit section; docs/m5-pipeline.md Stage C start line and the "Stall alerts" bullet. No port table change.

## Manual steps
1. Dan, in an interactive terminal session (the loop can't write `.claude/`): add the following to `.claude/settings.json` under `"hooks"`, next to PreToolUse/PostToolUse.
   ```
   "Notification": [{"matcher": "permission_prompt", "hooks": [{"type": "command",
     "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/loop-alert.sh"}]}],
   "PermissionDenied": [{"matcher": "*", "hooks": [{"type": "command",
     "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/loop-alert.sh"}]}]
   ```
   Then commit it.
2. Restart the tmux loop as `HOMELAB_LOOP=1 claude`, then `/loop /build-ideas`.
3. Test: in a scratch session started with `HOMELAB_LOOP=1 claude`, trigger a prompt (e.g. a WebFetch to an unlisted domain). You should get one Discord line, and a second prompt within 10 min should stay quiet (`journalctl -t loop-alert`).

## Review notes
1. /home/dan/homelab/.worktrees/loop-stall-alert/scripts/loop-alert.sh:22: `cut -c1-200` counts bytes in GNU coreutils, so a long field with non-ASCII text can be cut partway through a UTF-8 character. discord.sh would then send a garbled last character. It's cosmetic only.
2. `reason` comes from the auto-mode classifier and is on the plan's allow-list. It is classifier prose, but it could in theory quote part of the denied command. This is acceptable under the plan. Watch the first few real posts.
3. On the failed-post question: the code only writes the stamp after a successful post (`(( ok == 0 )) && echo "$now" > "$dir/$sid"`). I tested this with a stub discord.sh that exits 1. It exits 0, and the state dir holds only `.lock` with no session file. With a stub that exits 0, the `t1` stamp is written. While Discord is down, each event retries and can take up to about 10 s (curl -m 10) while it holds the lock. That fits the plan. An unset webhook fails at once.
4. Concurrency: I started three hooks at once against a stub discord.sh that sleeps 2 s. That gave exactly one post. The others were suppressed or hit the lock timeout and went to syslog.

## Declined to judge
- Whether the Notification `message` text could ever hold command text: Claude Code produces it, and the plan allow-lists it.
- Whether subagents share the parent's `session_id`, which decides if the rate limit spans main agent and subagents: this is Claude Code runtime behaviour, and Dan's step 3 tests it live.
