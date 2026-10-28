#!/usr/bin/env bash
# Cron wrapper for one FPL collector pull: fpl-job.sh <job> <fail-threshold> <limit-secs>
# Runs the job inside the fpl container (timeout kills the process in there too). Failures below the
# threshold exit 0 (the Kuma push monitor stays up, no alert spam from a 2-hourly job); at the threshold
# one Discord line and exit 1; above it exit 1 with no new post. A success resets the count.
# Count: ~/.local/state/homelab/fpl/<job>.fails. Syslog tag fpl-job.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
if [[ ${1:-} == --help ]]; then
  echo "usage: ${0##*/} <job> <fail-threshold> <limit-secs>"
  exit 0
fi
if [[ $# -ne 3 ]]; then
  echo "usage: ${0##*/} <job> <fail-threshold> <limit-secs>" >&2
  exit 2
fi
job="$1"; thr="$2"; limit="$3"
[[ $job =~ ^[a-z-]+$ && $thr =~ ^[0-9]+$ && $limit =~ ^[0-9]+$ ]] || { echo "bad arguments" >&2; exit 2; }
dir="$HOME/.local/state/homelab/fpl"
mkdir -p "$dir"
cf="$dir/$job.fails"

out="$("$REPO/scripts/dc.sh" tools/fpl exec -T fpl timeout "$limit" python -m collector "$job" 2>&1)"
rc=$?
last="$(printf '%s\n' "$out" | awk 'NF{l=$0} END{print l}' | cut -c1-300)"

if (( rc == 0 )); then
  logger -t fpl-job "$job ok: $last"
  echo "$out"
  rm -f "$cf"
  exit 0
fi

n=0
[[ -f $cf ]] && n="$(cat "$cf" 2>/dev/null)"
[[ $n =~ ^[0-9]+$ ]] || n=0
n=$((n + 1))
echo "$n" > "$cf"
(( rc == 124 )) && last="timed out after ${limit}s"
logger -t fpl-job "$job failed (rc $rc) $n/$thr: $last"
if (( n < thr )); then
  echo "failure $n/$thr: $last"
  exit 0
elif (( n == thr )); then
  "$REPO/scripts/discord.sh" "FPL collector: $job failed $n times in a row: $last" >/dev/null 2>&1 \
    || logger -t fpl-job "discord post failed"
  echo "failure $n/$thr: $last"
  exit 1
fi
echo "failure $n (threshold $thr, already reported): $last"
exit 1
