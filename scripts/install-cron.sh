#!/usr/bin/env bash
# Install the homelab entries in dan's crontab (no root). Idempotent: replaces lines tagged # homelab.
#   install-cron.sh                  install (REPO = the checkout this script lives in; run it from main only)
#   install-cron.sh --check          compare the tagged crontab lines with the entries from scripts/cron.d/*.cron; print missing:/extra: lines,
#                                    exit 0 "cron: in sync" or 1 on drift (changes nothing)
#   install-cron.sh --check --notify also post one Discord message and log to the journal on drift
# Test override: CRON_LIST=<file> makes --check read the current entries from that file instead of crontab -l.
# deploy-idea.sh runs --check after every deploy and reinstalls on drift; the self-check entry (scripts/cron.d/self-check.cron) checks daily.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
# Every job runs through cron-run.sh <name> <timeout-secs> [--ok codes] <cmd>: syslog (journalctl -t cron-<name>)
# plus a Kuma push monitor cron-<name> (labels on core/uptime-kuma). --ok 0,1 for scripts that exit 1 after they
# already sent their own ntfy/Discord alert, so a finding is not alerted twice; missed runs and timeouts still are.
R="$REPO/scripts/cron-run.sh"
# Entries: one file per job, scripts/cron.d/<name>.cron = optional # comment lines + exactly one crontab line, with
# $R (cron-run.sh path) and $REPO as literal text; ' # homelab' is appended here. Name = file name = 7th field.
# Any problem exits 2 before crontab is read or written (self-check then goes down in Kuma, not a silent pass).
build_entries() {
  local f base line n l out="" found=0 fld
  shopt -s nullglob
  for f in "$REPO"/scripts/cron.d/*.cron; do
    found=1; base="${f##*/}"; n=0; line=""
    [[ $base =~ ^[a-z0-9][a-z0-9-]*\.cron$ ]] || { echo "install-cron: bad file name: $f" >&2; exit 2; }
    while IFS= read -r l || [[ -n $l ]]; do
      [[ -z ${l//[[:space:]]/} || $l == \#* ]] && continue
      n=$((n + 1)); line="$l"
    done <"$f"
    (( n == 1 )) || { echo "install-cron: $f has $n entry lines, need exactly 1" >&2; exit 2; }
    line="${line//\$REPO/$REPO}"   # $REPO first, so the shorter $R cannot eat its prefix
    line="${line//\$R/$R}"
    read -ra fld <<<"$line"
    [[ ${fld[6]:-} == "${base%.cron}" ]] || { echo "install-cron: $f: 7th field '${fld[6]:-}' differs from the file name" >&2; exit 2; }
    out+="$line # homelab"$'\n'
  done
  (( found )) || { echo "install-cron: no scripts/cron.d/*.cron files" >&2; exit 2; }
  printf '%s' "${out%$'\n'}"
}
ENTRIES="$(build_entries)"

usage() { echo "usage: ${0##*/} [--check [--notify]]" >&2; exit 2; }

check() {
  local notify=0 cur line names="" msg nm=0 ne=0
  case "$*" in
    "") ;;
    "--notify") notify=1 ;;
    *) usage ;;
  esac
  if [[ -n ${CRON_LIST:-} ]]; then
    cur="$(grep '# homelab$' "$CRON_LIST" 2>/dev/null || true)"
  else
    cur="$(crontab -l 2>/dev/null | grep '# homelab$' || true)"
  fi
  while IFS= read -r line; do
    [[ -n $line ]] || continue
    if ! grep -qxF -- "$line" <<<"$cur"; then
      echo "missing: $line"; nm=$((nm + 1))
      names+=" $(awk '{print $7}' <<<"$line")"
    fi
  done <<<"$ENTRIES"
  while IFS= read -r line; do
    [[ -n $line ]] || continue
    if ! grep -qxF -- "$line" <<<"$ENTRIES"; then
      echo "extra: $line"; ne=$((ne + 1))
    fi
  done <<<"$cur"
  if (( nm + ne == 0 )); then echo "cron: in sync"; exit 0; fi
  msg="Cron drift: $nm missing, $ne extra; run scripts/install-cron.sh"
  [[ -z $names ]] || msg+=" (missing:$names)"
  if (( notify )); then
    logger -t install-cron "$msg" || true
    "$REPO/scripts/discord.sh" "$msg" >/dev/null 2>&1 || true
  fi
  exit 1
}

case "${1:-}" in
  "") ;;
  --check) shift; check "$@" ;;
  *) usage ;;
esac
{ crontab -l 2>/dev/null | grep -v '# homelab$' || true; echo "$ENTRIES"; } | crontab -
crontab -l | grep '# homelab$'
