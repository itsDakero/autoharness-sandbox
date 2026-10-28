#!/usr/bin/env bash
# PostToolUse: after an edit to */compose.yaml, validate it and re-check the whole file
# (pinned images, no docker.sock). Exit 2 sends the problem back to Claude.
# Read-write media mounts aren't checked here: guard.py asks the user before they're written.
# Interpolated config is only parsed here, never printed (it contains .env values).
set -uo pipefail
REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
file="$(jq -r '.tool_input.file_path // .tool_input.notebook_path // empty')"
[[ "$(basename -- "$file")" == compose.yaml ]] || exit 0
case "$file" in "$REPO"/*) ;; /*) exit 0 ;; *) file="$REPO/$file" ;; esac
dir="$(dirname -- "${file#"$REPO"/}")"

if ! err="$("$REPO/scripts/dc.sh" "$dir" config -q 2>&1)"; then
  echo "compose-check: scripts/dc.sh $dir config -q failed:" >&2
  echo "$err" >&2
  exit 2
fi

problems="$("$REPO/scripts/dc.sh" "$dir" config --format json 2>/dev/null | python3 -c '
import json, sys
allow_sock = sys.argv[1] == "core/docker-socket-proxy"
cfg = json.load(sys.stdin)
for name, svc in (cfg.get("services") or {}).items():
    img = svc.get("image", "")
    last = img.rsplit("/", 1)[-1]
    if img and "@" not in img and (":" not in last or last.endswith(":latest")):
        print(f"{name}: image {img} is not pinned (no :latest, no missing tag)")
    for v in svc.get("volumes") or []:
        src = v.get("source") or ""
        if "docker.sock" in src and not allow_sock:
            print(f"{name}: mounts docker.sock; use DOCKER_HOST=tcp://docker-socket-proxy:2375")
' "$dir")"
if [[ -n "$problems" ]]; then
  echo "compose-check: $dir/compose.yaml" >&2
  echo "$problems" >&2
  exit 2
fi
exit 0
