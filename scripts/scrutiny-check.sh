#!/usr/bin/env bash
# Cron (daily 09:05, user dan): ntfy alert when Scrutiny (tools/scrutiny) reports a disk problem:
# any disk with device_status != 0 (failed by SMART and/or Scrutiny's thresholds), fewer than
# MIN_DISKS disks, a disk whose newest collection is older than MAX_DAYS, or the API not answering.
# Repeats daily until fixed. Scrutiny v0.9.5 can't ignore attributes per disk, so the one known
# exception (sda, see sda_known_ok) lives here.
# Logs to syslog (journalctl -t scrutiny-check).
# Install: scripts/install-cron.sh. `scripts/scrutiny-check.sh test` sends a test notification.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
MIN_DISKS=3
MAX_DAYS=3
SDA_WWN=0x5000cca583cdf8cb   # Hitachi OS disk (sda): 187 raw is a packed value, 188 old timeouts
SDA_MAX_188=1000             # stop accepting sda's status 2 once Command_Timeout reaches this

log() { logger -t scrutiny-check "$*"; [[ -t 1 ]] && echo "$*"; return 0; }
envval() {  # Read one key from the repo env file without printing anything else.
  sed -n "s/^[[:space:]]*$1=//p" "$REPO/.env" 2>/dev/null | tail -n1 | tr -d "\"'\r" | xargs
}
notify() {  # title, message. The topic is a secret: read here, never printed.
  local topic
  topic="$(envval NTFY_ALERT_TOPIC)"
  if [[ -z $topic ]]; then log "NTFY_ALERT_TOPIC not set: no notification"; return 1; fi
  curl -fs -m 10 -o /dev/null -H "Title: $1" -H "Priority: high" -H "Tags: floppy_disk,warning" \
    -d "$2" "http://localhost:8081/$topic" || { log "ntfy post failed"; return 1; }
}

if [[ ${1:-} == test ]]; then
  notify "Scrutiny check test" "Test message: disk health alerts work." && log "test notification sent"
  exit
fi

# Port 8084 is published on the LAN IP only, so localhost would not answer.
lan_ip="$(envval LAN_IP)"
base="http://${lan_ip:-192.168.0.210}:8084"
url="$base/api/summary"
if ! json="$(curl -fs -m 20 "$url")"; then
  log "API not answering: $url"
  notify "Scrutiny unreachable" "No answer from $url. Check: scripts/dc.sh tools/scrutiny ps"
  exit 1
fi

# sda: status 2 is accepted only while SMART passed (status exactly 2), only 187/188 fail,
# 188 stays below SDA_MAX_188 and sector counters 5, 196, 197, 198 are all 0. Anything else,
# including a failed details call or a missing attribute, still alerts.
sda_known_ok() {  # wwn, status, scrutiny_uuid
  [[ $1 == "$SDA_WWN" && $2 == 2 ]] || return 1
  curl -fs -m 20 "$base/api/device/$3/details" | jq -e --argjson max188 "$SDA_MAX_188" '
    .data.smart_results | max_by(.date) | .attrs
    | ([.["5"], .["196"], .["197"], .["198"] | .raw_value] | all(. == 0))
      and (.["188"].raw_value < $max188)
      and ([to_entries[] | select(.value.status != 0) | .key] - ["187", "188"] == [])
    ' >/dev/null 2>&1
}

# One line per active disk: name, device_status, collector_date as epoch (0 if missing),
# scrutiny_uuid, wwn.
if ! rows="$(jq -er '.data.summary[] | select(.device.archived | not)
    | [.device.device_name, .device.device_status,
       ((.smart.collector_date // "") | sub("\\.[0-9]+"; "")
        | if . == "" then 0 else fromdateiso8601 end),
       .device.scrutiny_uuid, .device.wwn]
    | @tsv' <<<"$json" 2>/dev/null)"; then
  log "unexpected /api/summary format"
  notify "Scrutiny check failed" "Unexpected /api/summary format from $url. Check the script."
  exit 1
fi

now=$(date +%s)
problems=()
count=0
accepted=""
while IFS=$'\t' read -r name status collected uuid wwn; do
  [[ -z $name ]] && continue
  count=$((count + 1))
  if (( status != 0 )); then
    if sda_known_ok "$wwn" "$status" "$uuid"; then
      accepted=" ($name: known 187/188 accepted)"
    else
      problems+=("$name: status $status (1 = SMART failed, 2 = Scrutiny failed)")
    fi
  fi
  if (( collected == 0 )); then
    problems+=("$name: no collection yet")
  elif (( now - collected > MAX_DAYS * 86400 )); then
    problems+=("$name: last collection $(( (now - collected) / 86400 )) days ago (limit $MAX_DAYS)")
  fi
done <<<"$rows"
(( count < MIN_DISKS )) && problems+=("only $count disks reported (expected $MIN_DISKS)")

if (( ${#problems[@]} )); then
  log "problems: $(IFS=';'; echo "${problems[*]}")"
  notify "Disk health warning" "$(printf '%s\n' "${problems[@]}")
Details: $base/"
  exit 1
fi
log "ok: $count disks passed$accepted, newest collections within $MAX_DAYS days"
