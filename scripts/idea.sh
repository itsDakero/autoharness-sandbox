#!/usr/bin/env bash
# Git steps for the background idea loop (/build-ideas), so the agents never improvise them.
# Each idea is built in .worktrees/<slug> on branch idea/<slug>; main only gets note commits until Dan runs
# scripts/deploy-idea.sh. A branch with a reviewed commit ("Reviewed-by: idea-reviewer") is ready to deploy;
# one without is an unfinished build, which `start` throws away and redoes.
#   scripts/idea.sh queue               ideas to build, oldest first (git add date, else file time); notes in
#                                       ideas/waiting/ join once the idea in their "Depends on: <slug>" line is deployed
#   scripts/idea.sh unblocked <slug>    "<slug>\t<title>" per note (ideas/waiting/ or ideas/) that depends on <slug>
#   scripts/idea.sh start <slug>        commit the note on main, make the worktree, Discord "Building"
#   scripts/idea.sh diff <slug>         the build so far vs main, new files included
#   scripts/idea.sh commit <slug>       (message on stdin) note to ideas/done/, commit, secret scan, push the branch
#                                       (a scan hit: no push, the commit is undone, the note is parked, the build kept)
#   scripts/idea.sh park <slug>         (reason on stdin) drop the build, note to ideas/parked/ on main
#   scripts/idea.sh kit-paths <slug>    planned files under .claude/ (the Files: list of the note's last ## Plan)
#   scripts/idea.sh terminal <slug>     drop the build, note + plan to ideas/terminal/ on main: Dan builds it in a
#                                       terminal session (/build-ideas <slug>), where he sees the .claude/ prompts
#   scripts/idea.sh research-ok <slug>  "yes" | "no (<why>)": may the planner ask for the researcher (M6 Stage E)
#   scripts/idea.sh scout-due           "due ..." | "not due ..." (M6 scout: Fridays from 06:00, 6+ days after the last loop run)
#   scripts/idea.sh scout-done [auto]   stamp ideas/proposed/.last-scout after a /scout run (+ .last-scout-auto for a loop run)
#   scripts/idea.sh scout-topic-done    drop the first held topic (a "- " line + its indented lines) from ideas/proposed/_topics.md
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
REVIEWED="Reviewed-by: idea-reviewer"

die() { echo "idea.sh: $*" >&2; exit 1; }
slug_ok() { [[ ${1:-} =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "bad slug: '${1:-}'"; }
title() { sed -n 's/^#[[:space:]]\{1,\}\(Idea:[[:space:]]*\)\{0,1\}//p' "$1" 2>/dev/null | head -n1; }
on_main() { [[ $(git symbolic-ref --short HEAD 2>/dev/null) == main ]] || die "the repo checkout must be on main"; }
has_branch() { git show-ref --verify --quiet "refs/heads/idea/$1"; }
reviewed() { git log "main..idea/$1" --format=%B 2>/dev/null | grep -x "$REVIEWED" >/dev/null; }  # not -q: an early exit can SIGPIPE git log, and pipefail calls that "not reviewed"
lock() {  # one writer on main at a time: this, scripts/deploy-idea.sh, the dashboard's actions (idea-actions.py)
  exec 9>"$(git rev-parse --git-common-dir)/homelab-ideas.lock"
  flock -w 600 9 || die "another idea step held the lock for 10 minutes"
}
note_of() {  # the note's path in a checkout ($2, default the repo): a queued note, else a terminal build's
  local root="${2:-.}"
  if [[ -f $root/ideas/$1.md ]]; then echo "ideas/$1.md"
  elif [[ -f $root/ideas/terminal/$1.md ]]; then echo "ideas/terminal/$1.md"
  elif [[ -f $root/ideas/waiting/$1.md ]]; then echo "ideas/waiting/$1.md"
  else echo "ideas/$1.md"; fi
}
dep_of() {  # the slug in the header's "Depends on: <slug> free text" line (header = lines before the first "## "), or nothing
  local line word
  line="$(sed '/^## /q' "$1" 2>/dev/null | grep -i -m1 '^Depends on:' || true)"
  [[ -n $line ]] || return 0
  word="$(awk '{print $1}' <<<"${line#*:}")"
  word="${word%[,.)]}"
  if [[ $word =~ ^[a-z0-9][a-z0-9-]* ]]; then echo "${BASH_REMATCH[0]}"; fi
  return 0
}
deployed() { git cat-file -e "main:ideas/done/$1.md" 2>/dev/null; }  # on main, not in the working tree: a built-but-unmerged branch doesn't count
waiting_taken() {  # a waiting note's slug is already used elsewhere: starting it would collide
  local d
  [[ -e ideas/$1.md ]] && return 0
  for d in "done" parked rejected terminal; do [[ -e ideas/$d/$1.md ]] && return 0; done
  return 1
}
plan_files() {  # the Files: list of the last "## Plan" section of note $1, one path per line
  awk '/^## Plan[[:space:]]*$/ {n++; delete f; c=0; inplan=1; infiles=0; next}
       /^## / {inplan=0; infiles=0}
       inplan && /^Files:/ {infiles=1; next}
       inplan && infiles && /^[[:space:]]*- / {
         l=$0; sub(/^[[:space:]]*- [[:space:]]*/, "", l); sub(/:.*/, "", l); gsub(/[`*]/, "", l)
         sub(/[[:space:]].*/, "", l); if (l != "") f[++c]=l; next}
       inplan && infiles && /^[^[:space:]]/ {infiles=0}
       END {for (i = 1; i <= c; i++) print f[i]}' "$1"
}
notify() { "$REPO/scripts/discord.sh" "$1" >/dev/null || true; }  # the feed is best effort

upstream() { if git rev-parse --verify -q '@{u}' >/dev/null 2>&1; then echo '@{u}'; else echo origin/main; fi; }
scan_ok() {  # <dir> <range> <label>: secret scan before a push. 0 clean, 1 hit (SCAN_OUT = findings), 2 couldn't run
  local err rc=0 f
  SCAN_OUT=""; err="$(mktemp)"
  SCAN_OUT="$("$REPO/scripts/secret-scan.sh" "$1" "$2" 2>"$err")" || rc=$?
  case $rc in
    0) rm -f "$err"; return 0 ;;
    1) rm -f "$err"
       echo "idea.sh: secret scan blocked a push of $3:" >&2
       # indents every line of a multi-line string
       # shellcheck disable=SC2001
       sed 's/^/  /' <<<"$SCAN_OUT" >&2
       f="$(head -n3 <<<"$SCAN_OUT" | paste -sd';' -)"; f="${f//;/; }"
       [[ $(wc -l <<<"$SCAN_OUT") -gt 3 ]] && f+=" (more)"
       notify "Secret scan blocked a push of $3: ${f:0:300}"
       return 1 ;;
    *) f="$(head -n1 "$err")"; rm -f "$err"
       echo "idea.sh: ${f:-secret scan could not run}; $3 not pushed" >&2
       notify "Secret scan couldn't run (${f#secret-scan: }); $3 not pushed"
       return 2 ;;
  esac
}
push_main() {  # <what failed/blocked message> : push main only after a clean scan
  if scan_ok . "$(upstream)..HEAD" main; then git push -q || echo "idea.sh: push failed; $1" >&2
  else echo "idea.sh: not pushed (secret scan); $1" >&2; fi
}
park_note() {  # <slug> <reason> <keep>: note to ideas/parked/ on main (keep=1 keeps the build); needs lock + on_main
  local slug="$1" reason="$2" keep="$3" note paths
  note="$(note_of "$slug")"; [[ -f $note ]] || die "no $note"
  [[ $keep == 1 ]] || drop_build "$slug"
  mkdir -p ideas/parked
  printf '\n## Parked %s\n\n%s\n' "$(date +%F)" "$reason" >>"$note"
  paths=("ideas/parked/$slug.md")
  if git ls-files --error-unmatch "$note" >/dev/null 2>&1; then
    git mv -- "$note" "ideas/parked/$slug.md"
    paths+=("$note")
  else
    mv -- "$note" "ideas/parked/$slug.md"
  fi
  git add -- "ideas/parked/$slug.md"
  git commit -q -m "ideas: park $slug" -- "${paths[@]}"
  push_main "the park is committed locally"
  notify "Parked: $(title "ideas/parked/$slug.md"). Questions: http://homelab/admin#parked"
}

drop_build() {  # worktree + branch, local and remote
  [[ -d .worktrees/$1 ]] && git worktree remove --force ".worktrees/$1"
  git worktree prune
  if has_branch "$1"; then git branch -q -D "idea/$1"; fi
  git push -q origin --delete "idea/$1" 2>/dev/null || true
}

cmd="${1:-}"; slug="${2:-}"
case "$cmd" in
queue)
  for f in ideas/*.md ideas/waiting/*.md; do
    [[ -e $f ]] || continue
    s="$(basename "$f" .md)"
    dep="$(dep_of "$f" || true)"
    if [[ $f == ideas/waiting/* ]]; then
      # continue unless there is a dep and it is deployed
      # shellcheck disable=SC2015
      [[ -n $dep ]] && deployed "$dep" || continue  # waits: no dependency line, or it isn't deployed yet
      waiting_taken "$s" && continue                # collision: stays put, the dashboard shows it
    elif [[ -n $dep ]] && ! deployed "$dep"; then continue
    fi
    if has_branch "$s" && reviewed "$s"; then continue; fi  # ready to deploy
    d="$(git log --diff-filter=A --format=%at -- "$f" | tail -n1)"
    echo "${d:-$(stat -c %Y "$f")} $s"
  done | sort -n | awk '{print $2}'
  ;;
unblocked)
  slug_ok "$slug"
  for f in ideas/waiting/*.md ideas/*.md; do
    [[ -e $f ]] || continue
    [[ $(dep_of "$f" || true) == "$slug" ]] || continue
    printf '%s\t%s\n' "$(basename "$f" .md)" "$(title "$f")"
  done | sort -t$'\t' -k1,1
  ;;
start)
  slug_ok "$slug"; lock; on_main
  note="$(note_of "$slug")"
  [[ -f $note ]] || die "no ideas/$slug.md, ideas/terminal/$slug.md or ideas/waiting/$slug.md"
  dep="$(dep_of "$note" || true)"
  if [[ -n $dep ]] && ! deployed "$dep"; then die "$slug waits on $dep, which isn't deployed yet"; fi
  oldnote=""
  if [[ $note == ideas/waiting/* ]]; then
    waiting_taken "$slug" && die "$slug collides with a note in ideas/ (done, parked, rejected or terminal); rename the waiting note"
    oldnote="$note"; note="ideas/$slug.md"
    if git ls-files --error-unmatch "$oldnote" >/dev/null 2>&1; then git mv -- "$oldnote" "$note"; else mv -- "$oldnote" "$note"; fi
  fi
  if has_branch "$slug"; then
    reviewed "$slug" && die "idea/$slug is already built; deploy or drop it (scripts/deploy-idea.sh)"
    drop_build "$slug"  # unfinished build from an interrupted run
  fi
  if ! git ls-files --error-unmatch "$note" >/dev/null 2>&1 || ! git diff --quiet HEAD -- "$note"; then
    git add -- "$note"
    paths=("$note")
    if [[ -n $oldnote ]] && git cat-file -e "HEAD:$oldnote" 2>/dev/null; then paths+=("$oldnote"); fi  # the tracked waiting note: commit its removal too
    git commit -q -m "ideas: queue $slug" -- "${paths[@]}"
    push_main "the note is committed locally"
  fi
  git worktree add -q -b "idea/$slug" ".worktrees/$slug" main
  notify "Building: $(title "$note")"
  echo "$REPO/.worktrees/$slug"
  [[ $note == ideas/terminal/* ]] && echo "note: $REPO/.worktrees/$slug/$note (terminal build: the plan is in it)"
  ;;
diff)
  slug_ok "$slug"
  wt=".worktrees/$slug"; [[ -d $wt ]] || die "no $wt"
  git -C "$wt" add -A -N  # new files show up in the diff (intent to add; nothing is staged)
  git -C "$wt" diff --stat main
  git -C "$wt" diff main
  ;;
commit)
  slug_ok "$slug"
  wt=".worktrees/$slug"; [[ -d $wt ]] || die "no $wt"
  msg="$(cat)"; [[ -n $msg ]] || die "commit message on stdin"
  grep -qx "$REVIEWED" <<<"$msg" || msg+=$'\n'"$REVIEWED"
  mkdir -p "$wt/ideas/done"
  git -C "$wt" mv "$(note_of "$slug" "$wt")" "ideas/done/$slug.md"
  git -C "$wt" add -A
  git -C "$wt" commit -q -F - <<<"$msg"
  scan_rc=0; scan_ok "$wt" "main..HEAD" "idea/$slug" || scan_rc=$?
  case $scan_rc in
    0) git -C "$wt" push -q -u origin "idea/$slug" || echo "idea.sh: push failed; the branch is committed locally" >&2 ;;
    2) echo "idea.sh: not pushed (secret scan couldn't run); the branch is committed locally" >&2 ;;  # deploy-idea rescans before main is pushed
    *) findings="$SCAN_OUT"
       git -C "$wt" reset -q --soft HEAD~1  # the reviewed marker goes; the worktree keeps the files
       lock; on_main
       park_note "$slug" "Secret scan (gitleaks) blocked the push of idea/$slug. Findings (values redacted):
$findings

The build is kept locally in .worktrees/$slug (not pushed). Fix or allowlist it in .gitleaks.toml, then requeue; requeueing rebuilds from scratch.

## Questions

1. Is this a real secret (rotate it) or a false positive (allowlist the rule or path)?" 1
       echo "secret scan hit: parked, not pushed"
       exit 0 ;;
  esac
  notify "Ready to deploy: $(title "$wt/ideas/done/$slug.md"). Deploy tab: http://homelab/admin#deploy"
  git -C "$wt" log --oneline -1
  ;;
park)
  slug_ok "$slug"; lock; on_main
  reason="$(cat)"; [[ -n $reason ]] || die "reason on stdin"
  park_note "$slug" "$reason" 0
  ;;
kit-paths)
  slug_ok "$slug"
  wt=".worktrees/$slug"; [[ -d $wt ]] || die "no $wt"
  note="$wt/$(note_of "$slug" "$wt")"; [[ -f $note ]] || die "no $note"
  plan_files "$note" | grep -E '(^|/)\.claude/' || true
  ;;
terminal)
  slug_ok "$slug"; lock; on_main
  note="ideas/$slug.md"; [[ -f $note ]] || die "no $note"
  wtnote=".worktrees/$slug/$note"; [[ -f $wtnote ]] || die "no $wtnote (the plan goes there first)"
  grep -q '^## Plan' "$wtnote" || die "$wtnote has no ## Plan"
  [[ -e ideas/terminal/$slug.md ]] && die "ideas/terminal/$slug.md already exists"
  mkdir -p ideas/terminal
  cp -- "$wtnote" "ideas/terminal/$slug.md"  # the queued note + the planner's plan and manual steps
  printf '\n## Build in a terminal %s\n\nPlanned files under .claude/ (Claude Code asks before each write there, and\nnobody sees that in the background loop):\n%s\n' \
    "$(date +%F)" "$(plan_files "$wtnote" | grep -E '(^|/)\.claude/' | sed 's/^/- /')" >>"ideas/terminal/$slug.md"
  drop_build "$slug"
  paths=("ideas/terminal/$slug.md")
  if git ls-files --error-unmatch "$note" >/dev/null 2>&1; then git rm -q -- "$note"; paths+=("$note"); else rm -f -- "$note"; fi
  git add -- "ideas/terminal/$slug.md"
  git commit -q -m "ideas: $slug needs a terminal build" -- "${paths[@]}"
  push_main "the move is committed locally"
  notify "Needs a terminal build: $(title "ideas/terminal/$slug.md"). Steps: http://homelab/admin#deploy"
  ;;
research-ok)
  slug_ok "$slug"
  wt=".worktrees/$slug"; [[ -d $wt ]] || die "no $wt"
  note="$wt/$(note_of "$slug" "$wt")"; [[ -f $note ]] || die "no $note"
  head="$(sed '/^## /q' "$note")"  # the score header sits above the first section
  effort="$(sed -n 's/^Effort:[[:space:]]*\([0-9]\).*/\1/p' <<<"$head" | head -n1)"
  if grep -q '^## Research' "$note"; then echo "no (it already has a ## Research section)"
  elif grep -qi '^Research:[[:space:]]*yes' <<<"$head"; then echo "no (Research: yes; the planner's research mode)"
  elif grep -qi '^Source:[[:space:]]*scout' <<<"$head"; then echo "no (a scout note: it comes with its research)"
  elif [[ -n $effort ]] && (( effort <= 2 )); then echo "no (a small idea: Effort $effort)"
  else echo "yes"; fi
  ;;
scout-due)  # only loop runs count: a hand /scout never moves the Friday run
  stamp=ideas/proposed/.last-scout-auto
  last=never; age=999999999
  if [[ -e $stamp ]]; then
    last="$(date -d "@$(stat -c %Y "$stamp")" '+%F %H:%M')"; age=$(( $(date +%s) - $(stat -c %Y "$stamp") ))
  fi
  if (( $(date +%u) == 5 && 10#$(date +%H) >= 6 && age > 6 * 86400 )); then echo "due (last loop run: $last)"
  else echo "not due (last loop run: $last; runs Fridays from 06:00, or /scout by hand)"; fi
  ;;
scout-done)
  mkdir -p ideas/proposed
  date -Is >ideas/proposed/.last-scout
  if [[ $slug == auto ]]; then date -Is >ideas/proposed/.last-scout-auto; fi
  ;;
scout-topic-done)  # the run used the first held topic: drop it (its "- " line and the indented lines after it)
  f=ideas/proposed/_topics.md
  [[ -f $f ]] || exit 0
  awk 'done != 1 && /^- / { skip = 1; done = 1; next } skip && /^  / { next } { skip = 0; print }' "$f" >"$f.tmp" &&
    mv -- "$f.tmp" "$f"
  ;;
*)
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
  ;;
esac
