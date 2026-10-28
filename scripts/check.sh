#!/usr/bin/env bash
# Local "is the repo healthy" check; CI runs it too (.github/workflows/check.yml).
# Usage: scripts/check.sh
# Runs in order: bash -n, py_compile, shellcheck (skipped with a note if missing), compose-lint,
# service-catalog --check (docs/services.md fresh, CLAUDE.md Ports table matches homelab.port), unit tests.
# Exit 0 when every step passes, 1 otherwise. Reads files only; bytecode goes to a temp dir.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || exit 1

pycache="$(mktemp -d)"
trap 'rm -rf "$pycache"' EXIT
export PYTHONPYCACHEPREFIX="$pycache"

results=()
failed=0

# step <name> <cmd...>: run one check, record PASS/FAIL.
step() {
  local name=$1
  shift
  echo "== $name"
  if "$@"; then
    results+=("PASS  $name")
  else
    results+=("FAIL  $name")
    failed=1
  fi
}

bash_syntax() {
  local f rc=0
  for f in scripts/*.sh .claude/hooks/*.sh; do
    [[ -e $f ]] || continue
    bash -n "$f" || rc=1
  done
  return "$rc"
}

py_syntax() {
  local f rc=0
  for f in scripts/*.py; do
    python3 -m py_compile "$f" || rc=1
  done
  return "$rc"
}

step "bash -n" bash_syntax
step "py_compile" py_syntax
if command -v shellcheck >/dev/null; then
  step "shellcheck" shellcheck scripts/*.sh .claude/hooks/*.sh
else
  echo "== shellcheck"
  echo "shellcheck not installed (apt install shellcheck); skipped"
  results+=("SKIP  shellcheck (not installed)")
fi
step "compose-lint" python3 scripts/compose-lint.py
step "service-catalog" python3 scripts/service-catalog.py --check
step "unit tests" python3 -m unittest discover -s scripts/tests

echo
echo "== Summary"
printf '%s\n' "${results[@]}"
if ((failed)); then
  echo "check.sh: FAILED"
  exit 1
fi
echo "check.sh: all passed"
