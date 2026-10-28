#!/usr/bin/env bash
# Cron (daily 09:25, user dan): ntfy alert when a TLS certificate on the server is close to expiry. openssl only:
# no root, no container. Endpoints in TARGETS ("<host>:<port> <label>"); today only Omada's self-signed UI cert
# (HTTP everywhere else). Add a line per HTTPS endpoint when HTTPS comes.
#   <= 30 days left  (default priority): warn, repeats at most weekly per endpoint
#   <= 7 days left, or expired  (high): crit, sent instead of the warn alert, daily
# An endpoint that does not answer TLS is logged and skipped (its Kuma monitor alerts on that); an unreadable
# expiry date is logged and the script exits 1. State: one line per alert, "<host:port> <level> <epoch>", in
# /srv/homelab/cert-expiry-check/state; an endpoint with time to spare loses its line.
# Logs to syslog (journalctl -t cert-expiry-check). Install: scripts/install-cron.sh.
# `scripts/cert-expiry-check.sh test` sends a test notification.
# Test overrides (shell env, not .env): CERT_CHECK_TARGETS (newline-separated, same format), CERT_CHECK_WARN_DAYS,
# CERT_CHECK_CRIT_DAYS, CERT_CHECK_STATE.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
TARGETS="${CERT_CHECK_TARGETS:-127.0.0.1:8043 omada}"
WARN_DAYS="${CERT_CHECK_WARN_DAYS:-30}"
CRIT_DAYS="${CERT_CHECK_CRIT_DAYS:-7}"
STATE="${CERT_CHECK_STATE:-/srv/homelab/cert-expiry-check/state}"
WARN_REPEAT=$(( 7 * 86400 - 3600 ))
CRIT_REPEAT=0   # crit is sent on every run (cron: daily)

log() { logger -t cert-expiry-check "$*"; [[ -t 1 ]] && echo "$*"; return 0; }
notify() {  # title, message, priority. The topic is a secret: read here, never printed.
  local topic
  topic="$(sed -n 's/^[[:space:]]*NTFY_ALERT_TOPIC=//p' "$REPO/.env" 2>/dev/null | tail -n1 | tr -d "\"'\r" | xargs)"
  if [[ -z $topic ]]; then log "NTFY_ALERT_TOPIC not set: no notification"; return 1; fi
  curl -fs -m 10 -o /dev/null -H "Title: $1" -H "Priority: $3" -H "Tags: lock,warning" -d "$2" \
    "http://localhost:8081/$topic" || { log "ntfy post failed"; return 1; }
}

if [[ ${1:-} == test ]]; then
  notify "Cert expiry check test" "Test message: certificate expiry alerts work." default && log "test notification sent"
  exit
fi

# State: tolerate a missing or corrupt file (bad lines are ignored).
declare -A last   # "<host:port> <level>" -> epoch
declare -A keep   # lines to write back, same key
if [[ -r $STATE ]]; then
  while read -r e l t extra; do
    [[ -n ${e:-} && ${l:-} =~ ^(warn|crit)$ && ${t:-} =~ ^[0-9]+$ && -z ${extra:-} ]] && last["$e $l"]=$t
  done < "$STATE"
fi

now="$(date +%s)"
rc=0
while read -r ep label; do
  [[ -z ${ep:-} ]] && continue
  label="${label:-$ep}"
  host="${ep%:*}"
  # SNI only for names: openssl warns on an IP as servername.
  sni=(); [[ $host =~ ^[0-9.]+$ ]] || sni=(-servername "$host")
  pem="$(timeout 15 openssl s_client -connect "$ep" "${sni[@]}" </dev/null 2>/dev/null)"
  if [[ $pem != *"BEGIN CERTIFICATE"* ]]; then
    log "no TLS answer from $label ($ep): skipped"
    continue   # state kept: a down service says nothing about its cert
  fi
  end="$(openssl x509 -noout -enddate <<< "$pem" 2>/dev/null | sed -n 's/^notAfter=//p')"
  exp=""; [[ -n $end ]] && exp="$(date -d "$end" +%s 2>/dev/null)"   # date -d "" would give today
  if [[ ! $exp =~ ^[0-9]+$ ]]; then
    log "unreadable expiry date for $label ($ep) (got '${end}'): skipped"
    rc=1
    [[ -n ${last["$ep warn"]:-} ]] && keep["$ep warn"]=${last["$ep warn"]}
    [[ -n ${last["$ep crit"]:-} ]] && keep["$ep crit"]=${last["$ep crit"]}
    continue
  fi
  days=$(( (exp - now) / 86400 ))
  when="$(date -u -d "@$exp" +%Y-%m-%d)"

  if (( exp <= now )); then
    level=crit; repeat=$CRIT_REPEAT; prio=high
    title="Cert expired: $label"
    msg="The TLS certificate on $label ($ep) expired on $when. Renew or regenerate it."
  elif (( days <= CRIT_DAYS )); then
    level=crit; repeat=$CRIT_REPEAT; prio=high
    title="Cert expires in $days days: $label"
    msg="The TLS certificate on $label ($ep) expires on $when (limit $CRIT_DAYS days). Renew it now."
  elif (( days <= WARN_DAYS )); then
    level=warn; repeat=$WARN_REPEAT; prio=default
    title="Cert expires in $days days: $label"
    msg="The TLS certificate on $label ($ep) expires on $when (limit $WARN_DAYS days). Plan the renewal."
  else
    log "ok $label $days days (until $when)"
    continue   # time to spare: no keep entry, so the next crossing alerts at once
  fi

  prev="${last["$ep $level"]:-}"
  if [[ -n $prev ]] && (( now - prev < repeat )) && (( now >= prev )); then
    log "suppressed $level $label $days days (last sent $(( (now - prev) / 3600 ))h ago)"
    keep["$ep $level"]=$prev
    continue
  fi
  if notify "$title" "$msg" "$prio"; then
    log "alert $level $label $days days (until $when)"
    keep["$ep $level"]=$now
  else
    log "alert $level $label $days days NOT sent"
    rc=1
    [[ -n $prev ]] && keep["$ep $level"]=$prev
  fi
done <<< "$TARGETS"

# Write state via temp file + mv.
if ! mkdir -p "$(dirname "$STATE")" 2>/dev/null; then log "cannot create $(dirname "$STATE")"; exit 1; fi
tmp="$(mktemp "$STATE.XXXXXX" 2>/dev/null)" || { log "cannot write state $STATE"; exit 1; }
for k in "${!keep[@]}"; do echo "$k ${keep[$k]}"; done | sort > "$tmp"
mv -f "$tmp" "$STATE" || { log "cannot move state into place"; rm -f "$tmp"; exit 1; }
exit $rc
