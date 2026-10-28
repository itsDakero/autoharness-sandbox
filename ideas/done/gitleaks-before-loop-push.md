# Scan for secrets before the build loop pushes a branch (gitleaks)

Value: 3   (removes a real risk: an unreviewed build can push a token or webhook to GitHub)
Effort: 2  (pinned binary + a check step in two scripts + a small allowlist)
Risk: 1    (scripts/idea.sh and scripts/deploy-idea.sh only; a hit blocks a push, nothing else changes)
Score: 12
Source: scout 2026-10-26

## Problem
The loop pushes each build to GitHub before anyone has looked at it: `scripts/idea.sh:146` runs
`git -C "$wt" push -q -u origin "idea/$slug"` once the build is committed, and `deploy-idea.sh:98` pushes main.
The only secret check is the reviewer's judgement (`idea-reviewer.md:26`). There is no gitleaks/trufflehog and
no active `.git/hooks`. A builder that pastes a webhook or token into a script or README sends it to `origin`
before review. The 10-23 audit already saw the changedetection Discord webhook turn up in logs.

## Proposal
Install a pinned gitleaks binary (v8.30.1, sha256-checked against the release checksums file) into
`~/.local/bin`, as a user-level step (no root needed) documented in `docs/m5-pipeline.md`. Add a
`gitleaks git --redact --log-opts=<base>..HEAD` step in `idea.sh commit` and in `deploy-idea.sh` before every
push. A hit means no push: the branch stays local, the note is parked, and a Discord line names the file and
rule but never the matched value. Add a small `.gitleaks.toml` allowlist for `.env.example` placeholders. If the
binary is missing, fail closed (no push) with a clear message. Touches no containers, no secrets, no network
beyond the existing push.

## Existing tools checked
- gitleaks (https://github.com/gitleaks/gitleaks/releases): v8.30.1, last release 2026-03-21, MIT, linux_x64
  tarball + checksums; quiet but maintained; fits (single static binary, `git` mode over a commit range).
- trufflehog: heavier, verifies secrets by calling out to providers; not wanted for an offline pre-push check.

## Rough plan
1. Install step for the pinned binary with checksum check; doc line in m5-pipeline.md.
2. `.gitleaks.toml` allowlist; run once over the full history by hand and record (redacted) what it finds.
3. Pre-push scan in idea.sh and deploy-idea.sh; on a hit: no push, park with a reason, Discord line.
4. Test with a throwaway branch holding a fake token pattern.

_Approved on the dashboard, 2026-10-26._

## Plan
Goal: Run a gitleaks scan before every push in idea.sh and deploy-idea.sh. A hit means no push, the branch stays local and the note is parked. If the scan can't run, nothing is pushed.
Kind: script/cron (change to scripts/idea.sh and scripts/deploy-idea.sh, plus one new script)
Files:
- scripts/secret-scan.sh: new script with three modes. Make it executable and give it a header comment.
  - `secret-scan.sh install`: user-level install of gitleaks v8.30.1 into ~/.local/bin/gitleaks.
    - Download `gitleaks_8.30.1_linux_x64.tar.gz` and `gitleaks_8.30.1_checksums.txt` from
      https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/ into a mktemp dir.
    - Check the tarball against the checksums file and against a pinned constant,
      `SHA256=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb` (I fetched it from that checksums file today).
    - If either check fails, abort and install nothing.
    - Extract only the `gitleaks` binary, `install -m 0755`, then print `gitleaks version`.
    - Idempotent: if the right version is already installed, say so and exit 0.
  - `secret-scan.sh <dir> <range>`: scans the commits that are about to be pushed.
    - Binary: `${GITLEAKS:-$HOME/.local/bin/gitleaks}`. Cron and the loop don't have ~/.local/bin on PATH.
    - Command: `gitleaks git "$dir" --log-opts="$range" -c "$REPO/.gitleaks.toml" --redact --no-banner --log-level error --exit-code 3 --report-format json --report-path <mktemp file>`. Delete the report via trap.
    - Exit 0: clean.
    - Exit 1: gitleaks exit 3 (leaks found). Print one line per finding, `<File>:<StartLine> <RuleID> <Commit[0:7]>` (use jq). Never print the Secret or Match fields.
    - Exit 2: the scan can't run. That covers a missing or non-executable binary, a missing .gitleaks.toml, any other gitleaks exit code, and a report that isn't valid JSON. Print a one-line reason to stderr; for a missing binary, name `scripts/secret-scan.sh install`.
  - `secret-scan.sh history`: full-history scan of the repo (no --log-opts), same output and exit codes. Dan runs it once by hand.
- .gitleaks.toml: new file at the repo root.
  - `[extend] useDefault = true`.
  - One `[[allowlists]]` entry with a description, `paths = ['''(^|/)\.env\.example$''']`. Nothing else.
- scripts/idea.sh: scan before each push.
  - Add a helper, `scan_ok <dir> <range> <label>`:
    - Runs secret-scan.sh.
    - Exit 0: return 0.
    - Exit 1: print the findings to stderr. Discord "Secret scan blocked a push of <label>:" plus the first 3 findings, truncated to 300 chars, and "(more)" if there are more. Return 1.
    - Exit 2: print the reason to stderr. Discord "Secret scan couldn't run (<reason>); <label> not pushed". Return 2.
  - Main-branch pushes in start, park and terminal: change each `git push -q || echo ...` so it pushes only if `scan_ok . "$(upstream)..HEAD" main` succeeds.
    - `upstream` = `@{u}` if it resolves, else `origin/main`.
    - When blocked, the existing "committed locally" message still prints.
  - commit: after `git -C "$wt" commit`, run `scan_ok "$wt" "main..HEAD" "idea/$slug"`.
    - 0: push as now.
    - 2: no push. Print "idea.sh: not pushed (secret scan couldn't run); the branch is committed locally". Still notify "Ready to deploy", because deploy-idea rescans before main is pushed.
    - 1, a hit, in this order:
      1. `git -C "$wt" reset -q --soft HEAD~1`. The reviewed marker goes and the worktree keeps the files.
      2. `lock; on_main`.
      3. Park the note on main, keeping the build. Factor the existing park body into `park_note <slug> <reason> <keep>`; when keep=1 it skips drop_build. The `park` command calls it with keep=0, so its behaviour doesn't change.
         The reason: "Secret scan (gitleaks) blocked the push of idea/<slug>. Findings (values redacted):" and the finding lines, then "The build is kept locally in .worktrees/<slug> (not pushed). Fix or allowlist it in .gitleaks.toml, then requeue; requeueing rebuilds from scratch."
         Under it, a `## Questions` section: "1. Is this a real secret (rotate it) or a false positive (allowlist the rule or path)?"
      4. Echo "secret scan hit: parked, not pushed" and exit 0, so the loop doesn't retry or park a second time.
  - Update the header usage comment for commit.
- scripts/deploy-idea.sh: same scan_ok helper, labels `main`.
  - post_merge, line 98: push only if `scan_ok . "$(upstream)..HEAD" main` succeeds. Otherwise print "deploy-idea: push blocked by the secret scan; main is merged locally (fix the commit, then git push)".
    - Whatever the result, still drop the build branch: it was merged, and its remote copy is the one already pushed.
    - The deploy still counts as done and the Discord "Deployed" still posts.
  - reject push, line 189: guard it the same way.
  - Deletion pushes (`push --delete`) are not scanned.
- docs/m5-pipeline.md: a short "Secret scan before push" subsection under Stage C, plus the install, the history run and the fake-token test as commands under Commands. The subsection covers:
  - what is scanned: the branch push (`main..HEAD`) and every push of main (`@{u}..HEAD`);
  - a hit means no push, the note is parked and the build is kept locally;
  - a scan that can't run means no push, the branch is still deployable and the deploy's push rescans;
  - Discord shows file:line, rule and commit only;
  - the allowlist is in `.gitleaks.toml`.
- CLAUDE.md: a scripts-list line in alphabetical order (after `seerr-setup.py`):
  `secret-scan.sh install|history|<dir> <range>` (gitleaks v8.30.1 in ~/.local/bin; idea.sh/deploy-idea.sh scan before every push, a hit or a missing binary = no push).
New service: None
New env vars: None. `GITLEAKS` is only an optional override for tests and doesn't go in .env.example.
Checks the builder must run:
- `bash -n` on scripts/secret-scan.sh, scripts/idea.sh and scripts/deploy-idea.sh.
- `shellcheck` on the three scripts, if it is installed.
- `GITLEAKS=/nonexistent scripts/secret-scan.sh . HEAD~1..HEAD; echo $?` must print a reason naming `install`, then 2.
- `python3 -c 'import tomllib;tomllib.load(open(".gitleaks.toml","rb"))'`.
- `grep -n 'git push' scripts/idea.sh scripts/deploy-idea.sh`: every non-delete push is behind scan_ok.
- Don't run `install` and don't push. Dan does those at deploy.
Review focus:
- gitleaks missing, or exiting with an error code (not 3) -> no push anywhere, clear stderr + one Discord line, the loop carries on, the branch stays deployable.
- Hit in idea.sh commit -> no push, no "Ready to deploy", the reviewed commit is undone (queue and deploy don't see it as ready), the note goes to ideas/parked with findings, the worktree is kept, exit 0.
- Output anywhere (stdout, the note, Discord) -> file:line, rule and commit only; never the Secret/Match fields.
- Main ahead of origin by several commits (an earlier blocked push) -> the scan covers `@{u}..HEAD`, not just the last commit, so later note pushes can't carry an unscanned commit out.
- No upstream set or origin/main missing -> the fallback range works, or the scan exits 2 and the push is blocked. Never a push without a scan.
Docs: CLAUDE.md scripts list (one line); docs/m5-pipeline.md Stage C subsection + Commands.

Note: auto-deploy won't pick this build up (it changes idea.sh and deploy-idea.sh, and it has Manual steps). Dan deploys it from a terminal, after the install.

## Manual steps
1. Before deploying: `scripts/secret-scan.sh install`. Until gitleaks is installed, every loop and deploy push is blocked, but the commits stay local.
2. `scripts/secret-scan.sh history`. Rotate any real secret it reports, or add a narrow allowlist entry to .gitleaks.toml. Note the redacted result in docs/m5-pipeline.md.
3. Test: in a scratch clone, commit a fake token, e.g. a `ghp_` followed by 36 letters and digits. Then run `scripts/secret-scan.sh <clone> HEAD~1..HEAD`; it should exit 1 and print the file:line and rule, with no value.
4. Deploy: `scripts/deploy-idea.sh gitleaks-before-loop-push`.

## Review notes
1. /home/dan/homelab/.worktrees/gitleaks-before-loop-push/scripts/idea-actions.py:109-120: the plan didn't list this file. The builder added the same scan before the dashboard's Answer/Requeue `git push`. It's in scope in spirit: without it, a button push could carry an earlier blocked commit out unscanned (Review focus 4). The m5 doc describes it. Its Discord line doesn't name the findings.
2. /home/dan/homelab/.worktrees/gitleaks-before-loop-push/scripts/secret-scan.sh:9: under `set -e`, an unexpected failure (for example `mktemp`) exits 1, which callers read as "leaks found". In `idea.sh commit` that would park the note with an empty findings list. The same happens if gitleaks ever exits 3 with an empty report. Neither is likely. Mapping unexpected errors to 2 (an ERR trap, or checking for empty output on rc 1) would make the exit codes strict.
3. CLAUDE.md: the plan put the `secret-scan.sh` line after `seerr-setup.py`, and the builder followed it. Alphabetically, `secret-` sorts before `seerr-`, so it belongs before `seerr-route.py`.
4. A hit in `idea.sh commit` sends two Discord lines ("Secret scan blocked..." and "Parked: ..."). That's acceptable, but it's two lines for one event.
5. `reset --soft HEAD~1` only undoes the final commit. That's fine because the loop makes a single commit per build, and the reviewed marker is removed either way.

## Declined to judge
- Merge-commit conflict resolutions aren't scanned (`git log -p` skips merge diffs without `-m`): this is a gitleaks default, and the plan didn't raise it.
- Running the real gitleaks binary against a bad range (no origin/main): I'm not allowed to install or run it. I'm relying on gitleaks exiting non-zero when git writes to stderr, which maps to exit 2, so the push is blocked. Dan's manual step 3 exercises the real binary.
- How the `/build-ideas` skill reads "secret scan hit: parked, not pushed" with exit 0: that's `.claude/` territory, and the plan chose exit 0 on purpose.
