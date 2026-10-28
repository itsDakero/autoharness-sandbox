#!/usr/bin/env bash
# Monthly restore drill: proves a restic restore works. Run as root by homelab-restore-drill.service
# (timer: the 1st of each month, 10:00); failures trigger homelab-restore-drill-failure.service, which runs
# `restore-drill.sh notify-failure` (ntfy). Root because the restic repo and its password are root-only
# (same repo/password/cache as backup.sh), so this is a systemd job, not a cron.d job.
# Picks one service's appdata folder from DRILL (rotates by month), takes the newest `nightly` snapshot that
# holds /srv/homelab, restores that folder into a fresh temp dir with `restic restore --verify`, then checks
# the restored files against the snapshot listing (same file count and bytes, at least one non-empty file).
# Fails when the snapshot is older than MAX_AGE_H. Cleans up the temp dir in every case.
# One Discord line either way (scripts/discord.sh); exit 1 on failure, so systemd's OnFailure sends ntfy.
#   restore-drill.sh                 this month's folder
#   restore-drill.sh <folder>        a folder under /srv/homelab instead, e.g. `seerr/config`
#   restore-drill.sh test-alert      ntfy test (no root needed)
#   restore-drill.sh notify-failure  ntfy with the last journal lines (homelab-restore-drill-failure.service)
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
export RESTIC_REPOSITORY=/mnt/backup/restic RESTIC_PASSWORD_FILE=/etc/restic/password
export RESTIC_CACHE_DIR=/var/cache/restic  # systemd gives root no $HOME
APPDATA=/srv/homelab
TMP_PARENT=/var/tmp  # on disk, not tmpfs; jellyfin/config is ~900 MB
MAX_AGE_H=48
# One folder per month (January = first). Folders as in docs/restore-runbook.md, step 1.
DRILL=(radarr sonarr prowlarr seerr/config jellyfin/config uptime-kuma dashboard fitness books wardrobe mealie paperless)
tmp=""

log() { echo "$*"; }
notify() {  # title, message. The topic is a secret: read here, never printed.
  local topic
  topic="$(sed -n 's/^[[:space:]]*NTFY_ALERT_TOPIC=//p' "$REPO/.env" 2>/dev/null | tail -n1 | tr -d "\"'\r" | xargs)"
  if [[ -z $topic ]]; then log "NTFY_ALERT_TOPIC not set: no notification"; return 1; fi
  curl -fs -m 10 -o /dev/null -H "Title: $1" -H "Priority: high" -H "Tags: floppy_disk,warning" -d "$2" \
    "http://localhost:8081/$topic" || { log "ntfy post failed"; return 1; }
}
cleanup() { [[ -n $tmp && -d $tmp ]] && rm -rf -- "$tmp"; return 0; }
fail() {  # Discord line, then exit 1 (OnFailure sends ntfy)
  log "FAILED: $*"
  "$REPO/scripts/discord.sh" "Restore drill FAILED: ${folder:-?}: $*" >/dev/null || log "discord post failed"
  exit 1
}

case ${1:-} in
  test-alert)
    notify "Restore drill alert test" "Test message: homelab restore drill alerts work." && log "test alert sent"
    exit ;;
  notify-failure)
    notify "Homelab restore drill FAILED" "$(journalctl -u homelab-restore-drill.service -n 15 --no-pager -o cat 2>/dev/null)
Check: journalctl -u homelab-restore-drill -n 50"
    exit ;;
  "") folder=${DRILL[$(( (10#$(date +%m) - 1) % ${#DRILL[@]} ))]} ;;
  -*) echo "usage: $0 [<folder under $APPDATA>|test-alert|notify-failure]" >&2; exit 2 ;;
  *) folder=${1%/} ;;
esac
[[ $folder =~ ^[a-z0-9][a-z0-9_-]*(/[a-z0-9][a-z0-9_-]*)*$ ]] || { echo "bad folder: $folder" >&2; exit 2; }
src=$APPDATA/$folder

(( EUID == 0 )) || fail "run as root (homelab-restore-drill.service)"
mountpoint -q /mnt/backup || fail "/mnt/backup is not mounted"
# Share the backup jobs' lock: never restore while a backup or prune runs. Wait for it instead of skipping.
exec 9>/run/homelab-backup.lock
flock -w 7200 9 || fail "backup lock still held after 2h"

# Newest nightly snapshot holding /srv/homelab: "<id> <short_id> <age in hours>"
snap="$(restic snapshots --json --tag nightly 2>/dev/null | python3 -c '
import json, re, sys, time
from datetime import datetime
snaps = [s for s in json.load(sys.stdin) or [] if sys.argv[1] in s.get("paths", [])]
if not snaps:
    sys.exit(1)
def ts(s):  # RFC 3339 with nanoseconds; fromisoformat wants at most 6 digits
    return datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", s["time"])).timestamp()
s = max(snaps, key=ts)
print(s["id"], s["short_id"], int((time.time() - ts(s)) // 3600))
' "$APPDATA")" || fail "no nightly snapshot of $APPDATA (or restic snapshots failed)"
read -r snap_id snap_short age_h <<<"$snap"
log "snapshot $snap_short, ${age_h}h old; folder $folder"

# What the snapshot holds under the folder: "<files> <bytes>"
want="$(restic ls --json --recursive "$snap_id" "$src" 2>/dev/null | python3 -c '
import json, sys
n = b = 0
for line in sys.stdin:
    try:
        e = json.loads(line)
    except ValueError:
        continue
    if e.get("type") == "file" and e.get("path", "").startswith(sys.argv[1] + "/"):
        n += 1; b += e.get("size", 0)
print(n, b)
' "$src")" || fail "restic ls failed"
read -r want_files want_bytes <<<"$want"
(( want_files > 0 && want_bytes > 0 )) || fail "snapshot $snap_short has no files under $src"

avail=$(( $(df --output=avail -B1 "$TMP_PARENT" | tail -n1) ))
(( avail > want_bytes + 1024**3 )) || fail "not enough space in $TMP_PARENT for $(( want_bytes / 1024**2 )) MB"

tmp="$(mktemp -d "$TMP_PARENT/restore-drill.XXXXXX")" || fail "mktemp failed"
trap cleanup EXIT
start=$(date +%s)
restic restore "$snap_id" --target "$tmp" --include "$src" --verify >/dev/null \
  || fail "restic restore --verify failed (snapshot $snap_short)"
dur=$(( $(date +%s) - start ))

out=$tmp$src
[[ -d $out ]] || fail "restored folder missing: $src"
got_files=$(find "$out" -type f | wc -l)
got_bytes=$(find "$out" -type f -printf '%s\n' | awk '{ b += $1 } END { print b + 0 }')
nonempty=$(find "$out" -type f -size +0c | head -n1)
[[ -n $nonempty ]] || fail "every restored file is empty"
(( got_files == want_files )) || fail "restored $got_files files, snapshot has $want_files"
(( got_bytes == want_bytes )) || fail "restored $got_bytes bytes, snapshot has $want_bytes"
cleanup; tmp=""

(( age_h < MAX_AGE_H )) || fail "restore OK but snapshot $snap_short is ${age_h}h old (max ${MAX_AGE_H}h): is the nightly backup running?"

mb=$(awk -v b="$want_bytes" 'BEGIN { printf "%.1f", b / 1048576 }')
line="Restore drill OK: $folder from snapshot $snap_short (${age_h}h old): $got_files files, $mb MB restored and verified in ${dur}s"
log "$line"
"$REPO/scripts/discord.sh" "$line" >/dev/null || log "discord post failed"
exit 0
