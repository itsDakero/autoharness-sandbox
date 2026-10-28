#!/usr/bin/env bash
# Cron (Sundays 19:00, user dan): ask the fitness app for its weekly written summary and post it to Discord.
# The app does the work (/api/weekly-summary: 200 text = post; 204 no data; 409 already running; 502 bad model
# reply; 503 Mac mini down). Anything but 200 with a body: a syslog line only (journalctl -t fitness-weekly),
# no Discord post, no retry. Always exits 0.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
URL="http://127.0.0.1:8086/api/weekly-summary"

log() { logger -t fitness-weekly "$*"; [[ -t 1 ]] && echo "$*"; return 0; }

tmp="$(mktemp)" || { log "mktemp failed"; exit 0; }
trap 'rm -f "$tmp"' EXIT

code="$(curl -s -m 300 -X POST -o "$tmp" -w '%{http_code}' "$URL" 2>/dev/null)" || code=000
case "$code" in
  200)
    body="$(cat "$tmp")"
    if [[ -z $body ]]; then log "empty 200 body: no post"; exit 0; fi
    "$REPO/scripts/discord.sh" "$body"$'\n'"Insights: http://192.168.0.210:8086/insights" >/dev/null 2>&1 \
      || log "discord post failed"
    ;;
  *) log "fitness app answered $code: no post" ;;
esac
exit 0
