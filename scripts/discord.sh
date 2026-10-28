#!/usr/bin/env bash
# Post one line (or a few) to the homelab Discord feed: the non-urgent channel (ntfy stays for urgent alerts).
# Used by the agent loop ("build ready", "parked") and deploy-idea.sh ("deploy done"); the dashboard posts
# "idea queued" itself. Logs to syslog (journalctl -t discord).
#   scripts/discord.sh "<message>"
#   scripts/discord.sh test
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"

log() { logger -t discord "$*"; [[ -t 1 ]] && echo "$*"; return 0; }

msg="${1:-}"
[[ $msg == test ]] && msg="Homelab test message: the Discord feed works."
if [[ -z $msg ]]; then echo "usage: $0 <message> | test" >&2; exit 2; fi

# The webhook URL is a secret: read here, never printed or put on a command line (curl reads it from stdin).
url="$(sed -n 's/^[[:space:]]*DISCORD_WEBHOOK_URL=//p' "$REPO/.env" 2>/dev/null | tail -n1 | tr -d "\"'\r" | xargs)"
if [[ $url != https://discord.com/api/webhooks/* && $url != https://discordapp.com/api/webhooks/* ]]; then
  log "DISCORD_WEBHOOK_URL not set or not a Discord webhook: no post"
  exit 1
fi

# Discord's limit is 2000 characters. No pings: idea titles etc. could contain @everyone.
body="$(python3 -c 'import json, sys; print(json.dumps({"content": sys.argv[1][:1990], "allowed_mentions": {"parse": []}}))' "$msg")"
if printf 'url = "%s"\n' "$url" | curl -fs -m 10 -o /dev/null -K - -H "Content-Type: application/json" -d "$body"; then
  log "posted: ${msg%%$'\n'*}"
else
  log "post failed"
  exit 1
fi
