#!/usr/bin/env bash
# Nightly restic backup to the local backup disk (M4 stage A). Run as root by homelab-backup.service
# (timer 04:00); failures trigger homelab-backup-failure.service, which runs `backup.sh notify-failure`.
# Backs up the repo (incl. .env) and /srv/homelab (app configs + keep/), excludes caches and logs
# (scripts/backup-excludes.txt). It also backs up an allow-list of Dan's /home/dan/.claude (settings, skills,
# memory, plugin config; never credentials or transcripts). Containers with SQLite state (incl. fitness, hermes, books and
# wardrobe) are paused for the backup itself, so the
# files are one crash-consistent point; they are unpaused even if it fails, and autokuma is restarted after
# the unpause so it logs in to Uptime Kuma again.
# `backup.sh offsite` (M4 stage B) copies the local nightly snapshots to Backblaze B2. Run as root by
# homelab-backup-offsite.service, which systemd starts only after the local backup succeeds; failures
# trigger homelab-backup-offsite-failure.service (`notify-failure homelab-backup-offsite`).
# `scripts/backup.sh test-alert` (no root needed) sends a test ntfy message.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_REPO=/mnt/backup/restic
B2_REPO=b2:dan-homelab-restic-x7k2:homelab
B2_ENV=/etc/restic/b2.env  # B2_ACCOUNT_ID, B2_ACCOUNT_KEY; root-only, never printed
export RESTIC_REPOSITORY=$LOCAL_REPO RESTIC_PASSWORD_FILE=/etc/restic/password
export RESTIC_CACHE_DIR=/var/cache/restic  # systemd gives root no $HOME, so restic had no cache
SOURCES=("$REPO" /srv/homelab)
# Allow-list of Dan's Claude Code config. Absolute paths (root has no $HOME). A missing path is skipped:
# restic fails on a missing source. Credentials and transcripts are not listed (and are excluded too).
CLAUDE_HOME=/home/dan/.claude
shopt -s nullglob
for p in "$CLAUDE_HOME/settings.json" "$CLAUDE_HOME/skills" "$CLAUDE_HOME"/projects/*/memory \
         "$CLAUDE_HOME/plugins/known_marketplaces.json" "$CLAUDE_HOME/plugins/synced" "$CLAUDE_HOME/plugins/data"; do
  [[ -e $p ]] && SOURCES+=("$p")
done
shopt -u nullglob
PAUSE=(radarr radarr-remote sonarr sonarr-remote prowlarr jellyfin seerr uptime-kuma autokuma ntfy fitness hermes books wardrobe)
KEEP=(--keep-daily 7 --keep-weekly 4 --keep-monthly 6)
paused=()

log() { echo "$*"; }
fail() { log "FAILED: $*"; exit 1; }
notify() {  # title, message. The topic is a secret: read here, never printed.
  local topic
  topic="$(sed -n 's/^[[:space:]]*NTFY_ALERT_TOPIC=//p' "$REPO/.env" 2>/dev/null | tail -n1 | tr -d "\"'\r" | xargs)"
  if [[ -z $topic ]]; then log "NTFY_ALERT_TOPIC not set: no notification"; return 1; fi
  curl -fs -m 10 -o /dev/null -H "Title: $1" -H "Priority: high" -H "Tags: floppy_disk,warning" -d "$2" \
    "http://localhost:8081/$topic" || { log "ntfy post failed"; return 1; }
}
unpause() {
  local c restart_ak=0
  for c in "${paused[@]}"; do
    docker unpause "$c" >/dev/null || log "WARNING: could not unpause $c"
    [[ $c == autokuma ]] && restart_ak=1
  done
  (( ${#paused[@]} )) && log "unpaused: ${paused[*]}"
  paused=()
  if (( restart_ak )); then  # AutoKuma loses its Uptime Kuma session while paused; restart to log in again
    sleep 15                 # give uptime-kuma time to come back first
    if docker restart autokuma >/dev/null; then log "restarted autokuma"
    else log "WARNING: could not restart autokuma"; fi
  fi
  return 0
}
preflight() {  # root, backup disk, one backup job at a time (local and off-site share the lock)
  (( EUID == 0 )) || fail "run as root (homelab-backup*.service)"
  mountpoint -q /mnt/backup || fail "/mnt/backup is not mounted"
  exec 9>/run/homelab-backup.lock
  flock -n 9 || fail "another backup is running"
}

offsite() {
  preflight
  [[ -s $B2_ENV ]] || fail "$B2_ENV missing"
  set -a
  # root-only /etc/restic/b2.env, not in the repo
  # shellcheck source=/dev/null
  . "$B2_ENV"
  set +a
  export RESTIC_REPOSITORY=$B2_REPO
  # Copies every local nightly snapshot B2 doesn't have yet: normally just tonight's, more after a missed run.
  restic copy --from-repo "$LOCAL_REPO" --from-password-file "$RESTIC_PASSWORD_FILE" --tag nightly \
    || fail "restic copy to B2"
  restic forget --tag nightly "${KEEP[@]}" || fail "restic forget (B2)"
  if [[ $(date +%u) == 7 ]]; then  # Sundays: prune and read 1/12 of the data, a different 12th each week
    restic prune || fail "restic prune (B2)"
    restic check --with-cache --read-data-subset="$(( 10#$(date +%V) % 12 + 1 ))/12" || fail "restic check (B2)"
  fi
  log "off-site copy done"
}

case ${1:-} in
  test-alert)
    notify "Backup alert test" "Test message: homelab backup alerts work." && log "test alert sent"
    exit ;;
  notify-failure)
    unit=${2:-homelab-backup}
    title="Homelab backup FAILED"
    [[ $unit == homelab-backup-offsite ]] && title="Homelab off-site backup FAILED"
    notify "$title" "$(journalctl -u "$unit.service" -n 15 --no-pager -o cat 2>/dev/null)
Check: journalctl -u $unit -n 50"
    exit ;;
  offsite) offsite; exit ;;
  "") ;;
  *) echo "usage: $0 [offsite|test-alert|notify-failure [unit]]" >&2; exit 2 ;;
esac

preflight

trap unpause EXIT
for c in "${PAUSE[@]}"; do
  if [[ $(docker inspect --format '{{.State.Status}}' "$c" 2>/dev/null) == running ]]; then
    docker pause "$c" >/dev/null && paused+=("$c")
  fi
done
log "paused: ${paused[*]:-none}"

restic backup --tag nightly --exclude-file "$REPO/scripts/backup-excludes.txt" --exclude-caches \
  --one-file-system "${SOURCES[@]}"
rc=$?
unpause
(( rc == 0 )) || fail "restic backup exit $rc (3 = some files unreadable, snapshot incomplete)"

restic forget --tag nightly "${KEEP[@]}" --prune || fail "restic forget/prune"
if [[ $(date +%u) == 7 ]]; then
  restic check || fail "restic check"
fi
log "backup done"
