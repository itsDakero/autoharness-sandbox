#!/usr/bin/env bash
# Cron watchdog (every minute, user dan): restart qbittorrent when it has lost Gluetun's network
# namespace (Gluetun restarted outside compose), or start it when a compose up left it stuck in
# "created"; then post a normal-priority ntfy message.
# Never touches Gluetun; does nothing while either container is stopped on purpose or Gluetun isn't
# healthy yet. Logs to syslog (journalctl -t qbit-watchdog). Install: scripts/install-cron.sh
# `scripts/qbit-watchdog.sh test` sends a test notification.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
STATE="${XDG_STATE_HOME:-$HOME/.local/state}/homelab"
COOLDOWN=600   # seconds between restarts, so a restart that doesn't help can't loop
mkdir -p "$STATE"
exec 9>"$STATE/qbit-watchdog.lock"
flock -n 9 || exit 0

log() { logger -t qbit-watchdog "$*"; [[ -t 1 ]] && echo "$*"; return 0; }
state() { docker inspect --format '{{.State.Status}}{{if .State.Health}}/{{.State.Health.Status}}{{end}}' "$1" 2>/dev/null || echo missing; }
has_net() { docker exec qbittorrent cat /proc/net/dev 2>/dev/null | grep -q 'eth0:'; }
notify() {  # title, message. The topic is a secret: read here, never printed.
  local topic
  topic="$(sed -n 's/^[[:space:]]*NTFY_ALERT_TOPIC=//p' "$REPO/.env" 2>/dev/null | tail -n1 | tr -d "\"'\r" | xargs)"
  if [[ -z $topic ]]; then log "NTFY_ALERT_TOPIC not set: no notification"; return; fi
  curl -fs -m 10 -o /dev/null -H "Title: $1" -H "Priority: default" -H "Tags: wrench" -d "$2" \
    "http://localhost:8081/$topic" || log "ntfy post failed"
}

if [[ ${1:-} == test ]]; then   # scripts/qbit-watchdog.sh test: check the ntfy topic reaches the phone
  notify "qBittorrent watchdog test" "Test message: watchdog notifications work." && log "test notification sent"
  exit 0
fi

qbit=$(state qbittorrent)
[[ $(state gluetun) == running/healthy ]] || exit 0
# Stuck in "created": a compose up gave up waiting for Gluetun's healthcheck (e.g. a redeploy while
# the tunnel flapped). A stop on purpose leaves it "exited", which stays untouched.
if [[ $qbit == created ]]; then
  log "qbittorrent stuck in created while Gluetun is healthy: starting it"
  if docker start qbittorrent >/dev/null; then
    notify "qBittorrent started" "Watchdog started qbittorrent: it was stuck in created after a redeploy (Gluetun wasn't healthy in time)."
  else
    log "docker start qbittorrent failed"
  fi
  exit 0
fi
[[ $qbit == running* ]] || exit 0
has_net && exit 0

now=$(date +%s)
last=$(cat "$STATE/qbit-watchdog.last" 2>/dev/null || echo 0)
if (( now - last < COOLDOWN )); then
  log "qbittorrent has no network; last restart $(( now - last ))s ago, waiting for cooldown"
  exit 0
fi
echo "$now" > "$STATE/qbit-watchdog.last"

log "qbittorrent has no network while Gluetun is healthy: restarting qbittorrent"
docker restart qbittorrent >/dev/null
for _ in $(seq 1 12); do has_net && break; sleep 5; done
if has_net; then
  log "healed: qbittorrent is back on Gluetun's network"
  notify "qBittorrent healed" "Watchdog restarted qbittorrent: it had lost Gluetun's network (Gluetun restarted outside compose). Back on the VPN."
else
  log "restart did not restore qbittorrent's network"
  notify "qBittorrent watchdog: restart didn't help" "qbittorrent still has no network after a restart. Check: scripts/dc.sh media/qbittorrent logs --tail 50"
fi
