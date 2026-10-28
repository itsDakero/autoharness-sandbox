#!/usr/bin/env bash
# Cron (daily 09:10, user dan): ntfy alert when a disk fills up. df only: no root, no container.
#   /mnt/media          >= 70%  (default priority): time to build storage cleanup part B
#   /, /mnt/backup      >= 85%  (high); /srv/homelab too when it is its own mount
#   any of them         >= 95%  (high, crit; sent instead of the warn alert)
# Warn repeats at most weekly per disk, crit daily. State: one line per alert, "<mount> <level> <epoch>",
# in /srv/homelab/disk-space-check/state; a disk below its threshold loses its line.
# Logs to syslog (journalctl -t disk-space-check). Install: scripts/install-cron.sh.
# `scripts/disk-space-check.sh test` sends a test notification.
# Test overrides (shell env, not .env): DISK_CHECK_MEDIA_PCT, DISK_CHECK_SYSTEM_PCT, DISK_CHECK_CRIT_PCT,
# DISK_CHECK_STATE.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
MEDIA_PCT="${DISK_CHECK_MEDIA_PCT:-70}"
SYSTEM_PCT="${DISK_CHECK_SYSTEM_PCT:-85}"
CRIT_PCT="${DISK_CHECK_CRIT_PCT:-95}"
STATE="${DISK_CHECK_STATE:-/srv/homelab/disk-space-check/state}"
WARN_REPEAT=$(( 7 * 86400 - 3600 ))
CRIT_REPEAT=0   # crit is sent on every run (cron: daily)

log() { logger -t disk-space-check "$*"; [[ -t 1 ]] && echo "$*"; return 0; }
notify() {  # title, message, priority. The topic is a secret: read here, never printed.
  local topic
  topic="$(sed -n 's/^[[:space:]]*NTFY_ALERT_TOPIC=//p' "$REPO/.env" 2>/dev/null | tail -n1 | tr -d "\"'\r" | xargs)"
  if [[ -z $topic ]]; then log "NTFY_ALERT_TOPIC not set: no notification"; return 1; fi
  curl -fs -m 10 -o /dev/null -H "Title: $1" -H "Priority: $3" -H "Tags: floppy_disk,warning" -d "$2" \
    "http://localhost:8081/$topic" || { log "ntfy post failed"; return 1; }
}

if [[ ${1:-} == test ]]; then
  notify "Disk space check test" "Test message: disk space alerts work." default && log "test notification sent"
  exit
fi

# Disks: "<mount> <warn threshold> <label>"
disks=("/ $SYSTEM_PCT system" "/mnt/media $MEDIA_PCT media" "/mnt/backup $SYSTEM_PCT backup")
srv="$(findmnt -n -o TARGET --target /srv/homelab 2>/dev/null || true)"
if [[ -n $srv && $srv != / ]]; then disks+=("/srv/homelab $SYSTEM_PCT srv"); fi

# State: tolerate a missing or corrupt file (bad lines are ignored).
declare -A last   # "<mount> <level>" -> epoch
declare -A keep   # lines to write back, same key
if [[ -r $STATE ]]; then
  while read -r m l t extra; do
    [[ -n ${m:-} && ${l:-} =~ ^(warn|crit)$ && ${t:-} =~ ^[0-9]+$ && -z ${extra:-} ]] && last["$m $l"]=$t
  done < "$STATE"
fi

now="$(date +%s)"
rc=0
for d in "${disks[@]}"; do
  read -r mnt warn label <<< "$d"
  if [[ $mnt != / ]] && ! mountpoint -q "$mnt"; then
    log "not mounted $mnt: skipped"
    continue   # state kept: an unmounted disk says nothing about its fill
  fi
  raw="$(df --output=pcent "$mnt" 2>/dev/null | tail -n1 | tr -d ' %')"
  if [[ ! $raw =~ ^[0-9]+$ ]]; then
    log "df gave no usable percentage for $mnt (got '${raw}'): skipped"
    rc=1
    [[ -n ${last["$mnt warn"]:-} ]] && keep["$mnt warn"]=${last["$mnt warn"]}
    [[ -n ${last["$mnt crit"]:-} ]] && keep["$mnt crit"]=${last["$mnt crit"]}
    continue
  fi
  pct=$((10#$raw))

  if (( pct >= CRIT_PCT )); then
    level=crit; repeat=$CRIT_REPEAT; prio=high
    title="Disk almost full: $mnt at $pct%"
    msg="$mnt is at $pct% (limit $CRIT_PCT%). Free space now."
  elif (( pct >= warn )); then
    level=warn; repeat=$WARN_REPEAT
    if [[ $label == media ]]; then
      prio=default; title="Media disk at $pct%"
      msg="media disk at $pct%: time to build storage cleanup part B (docs/m2-media.md, Watched-media cleanup report)"
    else
      prio=high; title="Disk filling: $mnt at $pct%"
      msg="$mnt is at $pct% (limit $warn%). Check what is using the space."
    fi
  else
    log "ok $mnt $pct%"
    continue   # below threshold: no keep entry, so the next crossing alerts at once
  fi

  prev="${last["$mnt $level"]:-}"
  if [[ -n $prev ]] && (( now - prev < repeat )) && (( now >= prev )); then
    log "suppressed $level $mnt $pct% (last sent $(( (now - prev) / 3600 ))h ago)"
    keep["$mnt $level"]=$prev
    continue
  fi
  if notify "$title" "$msg" "$prio"; then
    log "alert $level $mnt $pct%"
    keep["$mnt $level"]=$now
  else
    log "alert $level $mnt $pct% NOT sent"
    rc=1
    [[ -n $prev ]] && keep["$mnt $level"]=$prev
  fi
done

# Write state via temp file + mv.
if ! mkdir -p "$(dirname "$STATE")" 2>/dev/null; then log "cannot create $(dirname "$STATE")"; exit 1; fi
tmp="$(mktemp "$STATE.XXXXXX" 2>/dev/null)" || { log "cannot write state $STATE"; exit 1; }
for k in "${!keep[@]}"; do echo "$k ${keep[$k]}"; done | sort > "$tmp"
mv -f "$tmp" "$STATE" || { log "cannot move state into place"; rm -f "$tmp"; exit 1; }
exit $rc
