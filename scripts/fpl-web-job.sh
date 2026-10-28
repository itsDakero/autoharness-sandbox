#!/usr/bin/env bash
# Cron wrapper for the FPL page's jobs (tools/fpl): fpl-web-job.sh <solve|deadline|teams|players>
# Runs the job inside the container; non-empty stdout is the Discord message (the deadline line),
# stderr goes to syslog (journalctl -t fpl-web-job). Exits with the job's rc.
# A second run while one is active exits 0 quietly.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
job="${1:-}"
case "$job" in
  solve|deadline|teams|players) ;;
  *) echo "usage: ${0##*/} <solve|deadline|teams|players>" >&2; exit 2 ;;
esac

state="$HOME/.local/state/homelab/fpl"
mkdir -p "$state"
exec 9>"$state/web-$job.lock"
flock -n 9 || exit 0

out="$(mktemp)"; err="$(mktemp)"
trap 'rm -f "$out" "$err"' EXIT
"$REPO/scripts/dc.sh" tools/fpl exec -T fpl timeout 1500 python -m web.jobs "$job" >"$out" 2>"$err"
rc=$?
if [[ -s $err ]]; then logger -t fpl-web-job -f "$err"; fi
if [[ -s $out ]]; then
  "$REPO/scripts/discord.sh" "$(cat "$out")" >/dev/null 2>&1 || logger -t fpl-web-job "discord post failed"
fi
exit "$rc"
