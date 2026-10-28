#!/usr/bin/env bash
# Claude Code hook: one Discord line when the background loop (or scout) waits on a permission prompt
# or auto mode denies a call. Reads the hook JSON on stdin.
#   Events:  Notification (notification_type permission_prompt), PermissionDenied, StopFailure (API error
#            type only, own rate-limit stamp). Others are ignored.
#   Gate:    only runs when HOMELAB_LOOP=1 (set on the loop's start command); otherwise silent, no state.
#   Dry run: LOOP_ALERT_DRY=1 prints the message instead of posting (still rate-limited and stamped).
#   Limit:   one post per session per 10 min; suppressed lines go to syslog (journalctl -t loop-alert).
# Only allow-listed fields are used; never command text, file content, URLs or prompts.
# Always exits 0 so it never blocks Claude Code. The hook entries in .claude/settings.json are added by hand
# (see docs/m5-pipeline.md, "Stall alerts").
set -uo pipefail

[[ ${HOMELAB_LOOP:-} == 1 ]] || exit 0

log() { logger -t loop-alert "$*" 2>/dev/null; return 0; }

input="$(cat 2>/dev/null)" || input=""
command -v jq >/dev/null 2>&1 || { log "jq missing"; exit 0; }

# Allow-listed fields, one per line, tidied (newlines/CR -> space, 200 chars max).
field() {
  printf '%s' "$input" | jq -j "$1 // empty" 2>/dev/null | tr '\n\r' '  ' | cut -c1-200
}
event="$(field '.hook_event_name')"
if [[ -z $event ]]; then log "bad or empty hook input"; exit 0; fi

agent="$(field '.agent_type')"
cwd="$(field '.cwd')"
sid="$(field '.session_id' | tr -cd 'A-Za-z0-9-')"
[[ -n $sid ]] || sid=nosession

stamp="$sid"
case "$event" in
  Notification)
    [[ "$(field '.notification_type')" == permission_prompt ]] || exit 0
    msg="Loop stuck: permission prompt waiting: $(field '.message')"
    ;;
  PermissionDenied)
    msg="Loop: auto mode denied $(field '.tool_name'): $(field '.reason')"
    extra="$(field '.tool_input.description')"
    [[ -n $extra ]] || extra="$(field '.tool_input.file_path')"
    [[ -z $extra ]] || msg+=" ($extra)"
    ;;
  StopFailure)
    etype="$(field '.error' | tr -cd 'a-z_')"
    [[ -n $etype ]] || etype=unknown
    msg="Loop stopped: API error $etype"
    stamp="$sid.stop"
    ;;
  *) exit 0 ;;
esac
[[ -z $agent ]] || msg+=" [$agent]"
[[ -z $cwd ]] || msg+=" in $(basename "$cwd")"

dir="${XDG_RUNTIME_DIR:-/tmp}/homelab-loop-alert"
mkdir -p "$dir" 2>/dev/null && chmod 700 "$dir" 2>/dev/null || { log "no state dir: $msg"; exit 0; }

(
  flock -w 5 9 || { log "lock timeout: $msg"; exit 0; }
  now="$(date +%s)"
  last="$(cat "$dir/$stamp" 2>/dev/null)"
  [[ $last =~ ^[0-9]+$ ]] || last=0
  if (( now - last < 600 )); then
    log "suppressed (rate limit): $msg"
    exit 0
  fi
  if [[ ${LOOP_ALERT_DRY:-} == 1 ]]; then
    echo "$msg"
    ok=0
  else
    "$(dirname "$0")/discord.sh" "$msg" >/dev/null 2>&1
    ok=$?
  fi
  (( ok == 0 )) && echo "$now" > "$dir/$stamp"
  exit 0
) 9>"$dir/.lock"
exit 0
