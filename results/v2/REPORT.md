# Autoharness sandbox v2: report

## Status: stopped at step 1 (blocked)

Nothing was built. No child sessions ran.

## What was blocked

- **Step 1: installing the plugin.**
- Command (run from the repo root):
  - `claude plugin marketplace add tigerless-labs/autoharness`
  - `claude plugin install autoharness@autoharness --scope project`
- Blocked by: Claude Code's **auto mode classifier**, before the command ran.
- Reason given: `[Untrusted Code Integration]`.
- The fix it suggests: add a permission rule for Bash to the settings.

## What was not tried

- **Step 2** (child sessions with `claude -p ... --dangerously-skip-permissions`). Not run.
  - It needs the plugin first.
  - It may hit the same kind of check. Expect a second approval.
- No research, no tasks, no commits besides this report.
- I did not try another way to install the plugin. The brief says not to work around a block.

## What Dan needs to do

- Approve the plugin install in this session (or add a Bash allow rule for those two commands).
- Then approve the `--dangerously-skip-permissions` child sessions for step 2.
- After that I can pick up from step 1.

## Context

- Claude Code CLI: 2.1.312.
- `.claude/settings.json` already lists the marketplace and enables the plugin. The plugin itself is not installed.
