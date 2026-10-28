#!/usr/bin/env bash
# Create shared networks and app data dirs, then start core services in order.
# Usage: scripts/core-up.sh [service ...]   (default: all core services)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
[[ -f .env ]] || { echo "Missing $REPO/.env (cp .env.example .env)" >&2; exit 1; }
set -a; . ./.env; set +a

ensure_network() {
  local name=$1; shift
  if docker network inspect "$name" >/dev/null 2>&1; then
    echo "Network $name present"
  else
    echo "Creating network $name"
    docker network create "$@" "$name"
  fi
}
ensure_network proxy
ensure_network socket-proxy --internal

# Pre-create bind mounts so Docker doesn't create them root-owned.
for d in adguard/work adguard/conf uptime-kuma autokuma ntfy dashboard ha-backups \
         omada/data omada/logs; do
  mkdir -p "$APPDATA_PATH/$d"
done

if (( $# )); then
  services=("$@")
else
  services=(docker-socket-proxy traefik adguard ntfy uptime-kuma dashboard ha-backups
            omada)
fi

for s in "${services[@]}"; do
  echo "--- $s"
  if [[ $s == uptime-kuma && -z ${KUMA_PASSWORD:-} ]]; then
    echo "KUMA_PASSWORD empty: starting uptime-kuma without autokuma"
    scripts/dc.sh "core/$s" up -d uptime-kuma
  else
    scripts/dc.sh "core/$s" up -d --build
  fi
done
