#!/usr/bin/env bash
# Cron wrapper for the LMS picker (tools/lms): lms-job.sh <odds|alerts|results>
# Runs the job inside the container; non-empty stdout is the Discord message, stderr goes to syslog
# (journalctl -t lms-job). Exits with the job's rc. A second run while one is active exits 0 quietly.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
job="${1:-}"
case "$job" in
  odds|alerts|results) ;;
  *) echo "usage: ${0##*/} <odds|alerts|results>" >&2; exit 2 ;;
esac

state="$HOME/.local/state/homelab/lms"
mkdir -p "$state"
exec 9>"$state/lms.lock"
flock -n 9 || exit 0

out="$(mktemp)"; err="$(mktemp)"
trap 'rm -f "$out" "$err"' EXIT
"$REPO/scripts/dc.sh" tools/lms exec -T lms timeout 240 python -m app.jobs "$job" >"$out" 2>"$err"
rc=$?
if [[ -s $err ]]; then logger -t lms-job -f "$err"; fi
if [[ -s $out ]]; then
  "$REPO/scripts/discord.sh" "$(cat "$out")" >/dev/null 2>&1 || logger -t lms-job "discord post failed"
fi
exit "$rc"
