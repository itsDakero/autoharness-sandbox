---
name: claude-hook-maintenance
description: Use when editing .claude/hooks/ scripts or their wiring.
category: repo-maintenance
---

# Claude Code hooks in this repo

A hook reads the tool call as JSON on stdin (`jq -r '.tool_input.file_path'`). Exit 2 with findings on stderr sends them back to Claude. Exit 0 otherwise.

- **Fail open on missing prerequisites.** No `.env`, no docker, no PyYAML, or a missing helper script: print a `warning:` on stderr and exit 0. Reserve exit 2 for real findings, so a sandbox without the server never blocks every edit.
- **Wiring is not automatic.** A hook runs only if `.claude/settings.json` lists it. Compare the hook lines in CLAUDE.md (PostToolUse compose-check, Notification/PermissionDenied/StopFailure loop-alert) against that file. The original block is in `git show 91e1616:.claude/settings.json`.
- **Keep CLAUDE.md in sync** with any change in a hook's behaviour.
- **Test with piped JSON**, never by running the real tool:
  `echo '{"tool_input":{"file_path":"'$PWD'/tools/books/compose.yaml"}}' | CLAUDE_PROJECT_DIR=$PWD bash .claude/hooks/compose-check.sh; echo rc=$?`
  Cover clean, bad, non-matching file, relative path, and each missing-prerequisite case. Simulate a missing binary with a stub `PATH` dir in the scratchpad, or by moving the helper aside and restoring it.
- **Clean up** test copies under `tools/` and `.worktrees/` before finishing.
- A file under `.worktrees/<slug>/` is checked against that checkout as the root, so a worktree copy does not clash with main's ports.
