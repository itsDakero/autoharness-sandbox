#!/usr/bin/env bash
# Cron (daily 09:00, user dan): ntfy alert when Home Assistant's backups on the SMB share (core/ha-backups)
# go stale, i.e. the newest file in /srv/homelab/ha-backups is older than MAX_DAYS, or there is none.
# Repeats daily until a fresh backup lands. Separate from backup.sh on purpose: a stale HA backup is not a
# failed server backup, and must not block the B2 copy. Logs to syslog (journalctl -t ha-backup-check).
# Install: scripts/install-cron.sh. `scripts/ha-backup-check.sh test` sends a test notification.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DIR=/srv/homelab/ha-backups
MAX_DAYS=9

log() { logger -t ha-backup-check "$*"; [[ -t 1 ]] && echo "$*"; return 0; }
notify() {  # title, message. The topic is a secret: read here, never printed.
  local topic
  topic="$(sed -n 's/^[[:space:]]*NTFY_ALERT_TOPIC=//p' "$REPO/.env" 2>/dev/null | tail -n1 | tr -d "\"'\r" | xargs)"
  if [[ -z $topic ]]; then log "NTFY_ALERT_TOPIC not set: no notification"; return 1; fi
  curl -fs -m 10 -o /dev/null -H "Title: $1" -H "Priority: high" -H "Tags: house,warning" -d "$2" \
    "http://localhost:8081/$topic" || { log "ntfy post failed"; return 1; }
}

if [[ ${1:-} == test ]]; then
  notify "HA backup check test" "Test message: Home Assistant backup alerts work." && log "test notification sent"
  exit
fi

if [[ ! -d $DIR ]]; then
  log "$DIR missing"
  notify "HA backups missing" "$DIR does not exist on the server. Check: scripts/dc.sh core/ha-backups ps"
  exit 1
fi

newest="$(find "$DIR" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -n1)"
if [[ -z $newest ]]; then
  log "no files in $DIR"
  notify "HA backups stale" "No Home Assistant backups in $DIR. Check HA > Settings > System > Backups."
  exit 1
fi

age=$(( $(date +%s) - ${newest%%.*} ))
age_days=$(( age / 86400 ))
file="${newest#* }"
if (( age > MAX_DAYS * 86400 )); then
  log "stale: newest ${file##*/} is $age_days days old"
  notify "HA backups stale" "Newest Home Assistant backup is $age_days days old (limit $MAX_DAYS): ${file##*/}
Check HA > Settings > System > Backups, and: scripts/dc.sh core/ha-backups logs --tail 50"
  exit 1
fi
log "ok: newest ${file##*/} is $age_days days old"
