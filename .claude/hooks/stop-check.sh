#!/usr/bin/env bash
# Stop: if the working tree changes scripts/, .claude/hooks/ or a compose.yaml and the session
# transcript has no Bash run of scripts/check.sh (or the unit tests / compose-lint.py) since the
# last Edit/Write of such a file, block the stop once and ask Claude to run scripts/check.sh.
# Never blocks twice in a row (stop_hook_active). Fails open: any error or missing input exits 0.
set -uo pipefail
trap 'exit 0' EXIT  # fail open: every path, including errors, exits 0
REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"

command -v jq >/dev/null || exit 0
input="$(cat)" || exit 0
[[ "$(jq -r '.stop_hook_active // false' <<<"$input" 2>/dev/null)" == false ]] || exit 0
transcript="$(jq -r '.transcript_path // empty' <<<"$input" 2>/dev/null)"
[[ -n "$transcript" && -f "$transcript" ]] || exit 0

changed="$(git -C "$REPO" status --porcelain --untracked-files=all -- \
  scripts .claude/hooks ':(glob)**/compose.yaml' 2>/dev/null)" || exit 0
[[ -n "$changed" ]] || exit 0

# One line per tool call, in order: "check" for a check run, "edit" for an edit of a watched path.
# Malformed transcript lines are skipped (fromjson?).
last="$(jq -rR --arg repo "$REPO/" '
  fromjson? | select(.type == "assistant") | .message.content[]?
  | select(type == "object" and .type == "tool_use")
  | if .name == "Bash" then
      (.input.command // "")
      | select(test("scripts/check\\.sh|unittest|compose-lint\\.py")) | "check"
    elif (.name | test("^(Edit|Write|MultiEdit|NotebookEdit)$")) then
      ((.input.file_path // .input.notebook_path // "") | ltrimstr($repo))
      | select(test("^(scripts/|\\.claude/hooks/)|(^|/)compose\\.yaml$")) | "edit"
    else empty end
' "$transcript" 2>/dev/null | tail -n 1)" || exit 0
[[ "$last" == check ]] && exit 0

files="$(cut -c4- <<<"$changed" | head -n 5 | paste -sd ' ' -)"
jq -n --arg files "$files" '{
  decision: "block",
  reason: ("stop-check: scripts/, .claude/hooks/ or compose.yaml changed (" + $files
    + ") and scripts/check.sh has not run since. Run scripts/check.sh and report its result"
    + " (or say why it cannot run), then stop.")
}'
exit 0
