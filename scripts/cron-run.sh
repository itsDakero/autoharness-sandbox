#!/usr/bin/env bash
# Run one cron job with a timeout, log its output to syslog and report to its Uptime Kuma push monitor.
#   cron-run.sh <name> <timeout-secs> [--ok <codes>] <cmd> [args...]
# - Output goes to syslog (journalctl -t cron-<name>), then "exit <rc> in <s>s".
# - up when rc is 0 or in --ok (comma list, default "0"); down otherwise ("timed out after Ns" on rc 124/137).
# - Push: http://127.0.0.1:3001/api/push/<token>, token = KUMA_CRON_PUSH_SECRET (16 letters/digits) + <name> without
#   hyphens, padded with 0 / cut to 16 (Kuma wants exactly 32 alphanumerics). The secret is read from the repo's env
#   file, never printed or put on a command line. Kuma down or secret unset/invalid: log and carry on (job never blocked).
# - Throttle: push on a status change, or when 300 s have passed since the last push (every-minute jobs).
# - Exits with the job's own rc. Usage errors exit 2.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"

usage() { echo "usage: ${0##*/} <name> <timeout-secs> [--ok <codes>] <cmd> [args...]" >&2; exit 2; }
(( $# >= 3 )) || usage
name="$1"; secs="$2"; shift 2
okcodes="0"
if [[ ${1:-} == --ok ]]; then
  (( $# >= 3 )) || usage
  okcodes="$2"; shift 2
fi
[[ $name =~ ^[a-z0-9][a-z0-9-]*$ ]] || usage
[[ $secs =~ ^[0-9]+$ ]] || usage
[[ $okcodes =~ ^[0-9]+(,[0-9]+)*$ ]] || usage
(( $# >= 1 )) || usage

tag="cron-$name"
log() { logger -t "$tag" -- "$*" || true; }

out="$(mktemp)"
trap 'rm -f "$out"' EXIT

start=$(date +%s)
timeout --kill-after=30 "$secs" "$@" >"$out" 2>&1 </dev/null
rc=$?
dur=$(( $(date +%s) - start ))

while IFS= read -r l || [[ -n $l ]]; do log "$l"; done <"$out"
log "exit $rc in ${dur}s"

status=down
case ",$okcodes," in *",$rc,"*) status=up ;; esac
if [[ $status == up ]]; then
  msg="OK"
elif (( rc == 124 || rc == 137 )); then
  msg="timed out after ${secs}s"
else
  last="$(grep -v '^[[:space:]]*$' "$out" | tail -n1 | tr -c '[:print:]' ' ' || true)"
  msg="exit $rc${last:+: $last}"
  msg="${msg:0:150}"
fi

secret="$(sed -n 's/^[[:space:]]*KUMA_CRON_PUSH_SECRET=//p' "$REPO/.env" 2>/dev/null | tail -n1 | tr -d "\"'\r" | xargs || true)"
if [[ -z $secret ]]; then
  log "KUMA_CRON_PUSH_SECRET not set: no push"
  exit "$rc"
fi
if [[ ! $secret =~ ^[A-Za-z0-9]{16}$ ]]; then
  log "KUMA_CRON_PUSH_SECRET must be 16 letters/digits (openssl rand -hex 8): no push"
  exit "$rc"
fi
suffix="${name//-/}0000000000000000"
token="$secret${suffix:0:16}"

statedir="${XDG_STATE_HOME:-$HOME/.local/state}/homelab/cron-run"
state="$statedir/$name.last"
now=$(date +%s)
push=1
if [[ -r $state ]]; then
  read -r last_t last_s <"$state" || true
  if [[ ${last_t:-} =~ ^[0-9]+$ && ${last_s:-} == "$status" ]] && (( now - last_t < 300 )); then push=0; fi
fi

if (( push )); then
  if printf 'url = "http://127.0.0.1:3001/api/push/%s"\n' "$token" |
     curl -fsG -m 10 -o /dev/null -K - \
       --data-urlencode "status=$status" --data-urlencode "msg=$msg" --data-urlencode "ping=$((dur * 1000))"; then
    mkdir -p "$statedir" && echo "$now $status" >"$state"
  else
    log "kuma push failed"
  fi
fi
exit "$rc"
