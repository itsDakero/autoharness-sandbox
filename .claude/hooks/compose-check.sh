#!/usr/bin/env bash
# PostToolUse: after an edit to */compose.yaml, validate it and re-check the whole file
# (pinned images, no docker.sock), then run scripts/compose-lint.py on it (that file's findings
# plus repo-wide port uniqueness). Exit 2 sends the problems back to Claude.
# Read-write media mounts aren't checked here: guard.py asks the user before they're written.
# Interpolated config is only parsed here, never printed (it contains .env values).
# Fails open: no .env/docker skips the config checks, no PyYAML/lint script skips the lint (warning).
set -uo pipefail
REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
file="$(jq -r '.tool_input.file_path // .tool_input.notebook_path // empty')"
[[ "$(basename -- "$file")" == compose.yaml ]] || exit 0
case "$file" in "$REPO"/*) ;; /*) exit 0 ;; *) file="$REPO/$file" ;; esac
[[ -f "$file" ]] || exit 0
dir="$(dirname -- "${file#"$REPO"/}")"

problems=""
if [[ ! -f "$REPO/.env" ]] || ! command -v docker >/dev/null; then
  echo "compose-check: warning: no .env or docker, skipped config -q and the image/docker.sock check" >&2
else
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
fi

# Lint against the checkout the file lives in, so a worktree copy isn't a port clash with main.
root="$REPO"
[[ "$dir" =~ ^(\.worktrees/[^/]+)/ ]] && root="$REPO/${BASH_REMATCH[1]}"
lint="$REPO/scripts/compose-lint.py"
if [[ ! -f "$lint" ]]; then
  echo "compose-check: warning: scripts/compose-lint.py missing, lint skipped" >&2
elif ! python3 -c 'import yaml' 2>/dev/null; then
  echo "compose-check: warning: PyYAML missing (apt install python3-yaml), lint skipped" >&2
else
  findings="$(timeout 20 python3 "$lint" --root "$root" "$file" 2>&1)"
  case $? in
    0) ;;
    1) problems="${problems:+$problems$'\n'}$findings" ;;
    *) echo "compose-check: warning: compose-lint.py failed, lint skipped: $findings" >&2 ;;
  esac
fi

if [[ -n "$problems" ]]; then
  echo "compose-check: $dir/compose.yaml" >&2
  echo "$problems" >&2
  exit 2
fi
exit 0
