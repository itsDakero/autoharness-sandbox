# Discord line when the build loop stops on an API error

Value: 3   (Dan learns the same day that the loop hit the usage limit or got logged out, instead of noticing nothing got built)
Effort: 1  (one case in an existing hook script plus one settings entry)
Risk: 1    (a notify-only hook; StopFailure output is ignored, so it can't block anything)
Score: 15
Source: scout 2026-10-19

## Problem
`scripts/loop-alert.sh` only handles `Notification` (permission_prompt) and `PermissionDenied`. When a
`/loop /build-ideas` run on the subscription hits its usage limit, gets "overloaded", or is logged out,
the turn ends and nothing is posted. Claude Code has a `StopFailure` hook event for exactly this, with
matcher values such as `rate_limit`, `overloaded`, `authentication_failed`, `billing_error`,
`server_error` and `max_output_tokens`. The installed Claude Code (2.1.302) has it.

## Proposal
- `scripts/loop-alert.sh`: a `StopFailure` case that posts "Loop stopped: API error <type> [agent] in
  <dir>", using the same allow-listed fields, the 10-minute per-session rate limit and the
  `HOMELAB_LOOP=1` gate. Never the prompt or the error body beyond the type.
- `.claude/settings.json`: a `StopFailure` entry (matcher `*`) running the same script.
- This writes under `.claude/`, so the plan goes to the `ideas/terminal/` lane and Dan builds it with
  `/build-ideas <slug>`.
- Update the "Stall alerts" section in `docs/m5-pipeline.md` and the script's header comment.

## Existing tools checked
- Claude Code hooks reference (https://code.claude.com/docs/en/hooks): `StopFailure` has no decision
  control and its output is ignored; fits a notify-only hook.
- Claude Code CHANGELOG (https://raw.githubusercontent.com/anthropics/claude-code/refs/heads/main/CHANGELOG.md):
  2.1.303 is the latest, 2.1.302 installed; no upgrade needed for this.
- Existing `loop-alert.sh` (done idea `loop-stall-alert`): reused as is, one more event.

## Rough plan
1. Add the `StopFailure` case to `loop-alert.sh` (read the error type field from the hook JSON; fall back
   to "unknown").
2. Add the settings entry by hand in a terminal (protected path).
3. Test with `HOMELAB_LOOP=1 LOOP_ALERT_DRY=1` and a hand-made StopFailure JSON on stdin; check the rate
   limit and that it stays silent without the gate.
4. Docs: `docs/m5-pipeline.md` "Stall alerts"; CLAUDE.md's loop-alert line names the new event.

_Approved on the dashboard, 2026-10-19._

## Plan
Goal: post one Discord line when a `HOMELAB_LOOP=1` session's turn ends on an API error (usage limit, overloaded, logged out and so on), using Claude Code's `StopFailure` hook.
Kind: change to scripts/loop-alert.sh plus the Claude Code hook settings
Files:
- .claude/settings.json: under `"hooks"`, add `"StopFailure": [{"matcher": "*", "hooks": [{"type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/scripts/loop-alert.sh"}]}]` next to `PermissionDenied`. Change nothing else in the file. It must still parse: run `python3 -m json.tool` on it.
- scripts/loop-alert.sh:
  - Header "Events:" line: add `StopFailure` (API error type only).
  - New case `StopFailure)`:
    - `etype="$(field '.error' | tr -cd 'a-z_')"`, and if that is empty, `etype=unknown`.
    - `msg="Loop stopped: API error $etype"`.
    - The usual ` [$agent]` and ` in <dir>` suffixes are added after the case, as now.
    - Never read `error_details`, `last_assistant_message` or `transcript_path`.
  - Rate-limit stamp: keep a separate one for StopFailure, `stamp="$sid.stop"` (other events keep `$sid`), so a permission-prompt post just before doesn't swallow the stop alert. The rule stays one post per stamp per 10 min, as the note asks.
  - Use `$stamp` in the read and write of `$dir/...`.
  - Everything else stays as it is: the gate, `exit 0` everywhere, and the dry run.
- docs/m5-pipeline.md, "Stall alerts":
  - Add a sentence: a turn that ends on an API error (`StopFailure`: rate_limit, overloaded, authentication_failed, billing_error and so on) posts "Loop stopped: API error <type>". Only the type is sent, never the error text. It has its own 10-min limit per session.
  - Add the `StopFailure` entry to the settings snippet.
- CLAUDE.md:
  - Line 31 (the `loop-alert.sh` scripts entry): "...waits on a prompt, auto mode denies a call or a turn stops on an API error...".
  - Line 89: "Hooks `Notification` (permission_prompt), `PermissionDenied` and `StopFailure` run `scripts/loop-alert.sh`."
New service: None
New env vars: None
Checks the builder must run:
- `bash -n scripts/loop-alert.sh`
- `python3 -m json.tool .claude/settings.json >/dev/null`
- Dry run with its own state dir:
  - Set `XDG_RUNTIME_DIR=<scratch dir>`, then pipe `{"session_id":"t1","cwd":"/x/.worktrees/foo","hook_event_name":"StopFailure","error":"rate_limit","error_details":"429 secret","last_assistant_message":"API Error: x"}` into `HOMELAB_LOOP=1 LOOP_ALERT_DRY=1 scripts/loop-alert.sh`.
  - Expect exactly `Loop stopped: API error rate_limit in foo`.
  - Run it again: no output (rate-limited).
- The same input without `HOMELAB_LOOP`: no output and no state file.
- With `"error"` missing, and with `"error":"rate limit; rm -rf"` (new session ids): `...API error unknown...` and `...API error ratelimitrm...`. No details text in either.
- A Notification permission_prompt dry run on session `t2`, then a StopFailure on `t2`: both print.
Review focus:
- `error_details` or `last_assistant_message` carry account or prompt text -> never read, never posted.
- `error` field missing, empty or odd characters -> type `unknown` or sanitised `[a-z_]`, still exit 0.
- Loop retries after a rate limit and fails again and again -> at most one post per session per 10 min; the extras go to syslog.
- A permission-prompt alert was posted minutes before -> the StopFailure alert still posts (separate stamp).
- Interactive session (no `HOMELAB_LOOP=1`) -> silent, no state written.
Docs: the docs/m5-pipeline.md "Stall alerts" section and its settings snippet; CLAUDE.md lines 31 and 89.

## Manual steps
- The plan writes `.claude/settings.json`, so it goes to the `ideas/terminal/` lane. Dan builds it with `/build-ideas loop-stopfailure-alert` in a terminal.
- Restart the loop session (`HOMELAB_LOOP=1 claude`) so the new hook loads.

## Build in a terminal 2026-10-19

Planned files under .claude/ (Claude Code asks before each write there, and
nobody sees that in the background loop):
- .claude/settings.json

## Review notes
1. /home/dan/homelab/.worktrees/loop-stopfailure-alert/scripts/loop-alert.sh:2-3: the header's opening sentence still says "waits on a permission prompt or auto mode denies a call". The Events line does list StopFailure, but the first line could also say "or a turn stops on an API error".
2. /home/dan/homelab/.worktrees/loop-stopfailure-alert/docs/m5-pipeline.md:55: the rewrapped "Stall alerts" paragraph has one line well over the wrap width of the lines around it. Cosmetic only.
3. The plan's expected output for `"rate limit; rm -rf"` was `ratelimitrm`. The script actually gives `ratelimitrmrf`, which is the correct result of `tr -cd 'a-z_'`. The plan had a typo; the code is fine.
4. If `error` is a JSON object, `jq -j` prints it as compact JSON and the sanitiser cuts it to letters (for example `{"x":1}` becomes `x`). It is harmless and still exits 0, though `unknown` would be tidier.

## Declined to judge
- Posting a StopFailure from an interactive session that started with HOMELAB_LOOP=1 inherited from the parent shell: it's the same gate as the existing events, so it's outside this plan.
