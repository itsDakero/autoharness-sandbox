#!/usr/bin/env bash
# Start or attach to the build loop's tmux session `ideas`.
# A new session runs: HOMELAB_LOOP=1 CLAUDE_CODE_AUTO_COMPACT_WINDOW=150000 claude
# Then type: /loop /build-ideas
# The compact window applies only to a newly started session; an existing one is just attached.
# Optional override: LOOP_COMPACT_WINDOW=<100000..1000000> (default 150000).
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
window="${LOOP_COMPACT_WINDOW:-150000}"

if ! [[ "$window" =~ ^[0-9]+$ ]] || [ "${#window}" -gt 7 ] || [ "$window" -lt 100000 ] || [ "$window" -gt 1000000 ]; then
  echo "loop.sh: LOOP_COMPACT_WINDOW must be an integer from 100000 to 1000000 (got '$window')" >&2
  exit 1
fi
for c in tmux claude; do
  command -v "$c" >/dev/null 2>&1 || { echo "loop.sh: $c not found" >&2; exit 1; }
done

attach_session() {
  if [ -n "${TMUX:-}" ]; then
    tmux switch-client -t =ideas
  else
    tmux attach -t =ideas
  fi
}

if tmux has-session -t =ideas 2>/dev/null; then
  echo "session 'ideas' already exists; the compact window applies only to a new session. To restart: quit claude in it, \`tmux kill-session -t ideas\`, then rerun scripts/loop.sh" >&2
  attach_session
  exit 0
fi

tmux new-session -d -s ideas -c "$repo" "env HOMELAB_LOOP=1 CLAUDE_CODE_AUTO_COMPACT_WINDOW=$window claude; exec bash"
echo "type: /loop /build-ideas"
attach_session
