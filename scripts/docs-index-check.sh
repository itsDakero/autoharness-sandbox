#!/usr/bin/env bash
# Cron (weekly, Mondays 09:35, user dan): Discord line when a file in docs/ is not listed in docs/README.md.
# A file counts as listed when docs/README.md names it as `docs/<path>` or names a parent dir as `docs/<dir>/`
# (e.g. `docs/fitness-analysis/` covers its notes). docs/README.md itself is skipped. Read-only, no state:
# the line repeats each week until the index is fixed.
#   scripts/docs-index-check.sh            # what cron runs
#   scripts/docs-index-check.sh --dry-run  # print the result, post nothing
# Exit 0 all listed; 1 unlisted files, Discord line sent (cron-run.sh --ok 0,1, no double alert from Kuma);
# 2 usage, docs/README.md missing, or the Discord post failed (Kuma alerts).
# Test override (shell env, not .env): DOCS_INDEX_DIR = the docs dir to check.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DOCS="${DOCS_INDEX_DIR:-$REPO/docs}"

dry=0
case "${1:-}" in
  "") ;;
  --dry-run) dry=1 ;;
  -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "usage: ${0##*/} [--dry-run]" >&2; exit 2 ;;
esac
(( $# <= 1 )) || { echo "usage: ${0##*/} [--dry-run]" >&2; exit 2; }

index="$DOCS/README.md"
[[ -r $index ]] || { echo "docs index not found: $index"; exit 2; }

missing=()
while IFS= read -r -d '' f; do
  rel="${f#"$DOCS"/}"
  [[ $rel == README.md ]] && continue
  grep -qF -- "\`docs/$rel\`" "$index" && continue
  listed=0; dir="$rel"
  while [[ $dir == */* ]]; do
    dir="${dir%/*}"
    if grep -qF -- "\`docs/$dir/\`" "$index"; then listed=1; break; fi
  done
  (( listed )) || missing+=("docs/$rel")
done < <(find "$DOCS" -type f ! -name '.*' -print0 | sort -z)

if (( ${#missing[@]} == 0 )); then
  echo "docs index ok: every file in docs/ is listed in docs/README.md"
  exit 0
fi

msg="Docs index: ${#missing[@]} file(s) in docs/ not listed in docs/README.md: ${missing[*]}"
if (( dry )); then
  echo "dry run, not posted: $msg"
  exit 1
fi
if "$REPO/scripts/discord.sh" "$msg" >/dev/null 2>&1; then
  echo "$msg"
  exit 1
fi
echo "Discord post failed: $msg"
exit 2
