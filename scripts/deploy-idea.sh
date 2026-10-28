#!/usr/bin/env bash
# Deploy a reviewed idea build from the background loop (/build-ideas). Dan runs this, not Claude.
#   scripts/deploy-idea.sh               builds ready to deploy
#   scripts/deploy-idea.sh <slug>        show it, ask, merge into main, start what changed, check, push
#   scripts/deploy-idea.sh drop <slug>   throw the build away; the note stays in ideas/, so the loop redoes it
#                                        (edit or move the note first if you don't want that)
#   scripts/deploy-idea.sh reject <slug> throw the build away and file the note under ideas/rejected/ with the
#                                        date and a reason (asked for, or on stdin: the dashboard's Reject button);
#                                        the planner won't build the same thing again unless something changed;
#                                        also files a plan waiting in ideas/terminal/ (no build yet) or a
#                                        parked note in ideas/parked/ (no branch, no build to drop)
#   scripts/deploy-idea.sh check <slug>  "terminal <file>" / "sensitive <file>" lines (the dashboard's Deploy tab)
#   --yes [--sensitive-ok] <slug>        no prompt: the dashboard's Deploy button (scripts/idea-actions.py).
#                                        Refuses terminal-only builds; sensitive ones need --sensitive-ok
#   --post-merge <slug>                  the steps after the merge (internal: re-exec after a self-update; or by hand)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
REVIEWED="Reviewed-by: idea-reviewer"
APPDATA="${APPDATA_PATH:-/srv/homelab}"
# Changes here need a closer look before saying yes: DNS, network, firewall, host setup, backups, the kit.
# Terminal only: host setup (bootstrap.sh has to be run as root after) and the Claude Code kit that reviews builds.
TERMINAL_ONLY='^(bootstrap\.sh|systemd/|\.claude/)'
SENSITIVE='^(bootstrap\.sh|systemd/|\.claude/|scripts/(backup|docker-user-rules)|core/(adguard|traefik|omada|docker-socket-proxy|ha-backups)/)'

die() { echo "deploy-idea: $*" >&2; exit 1; }
title() { sed -n 's/^#[[:space:]]\{1,\}\(Idea:[[:space:]]*\)\{0,1\}//p' "$1" 2>/dev/null | head -n1; }
reviewed() { git log "main..idea/$1" --format=%B 2>/dev/null | grep -x "$REVIEWED" >/dev/null; }  # not -q: an early exit can SIGPIPE git log, and pipefail calls that "not reviewed"
done_note() { git show "idea/$1:ideas/done/$1.md" 2>/dev/null || true; }
classify() {  # changed files on stdin -> "terminal <file>" / "sensitive <file>"
  local f
  while IFS= read -r f; do
    if [[ $f =~ $TERMINAL_ONLY ]]; then echo "terminal $f"
    elif [[ $f =~ $SENSITIVE ]]; then echo "sensitive $f"
    fi
  done
  return 0
}
lock() {  # one writer on main at a time: the build loop (idea.sh), deploys, the dashboard's actions
  exec 9>"$(git rev-parse --git-common-dir)/homelab-ideas.lock"
  flock -w 600 9 || die "another idea step held the lock for 10 minutes"
}
upstream() { if git rev-parse --verify -q '@{u}' >/dev/null 2>&1; then echo '@{u}'; else echo origin/main; fi; }
scan_ok() {  # <dir> <range> <label>: secret scan before a push. 0 clean, 1 hit, 2 couldn't run
  local err rc=0 out f
  err="$(mktemp)"
  out="$("$REPO/scripts/secret-scan.sh" "$1" "$2" 2>"$err")" || rc=$?
  case $rc in
    0) rm -f "$err"; return 0 ;;
    1) rm -f "$err"
       echo "deploy-idea: secret scan blocked a push of $3:" >&2
       # indents every line of a multi-line string
       # shellcheck disable=SC2001
       sed 's/^/  /' <<<"$out" >&2
       f="$(head -n3 <<<"$out" | paste -sd';' -)"; f="${f//;/; }"
       [[ $(wc -l <<<"$out") -gt 3 ]] && f+=" (more)"
       "$REPO/scripts/discord.sh" "Secret scan blocked a push of $3: ${f:0:300}" >/dev/null || true
       return 1 ;;
    *) f="$(head -n1 "$err")"; rm -f "$err"
       echo "deploy-idea: ${f:-secret scan could not run}; $3 not pushed" >&2
       "$REPO/scripts/discord.sh" "Secret scan couldn't run (${f#secret-scan: }); $3 not pushed" >/dev/null || true
       return 2 ;;
  esac
}
drop_build() {
  [[ -d .worktrees/$1 ]] && git worktree remove --force ".worktrees/$1"
  git worktree prune
  git branch -q -D "idea/$1"
  git push -q origin --delete "idea/$1" 2>/dev/null || true
}

post_merge() {  # the steps after the merge; needs $s, $name and $changed
  local dirs d svc state services=() built=0
  # Start or update every service dir whose files changed. New service: create its app data dir first,
  # owned by dan (docker would create a missing bind-mount source as root).
  dirs="$(git diff --name-only HEAD^1 HEAD | xargs -rn1 dirname | sed 's#/compose\.d$##' | sort -u)"
  # built: a Dockerfile dir was rebuilt; prune old homelab/* images afterwards
  for d in $dirs; do
    [[ -f $d/compose.yaml ]] || continue
    svc="$(basename "$d")"
    git cat-file -e "HEAD^1:$d/compose.yaml" 2>/dev/null || mkdir -p "$APPDATA/$svc"
    echo "== starting $d"
    if [[ -f $d/Dockerfile ]]; then
      "$REPO/scripts/dc.sh" "$d" up -d --build
      built=1
    else
      "$REPO/scripts/dc.sh" "$d" up -d
    fi
    services+=("$svc")
  done
  for d in $dirs; do
    if git cat-file -e "HEAD^1:$d/compose.yaml" 2>/dev/null && [[ ! -f $d/compose.yaml ]]; then
      echo "!! $d/compose.yaml was removed; stop that container by hand (docker stop $(basename "$d"))"
    fi
  done
  grep -qE '^(bootstrap\.sh|systemd/)' <<<"$changed" && echo "!! Host setup changed: run  sudo ./bootstrap.sh"

  echo "== cron"  # only dan's user crontab; a failure never fails the deploy
  if ! "$REPO/scripts/install-cron.sh" --check; then
    "$REPO/scripts/install-cron.sh" || echo "deploy-idea: install-cron failed (deploy is fine)" >&2
  fi

  for svc in "${services[@]}"; do
    echo "== checking $svc"
    state=""
    for _ in $(seq 24); do  # up to 2 min
      state="$(docker ps --filter "name=^/$svc$" --format '{{.Status}}')"
      [[ $state == Up* && $state != *starting* && $state != *unhealthy* ]] && break
      sleep 5
    done
    echo "container: ${state:-not running}"
    "$REPO/scripts/kuma-status.py" "$svc" --beats 1 || true
  done

  if (( built )); then  # a prune failure never fails the deploy
    echo "== pruning old homelab images"
    "$REPO/scripts/image-prune.sh" --apply || echo "deploy-idea: image prune had errors (deploy is fine)" >&2
  fi

  if scan_ok . "$(upstream)..HEAD" main; then
    git push -q || echo "deploy-idea: push failed; main is merged locally" >&2
  else
    echo "deploy-idea: push blocked by the secret scan; main is merged locally (fix the commit, then git push)" >&2
  fi
  drop_build "$s"
  "$REPO/scripts/discord.sh" "Deployed: $name" >/dev/null || true
  # Waiting notes that depend on this idea can be queued now (idea.sh queue sees ideas/done/$s.md on main)
  local slug_t title_t
  while IFS=$'\t' read -r slug_t title_t; do
    [[ -n $slug_t ]] || continue
    echo "Unblocked: ${title_t:-$slug_t}. The loop picks it up on its next pass"
    "$REPO/scripts/discord.sh" "Unblocked: ${title_t:-$slug_t}. The loop picks it up on its next pass" >/dev/null || true
  done < <("$REPO/scripts/idea.sh" unblocked "$s" 2>/dev/null || true)
  echo "Deployed $s. Check the dashboard; Kuma may need a minute for a new monitor."
}

YES=0 SENSITIVE_OK=0 POST=0
while [[ ${1:-} == --* ]]; do
  case $1 in
    --yes) YES=1 ;;
    --sensitive-ok) SENSITIVE_OK=1 ;;
    --post-merge) POST=1 ;;
    *) die "unknown option $1" ;;
  esac
  shift
done

if [[ $# -eq 0 ]]; then
  found=0
  for b in $(git for-each-ref --format='%(refname:short)' 'refs/heads/idea/'); do
    s="${b#idea/}"
    if reviewed "$s"; then
      echo "ready     $s  $(done_note "$s" | title /dev/stdin)"
    else
      echo "building  $s"
    fi
    found=1
  done
  (( found )) || echo "No idea builds."
  exit 0
fi

if [[ $1 == check ]]; then
  s="${2:-}"; git show-ref --verify --quiet "refs/heads/idea/$s" || die "no branch idea/$s"
  git diff --name-only "main...idea/$s" | classify
  exit 0
fi

if [[ $1 == drop ]]; then
  s="${2:-}"; git show-ref --verify --quiet "refs/heads/idea/$s" || die "no branch idea/$s"
  lock
  read -rp "Throw away the build of '$s'? [y/N] " a; [[ $a == [yY]* ]] || exit 1
  drop_build "$s"
  "$REPO/scripts/discord.sh" "Dropped build: $s (the idea stays queued)" >/dev/null || true
  echo "Dropped. ideas/$s.md is still queued; edit or move it if it shouldn't be rebuilt."
  exit 0
fi

if [[ $1 == reject ]]; then
  s="${2:-}"; [[ $s =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "bad slug: '$s'"
  hand=0  # a plan waiting for a terminal build (ideas/terminal/): no branch yet, only the note
  if git show-ref --verify --quiet "refs/heads/idea/$s"; then
    reviewed "$s" || die "idea/$s isn't reviewed yet (the loop or a terminal build may still be on it)"
  elif [[ -f ideas/terminal/$s.md ]]; then hand=1
  elif [[ -f ideas/parked/$s.md ]]; then hand=1
  else die "no branch idea/$s, no ideas/terminal/$s.md and no ideas/parked/$s.md"
  fi
  if [[ -t 0 ]]; then read -rp "Why reject '$s'? (a short reason; empty cancels) " reason; else reason="$(head -c 2000)"; fi
  reason="$(tr -s '[:space:]' ' ' <<<"$reason" | sed 's/^ //; s/ $//')"  # one line
  [[ -n $reason ]] || die "no reason given; nothing rejected"
  lock
  [[ $(git symbolic-ref --short HEAD) == main ]] || die "check out main first"
  note="ideas/$s.md" rej="ideas/rejected/$s.md"
  [[ -f ideas/terminal/$s.md ]] && note="ideas/terminal/$s.md"  # a terminal build: its note waits there on main
  # A parked note: only when there is no branch, so a build's done note still wins
  if ! git show-ref --verify --quiet "refs/heads/idea/$s" && [[ -f ideas/parked/$s.md ]]; then note="ideas/parked/$s.md"; fi
  [[ -e $rej ]] && die "$rej already exists"
  mkdir -p ideas/rejected
  # The build's copy has the planner's plan too, which helps judge "the same thing" later
  done_note "$s" >"$rej"
  [[ -s $rej ]] || { [[ -f $note ]] && cp -- "$note" "$rej"; } || { rm -f -- "$rej"; die "no note for $s"; }
  name="$(title "$rej")"
  printf '\n## Rejected %s\n\nStatus: rejected\nReason: %s\n' "$(date +%F)" "$reason" >>"$rej"
  paths=("$rej")
  git ls-files --error-unmatch "$note" >/dev/null 2>&1 && paths+=("$note")
  if ! { git add -- "$rej" && { [[ ${#paths[@]} -eq 1 ]] || git rm -q -- "$note"; } &&
         git commit -q -m "ideas: reject $s" -m "Reason: $reason" -- "${paths[@]}"; }; then
    # Put main back as it was: a staged half-move would block the next deploy
    git reset -q -- "${paths[@]}" 2>/dev/null || true
    [[ ${#paths[@]} -eq 1 ]] || git checkout -q -- "$note" 2>/dev/null || true
    rm -f -- "$rej"
    die "commit failed; nothing rejected"
  fi
  [[ ${#paths[@]} -eq 1 ]] && rm -f -- "$note"  # an untracked note
  if scan_ok . "$(upstream)..HEAD" main; then
    git push -q || echo "deploy-idea: push failed; the rejection is committed locally" >&2
  else
    echo "deploy-idea: push blocked by the secret scan; the rejection is committed locally" >&2
  fi
  (( hand )) || drop_build "$s"
  "$REPO/scripts/discord.sh" "Rejected: ${name:-$s} ($reason)" >/dev/null || true
  # Notes that wait on this idea stay in place; Dan decides (edit the Depends on line, or reject them)
  titles="$("$REPO/scripts/idea.sh" unblocked "$s" 2>/dev/null | cut -f2 | paste -sd, - | sed 's/,/, /g' || true)"
  if [[ -n $titles ]]; then
    n="$("$REPO/scripts/idea.sh" unblocked "$s" 2>/dev/null | wc -l || true)"
    echo "Waiting on $s (left in place): $titles"
    "$REPO/scripts/discord.sh" "Rejected ${name:-$s}: $n waiting idea(s) depend on it (${titles:0:300}). Edit or remove them in ideas/waiting/" >/dev/null || true
  fi
  if (( hand )); then echo "Rejected $s: the note is in $rej."; else echo "Rejected $s: the build is gone, the note is in $rej."; fi
  exit 0
fi

if (( POST )); then  # the steps after the merge, run from the merged copy of this script
  s="${1:-}"; [[ $s =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "bad slug: '$s'"
  # fd 9 (the lock) is inherited across exec; opening it again would release it
  [[ -n ${DEPLOY_IDEA_REEXEC:-} ]] || lock
  [[ $(git symbolic-ref --short HEAD) == main ]] || die "check out main first"
  subj="$(git log -1 --format=%s HEAD)"
  [[ $subj == "Merge idea/$s: "* ]] || die "HEAD is not the merge of idea/$s"
  name="${subj#"Merge idea/$s: "}"
  changed="$(git diff --name-only HEAD^1 HEAD)"
  post_merge
  exit 0
fi

s="$1"
lock
[[ $(git symbolic-ref --short HEAD) == main ]] || die "check out main first"
# die if either diff is non-empty; die never returns
# shellcheck disable=SC2015
git diff --quiet && git diff --cached --quiet || die "main has uncommitted changes; commit or stash them first"
git show-ref --verify --quiet "refs/heads/idea/$s" || die "no branch idea/$s (scripts/deploy-idea.sh lists them)"
reviewed "$s" || die "idea/$s has no reviewed commit yet (the loop is still on it, or it failed)"
name="$(done_note "$s" | title /dev/stdin)"

echo "== $name (idea/$s)"
git log --oneline "main..idea/$s"
git diff --stat "main...idea/$s"
changed="$(git diff --name-only "main...idea/$s")"
if risky="$(grep -E "$SENSITIVE" <<<"$changed")"; then
  echo
  echo "!! Touches sensitive files, look at these diffs before saying yes:"
  # indents every line of a multi-line string
  # shellcheck disable=SC2001
  sed 's/^/   /' <<<"$risky"
fi
manual="$(done_note "$s" | sed -n '/^## Manual steps/,/^## /p' | sed '$!b;/^## /d')"
[[ -n $manual ]] && { echo; echo "$manual"; }
echo
if (( YES )); then
  kinds="$(classify <<<"$changed")"
  grep -q '^terminal ' <<<"$kinds" && die "touches host setup or the Claude Code kit; deploy it from a terminal: scripts/deploy-idea.sh $s"
  grep -q '^sensitive ' <<<"$kinds" && (( ! SENSITIVE_OK )) && die "touches sensitive files; confirm them first (--sensitive-ok)"
  echo "Deploying $s (--yes)"
else
  read -rp "Deploy $s? (full diff: git diff main...idea/$s) [y/N] " a
  [[ $a == [yY]* ]] || exit 1
fi

git merge -q --no-ff -m "Merge idea/$s: $name" "idea/$s" || { git merge --abort; die "merge conflict; nothing deployed"; }

if grep -qx 'scripts/deploy-idea.sh' <<<"$changed" && [[ -z ${DEPLOY_IDEA_REEXEC:-} ]]; then
  echo "== deploy-idea.sh changed: continuing with the new copy"
  DEPLOY_IDEA_REEXEC=1 exec "$REPO/scripts/deploy-idea.sh" --post-merge "$s"
fi
post_merge
