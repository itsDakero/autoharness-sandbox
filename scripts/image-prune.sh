#!/usr/bin/env bash
# Remove old homelab/* image tags and old build cache. Dry run by default.
#   scripts/image-prune.sh            list what would go (changes nothing)
#   scripts/image-prune.sh --apply    remove it
# Per homelab/<name> repo the newest 2 tags are kept (rollback), plus any tag a container uses (running or
# stopped). Build cache older than 168h is pruned. Other unused images are only listed for Dan to remove by hand.
# Runs after build deploys from scripts/deploy-idea.sh. Never uses -f on rmi, never removes by image ID.
set -euo pipefail

usage() { echo "usage: ${0##*/} [--apply]" >&2; exit 2; }
APPLY=0
case "${1:-}" in
  "") ;;
  --apply) APPLY=1 ;;
  *) usage ;;
esac
[[ $# -le 1 ]] || usage

# Full IDs of every image a container uses, running or stopped
inuse="$(docker ps -aq | xargs -r docker inspect --format '{{.Image}}' | sort -u)"
is_inuse() { grep -qxF -- "$1" <<<"$inuse"; }

imgs="$(docker images --no-trunc --format '{{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}')"

remove=() keep=() other=()
while IFS= read -r repo; do
  [[ -n $repo ]] || continue
  # newest first; version sort, not string sort (0.10.0 > 0.9.0)
  rank=0
  while IFS=$'\t' read -r tag id size; do
    rank=$((rank + 1))
    if (( rank <= 2 )); then keep+=("$repo:$tag (newest)")
    elif is_inuse "$id"; then keep+=("$repo:$tag (in use)")
    else remove+=("$repo:$tag"$'\t'"$size")
    fi
  done < <(awk -F'\t' -v r="$repo" '$1==r && $2!="<none>" {print $2 "\t" $3 "\t" $4}' <<<"$imgs" | sort -t$'\t' -k1,1 -V -r)
done < <(awk -F'\t' '$1 ~ /^homelab\//' <<<"$imgs" | cut -f1 | sort -u)

while IFS=$'\t' read -r repo tag id size; do
  [[ -n $repo ]] || continue
  [[ $repo == homelab/* && $tag != "<none>" ]] && continue
  is_inuse "$id" && continue
  if [[ $repo == "<none>" ]]; then other+=("<none> ${id#sha256:} (dangling)"$'\t'"$size")
  else other+=("$repo:$tag"$'\t'"$size")
  fi
done <<<"$imgs"

echo "== homelab/* tags kept"
if (( ${#keep[@]} )); then printf '  %s\n' "${keep[@]}"; else echo "  none"; fi
echo "== homelab/* tags to remove"
for r in "${remove[@]}"; do printf '  %s  (%s)\n' "${r%%$'\t'*}" "${r#*$'\t'}"; done
(( ${#remove[@]} )) || echo "  none"

echo "== build cache older than 168h"
fail=0
if (( APPLY )); then
  docker builder prune --filter until=168h -f || { echo "image-prune: builder prune failed" >&2; fail=1; }
else
  # buildx du prints a Total line only in some versions; otherwise sum the SIZE column ourselves
  docker buildx du --filter until=168h 2>/dev/null | awk '
    /^Total/ { print; t = 1; next }
    NR > 1 && $3 ~ /^[0-9.]+[kKMGT]?B\*?$/ {
      v = $3; sub(/\*$/, "", v); u = v; sub(/^[0-9.]+/, "", u); sub(/[kKMGT]?B$/, "", v)
      m = (u == "kB" || u == "KB") ? 1e3 : (u == "MB") ? 1e6 : (u == "GB") ? 1e9 : (u == "TB") ? 1e12 : 1
      sum += v * m; n++
    }
    END { if (!t) printf "  Total: %d entries, about %.0f MB\n", n, sum / 1e6 }'
fi

echo "== for Dan (unused, not homelab/*; remove by hand)"
for o in "${other[@]}"; do
  name="${o%%$'\t'*}"
  printf '  %s  (%s)\n' "$name" "${o#*$'\t'}"
done
if (( ${#other[@]} )); then echo "  remove one with: docker rmi <repo:tag>"; else echo "  none"; fi

if (( APPLY )); then
  n=0
  for r in "${remove[@]}"; do
    t="${r%%$'\t'*}"
    if docker rmi "$t"; then n=$((n + 1)); else echo "image-prune: could not remove $t" >&2; fail=1; fi
  done
  echo "== done: $n tag(s) removed"
  (( fail == 0 )) || echo "== some steps failed" >&2
  (( fail == 0 )) || exit 1
else
  echo "== dry run: ${#remove[@]} tag(s) would be removed; use --apply to do it"
fi
