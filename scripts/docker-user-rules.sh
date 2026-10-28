#!/usr/bin/env bash
# DOCKER-USER firewall rule for core/ha-backups (M4 stage C). Run as root by homelab-docker-user.service
# after every docker start. Published ports skip UFW, so this drops SMB (tcp 445) to the server's LAN IP
# from any LAN source except the Home Assistant Pi. It matches the original destination with conntrack,
# because DOCKER-USER sees packets after Docker's DNAT. Only the LAN interface is filtered, so Uptime Kuma's
# probe from the monitor bridge still gets through (smb.conf "hosts allow" closes it).
# Only ever touches its own rule (tagged with a comment) in DOCKER-USER for tcp port 445.
#   docker-user-rules.sh          add the rule if it is missing
#   docker-user-rules.sh remove   delete the rule
#   docker-user-rules.sh show     print the DOCKER-USER chain
set -euo pipefail
LAN_IP=192.168.0.210
HA_IP=192.168.0.78
PORT=445
TAG=homelab-ha-backups-smb

log() { echo "docker-user-rules: $*"; logger -t docker-user-rules -- "$*" 2>/dev/null || true; }
fail() { log "FAILED: $*"; exit 1; }

(( EUID == 0 )) || { echo "docker-user-rules: run as root" >&2; exit 1; }
if ! iptables -n -L DOCKER-USER >/dev/null 2>&1; then
  [[ ${1:-add} == remove ]] && { log "chain DOCKER-USER missing: nothing to remove"; exit 0; }
  fail "chain DOCKER-USER missing (is docker running?)"
fi

# The interface that holds the LAN IP, so the NIC name isn't hard-coded.
IFACE="$(ip -o -4 addr show | awk -v ip="$LAN_IP" '{split($4, a, "/")} a[1] == ip {print $2; exit}')"
[[ -n $IFACE ]] || fail "no interface has $LAN_IP"

RULE=(-i "$IFACE" -p tcp -m conntrack --ctorigdst "$LAN_IP" --ctorigdstport "$PORT"
      ! -s "$HA_IP" -m comment --comment "$TAG" -j DROP)

case ${1:-add} in
  add)
    if iptables -C DOCKER-USER "${RULE[@]}" 2>/dev/null; then
      log "rule present: drop tcp $PORT to $LAN_IP on $IFACE unless from $HA_IP"
    else
      iptables -I DOCKER-USER 1 "${RULE[@]}"
      log "rule added: drop tcp $PORT to $LAN_IP on $IFACE unless from $HA_IP"
    fi ;;
  remove)
    removed=0
    while iptables -D DOCKER-USER "${RULE[@]}" 2>/dev/null; do removed=$((removed + 1)); done
    log "rule removed ($removed copies) from DOCKER-USER on $IFACE" ;;
  show)
    iptables -S DOCKER-USER ;;
  *) echo "usage: $0 [add|remove|show]" >&2; exit 2 ;;
esac
