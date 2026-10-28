# Make the guard hook fail closed

Value: 3   (Dan: the secrets/sudo/media/docker.sock guard can no longer be bypassed by a crash or timeout)
Effort: 1  (two fields in settings.json plus checking guard.py's exit paths)
Risk: 1    (Claude Code settings only; protected path, so a hand build)
Score: 15
Source: scout 2026-10-16

## Problem
`.claude/hooks/guard.py` enforces the rules on secrets, sudo, `/mnt/media`, docker.sock and `:latest`. Its
`main()` calls `json.load(sys.stdin)` with no try/except (lines 147-165). Today any uncaught exception, a
missing `python3` or a timeout is a non-blocking hook error, so the tool call runs anyway. The hooks docs
say it plainly: "a policy hook with a wrong path or a crashing script lets everything through." Claude Code
2.1.295 (Oct 8) added `"onFailure": "block"` for command hooks; this host runs 2.1.299.

## Proposal
- Add `"onFailure": "block"` and an explicit `"timeout": 10` to the PreToolUse guard entry in
  `.claude/settings.json`.
- Check every path in guard.py ends in exit 0 (allow, or "ask" JSON) or exit 2 (block); no other codes.
- Mention fail-closed in the kit section of CLAUDE.md.
- `.claude/` is a protected path, so Dan builds this in a terminal session.

## Existing tools checked
- Claude Code hooks docs, "Block the action when a hook fails" (https://code.claude.com/docs/en/hooks).
- CHANGELOG 2.1.295 and 2.1.299 (https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md).
- .claude/hooks/guard.py: already uses exit 2 to block and exit 0 with an "ask" JSON.

## Rough plan
1. Audit guard.py exit paths; make sure normal allows exit 0.
2. Add onFailure/timeout to the guard entry (compose-check.sh stays as is; it's PostToolUse).
3. Test in a scratch session: temporarily misspell the guard command path and confirm calls are blocked;
   restore; confirm normal work, the `.env` block and the `:ro` ask still behave.
4. Update CLAUDE.md kit section.

_Approved on the dashboard, 2026-10-16._

## Parked 2026-10-16

## Questions
Reason: build it in a terminal. All the code changes are under `.claude/`, a protected path, so a background builder would stall on them. The only part outside `.claude/` is one line in CLAUDE.md, which describes behaviour the settings change creates, so it should not go in on its own.

Checked facts: hooks docs (https://code.claude.com/docs/en/hooks) confirm `onFailure` takes `"continue"` (default) or `"block"` on command hooks, from v2.1.295. Failures: can't start, exit other than 0/2, timeout, invalid JSON. On PreToolUse, a failure under `"block"` acts like exit 2. `timeout` is in seconds (default 600). This host runs 2.1.299.

1. OK to build this in a terminal session from the plan below, with the CLAUDE.md line in the same commit? (yes/no)

## Plan (for the terminal build)
Goal: a crash, a missing interpreter or a timeout in the PreToolUse guard blocks the tool call instead of letting it through.
Kind: change to the Claude Code kit (.claude/settings.json, .claude/hooks/guard.py) plus CLAUDE.md
Files:
- `.claude/settings.json`: in the single PreToolUse hook entry (matcher `Bash|Read|Edit|Write|MultiEdit|Grep|NotebookEdit`, command `"$CLAUDE_PROJECT_DIR"/.claude/hooks/guard.py`), add `"timeout": 10` and `"onFailure": "block"`. Leave the PostToolUse compose-check.sh entry as it is.
- `.claude/hooks/guard.py`:
  - Audit result: every deliberate path already exits 0 (normal return, or `ask()` printing JSON and calling `sys.exit(0)`) or 2 (`block()`). The gaps are uncaught exceptions, which exit 1: malformed or empty stdin in `json.load`; `data` not a dict; `tool_input` not a dict; `"command": null` reaching `MESSAGE_ARG.sub`; a non-string `file_path` reaching `PurePath`.
  - Fix: rename the body of `main()` to `_main()`. The new `main()` calls `_main()` inside `try/except Exception as e: block(f"guard error ({type(e).__name__}: {e}); failing closed.")`. `SystemExit` is not an `Exception`, so the existing exits still pass through.
  - In `_main()`, after the load: `if not isinstance(data, dict): block("unexpected hook input")`. Then `inp = data.get("tool_input") or {}`, and if `inp` is not a dict, block.
  - `check_command(inp.get("command") or "")`.
  - Module docstring: any error exits 2, and settings.json has `onFailure: block` for crashes Python can't catch.
- `CLAUDE.md`, kit section, the `Hook guard.py (PreToolUse)` bullet: add "Fails closed: `onFailure: block`, 10 s timeout; a guard crash or timeout blocks the call."

Checks:
- `python3 -m py_compile .claude/hooks/guard.py`; `python3 -m json.tool .claude/settings.json >/dev/null`
- Pipe tests into guard.py, check exit codes:
  - `printf 'garbage'` -> 2, stderr starts with "Blocked by homelab guard: guard error"
  - `printf '[]'` -> 2
  - `{"tool_name":"Bash","tool_input":{"command":null}}` -> 0
  - `{"tool_name":"Bash","tool_input":{"command":"ls"}}` -> 0
  - Read of the repo env file -> 2
  - Write of a compose.yaml mounting /mnt/media without :ro -> 0 with the "ask" JSON on stdout
- Live session test: temporarily change the command path to `guard.pyX`, start a fresh session, `ls` must be refused ("blocking because onFailure is block"). Restore, new session: `ls` runs, reading the env file is blocked, a compose write with /mnt/media and no :ro asks. `git diff` shows only the two new settings fields.

Review focus:
- Malformed or empty hook JSON -> exit 2 with "guard error", never 1 or 0.
- `ask()` path -> still exit 0 with valid JSON (any other exit would now block instead of ask).
- Large Write (~1 MB content) -> guard finishes well under 10 s; flag if over 1 s.
- Path-typo test left in place -> settings.json must be restored exactly, or every tool call (including the loop's) is blocked.
- Non-Bash tools with missing fields (Grep with no path, Read with only file_path) -> exit 0.

## Manual steps
Build in a terminal session (Dan approves the `.claude/` writes). After merging, restart running Claude Code sessions, including the `/loop /build-ideas` loop, so the new hook settings load.

## Answers 2026-10-16

1. Yes

## Plan
Goal: if the PreToolUse guard crashes, can't start or times out, the tool call is blocked instead of let through. Dan said yes on 2026-10-16 to a terminal build with the CLAUDE.md line in the same commit.
Kind: change to the Claude Code kit (`.claude/settings.json`, `.claude/hooks/guard.py`) plus CLAUDE.md
Files:
- .claude/settings.json: the only PreToolUse hook entry (matcher `Bash|Read|Edit|Write|MultiEdit|Grep|NotebookEdit`, command `"$CLAUDE_PROJECT_DIR"/.claude/hooks/guard.py`) gets two new fields, `"timeout": 10` and `"onFailure": "block"`. Leave the PostToolUse compose-check.sh entry alone.
- .claude/hooks/guard.py:
  - Rename the current `main()` body to `_main()`. The new `main()` runs `_main()` inside `try: ... except Exception as e: block(f"guard error ({type(e).__name__}: {e}); failing closed.")`. `SystemExit` isn't an `Exception`, so the existing exit 0 and exit 2 calls still get through.
  - In `_main()`, right after `json.load`: if `data` is not a dict, `block("unexpected hook input")`. Then `inp = data.get("tool_input") or {}`, and if `inp` is not a dict, block the same way.
  - Change the Bash branch to `check_command(inp.get("command") or "")`, so a `null` command is allowed instead of crashing.
  - Add to the module docstring: any internal error exits 2, and settings.json sets `onFailure: block` for failures Python can't catch (missing interpreter, timeout).
  - Leave all other logic alone. The audit found every deliberate path already ends in exit 0 (normal return, or `ask()`) or exit 2 (`block()`).
- CLAUDE.md: at the end of the kit-section bullet "Hook `guard.py` (PreToolUse) blocks: ..." (line 82 onward), add: "Fails closed (`onFailure: block`, 10 s timeout): a guard crash or timeout blocks the call."
New service: None
New env vars: None
Checks the builder must run (from the worktree):
- `python3 -m py_compile .claude/hooks/guard.py`; `python3 -m json.tool .claude/settings.json >/dev/null`
- Pipe each input into `.claude/hooks/guard.py` and check the exit code:
  - `printf 'garbage'` -> 2, stderr starts with "Blocked by homelab guard: guard error"
  - `printf ''` -> 2; `printf '[]'` -> 2; `{"tool_name":"Bash","tool_input":"x"}` -> 2
  - `{"tool_name":"Bash","tool_input":{"command":null}}` -> 0
  - `{"tool_name":"Bash","tool_input":{"command":"ls"}}` -> 0
  - `{"tool_name":"Read","tool_input":{"file_path":"/home/dan/homelab/.env"}}` -> 2
  - `{"tool_name":"Grep","tool_input":{"pattern":"x"}}` -> 0
  - A Write of `x/compose.yaml` whose content has `- /mnt/media:/media` (no `:ro`) -> 0, with valid "ask" JSON on stdout
  - A Write with about 1 MB of content -> 0, finishing in well under 1 s (time it)
- Live session test: change the command path to `guard.pyX` for a moment and start a fresh session; `ls` must be refused. Put it back and start another fresh session: `ls` runs, reading the env file is blocked, and a compose write with /mnt/media and no `:ro` asks first. Afterwards `git diff .claude/settings.json` must show only the two new fields.
Review focus:
- Malformed, empty or non-dict hook JSON -> exit 2 with "guard error" or "unexpected hook input", never exit 1 or 0.
- The `ask()` path -> still exit 0 with valid JSON on stdout; anything else would now block instead of asking.
- Path-typo test left in place -> settings.json restored exactly; otherwise every tool call, the loop's included, is blocked.
- Non-Bash tools with missing or null fields (Grep with no path, Read with only file_path) -> exit 0.
- Large Write content (about 1 MB) -> finishes far below the 10 s timeout; flag it if it takes over 1 s.
Docs: CLAUDE.md kit section, the guard.py bullet (above). No port, layout or scripts-list changes.

## Manual steps
Build this in a terminal session, where Dan approves the `.claude/` writes. After merging, restart every running Claude Code session, including the `/loop /build-ideas` loop, so it loads the new hook settings. The host runs Claude Code 2.1.299, and `onFailure` needs 2.1.295 or later.

## Build in a terminal 2026-10-16

Planned files under .claude/ (Claude Code asks before each write there, and
nobody sees that in the background loop):
- .claude/settings.json
- .claude/hooks/guard.py

## Review notes
1. The changes are uncommitted in the worktree (`git status` shows M on the three files). That's expected for a terminal build, but they need committing before deploy-idea.sh can merge them.
2. A non-string `file_path` (e.g. `123`) now gets exit 2 with "guard error (TypeError ...)". That is the right fail-closed behaviour, and Claude Code never sends one anyway.
3. I could not run the live-session `guard.pyX` test because it needs a fresh session. I checked the restore by reading the diff: `/home/dan/homelab/.worktrees/guard-fail-closed/.claude/settings.json` has the original command path unchanged, plus only `"timeout": 10` and `"onFailure": "block"`.

## Declined to judge
None
