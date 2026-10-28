#!/usr/bin/env bash
# docker compose for one service dir, with the repo .env used for interpolation.
# Usage: scripts/dc.sh core/traefik up -d
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
dir="${1:?usage: $0 <service-dir> <compose args...>}"
shift
cd "$REPO"
[[ -f .env ]] || { echo "Missing $REPO/.env (cp .env.example .env)" >&2; exit 1; }
[[ -f "$dir/compose.yaml" ]] || { echo "No compose.yaml in $dir" >&2; exit 1; }
files=(-f "$dir/compose.yaml")
# Optional per-dir fragments (core/uptime-kuma/compose.d/cron-<name>.yaml): always loaded, or AutoKuma drops their monitors.
for f in "$dir"/compose.d/*.yaml; do
  [[ -e $f ]] && files+=(-f "$f")
done
exec docker compose --env-file .env --project-directory "$dir" "${files[@]}" "$@"
