#!/usr/bin/env bash
# Secret scan (gitleaks) for commits about to be pushed. Used by scripts/idea.sh and scripts/deploy-idea.sh.
#   scripts/secret-scan.sh install          user-level install of gitleaks v8.30.1 into ~/.local/bin (sha256 checked)
#   scripts/secret-scan.sh <dir> <range>    scan the commits in <range> (a git log range, e.g. main..HEAD) of the repo at <dir>
#   scripts/secret-scan.sh history          scan the whole history of this repo (Dan runs it once by hand)
# Exit: 0 clean, 1 leaks found (one "file:line rule commit" line each; never the matched value),
#       2 the scan couldn't run (reason on stderr). Callers treat 2 like 1 for the push: no scan, no push.
# GITLEAKS=<path> overrides the binary (tests only).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="8.30.1"
SHA256="551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
BIN="${GITLEAKS:-$HOME/.local/bin/gitleaks}"

install_cmd() {
  local dest="$HOME/.local/bin/gitleaks" tmp base tar sum
  if [[ -x $dest ]] && "$dest" version 2>/dev/null | grep -q "$VERSION"; then
    echo "gitleaks $VERSION is already installed at $dest"
    return 0
  fi
  tmp="$(mktemp -d)"
  # expand now: tmp is local and gone by the time EXIT fires
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp'" EXIT
  base="https://github.com/gitleaks/gitleaks/releases/download/v$VERSION"
  tar="gitleaks_${VERSION}_linux_x64.tar.gz"
  curl -fsSL -o "$tmp/$tar" "$base/$tar" || { echo "secret-scan: download failed" >&2; return 1; }
  curl -fsSL -o "$tmp/checksums.txt" "$base/gitleaks_${VERSION}_checksums.txt" || { echo "secret-scan: checksums download failed" >&2; return 1; }
  sum="$(sha256sum "$tmp/$tar" | awk '{print $1}')"
  [[ $sum == "$SHA256" ]] || { echo "secret-scan: tarball sha256 doesn't match the pinned value; nothing installed" >&2; return 1; }
  grep -q "^$sum  $tar\$" "$tmp/checksums.txt" || { echo "secret-scan: tarball isn't in the release checksums file; nothing installed" >&2; return 1; }
  tar -xzf "$tmp/$tar" -C "$tmp" gitleaks
  mkdir -p "$HOME/.local/bin"
  install -m 0755 "$tmp/gitleaks" "$dest"
  "$dest" version
}

scan() {  # $1 = dir, $2 = range (empty = whole history)
  local dir="$1" range="$2" report rc=0 args
  [[ -x $BIN ]] || { echo "secret-scan: gitleaks not found or not executable at $BIN; run scripts/secret-scan.sh install" >&2; return 2; }
  [[ -f $REPO/.gitleaks.toml ]] || { echo "secret-scan: $REPO/.gitleaks.toml is missing" >&2; return 2; }
  report="$(mktemp)"; trap 'rm -f "$report"' RETURN
  args=(git "$dir" -c "$REPO/.gitleaks.toml" --redact --no-banner --log-level error --exit-code 3
        --report-format json --report-path "$report")
  [[ -n $range ]] && args+=("--log-opts=$range")
  "$BIN" "${args[@]}" >/dev/null 2>&1 || rc=$?
  case $rc in
    0|3) ;;
    *) echo "secret-scan: gitleaks failed (exit $rc)" >&2; return 2 ;;
  esac
  jq -e 'type == "array"' "$report" >/dev/null 2>&1 || { echo "secret-scan: gitleaks report isn't valid JSON" >&2; return 2; }
  if [[ $rc -eq 3 ]]; then
    jq -r '.[] | "\(.File):\(.StartLine) \(.RuleID) \(.Commit[0:7])"' "$report" 2>/dev/null ||
      { echo "secret-scan: couldn't read the gitleaks report" >&2; return 2; }
    return 1
  fi
  return 0
}

case "${1:-}" in
  install) install_cmd ;;
  history) scan "$REPO" "" ;;
  ""|-h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; [[ -n ${1:-} ]] || exit 2 ;;
  *) [[ $# -eq 2 ]] || { echo "usage: secret-scan.sh <dir> <range> | install | history" >&2; exit 2; }
     scan "$1" "$2" ;;
esac
