# Claude Code kit (`.claude/`)

Reference for the skills, agents, hooks and permissions under `.claude/`. `CLAUDE.md` keeps only the rules a
session needs every time; this is the detail. Update it when a skill, agent, hook or permission rule changes.

- Skills (user-invoked): `/add-service <idea>`, `/add-cron-job <name>` (script, `scripts/cron.d/` entry, Kuma push
  fragment, README bullet, sandbox checks; follows `docs/new-cron-job.md`), `/remove-service <name>`, `/debug-service <name>`
  (read-only), `/update-stack [name]`, `/build-ideas` (background loop, run as `/loop /build-ideas`: subagents
  `idea-planner` (Opus), `idea-researcher` (Sonnet, when the planner says RESEARCH), `idea-builder` (Sonnet),
  `idea-reviewer` (Opus) in `.claude/agents/`; reviewed builds wait on `idea/<slug>` branches for
  `scripts/deploy-idea.sh`; plans that write under `.claude/` go to `ideas/terminal/` instead (protected path:
  a background builder stalls on the prompt), and Dan builds them with `/build-ideas <slug>`; see `docs/m5-pipeline.md`), `/scout [topic]` (M6:
  `idea-scout` (Opus) sweeps AI tech, a homelab audit and GitHub, writes 3 proposals to `ideas/proposed/`; the
  loop runs it on Fridays; see `docs/m6-research.md`).
- `scripts/kuma-status.py [name]`: Kuma monitors, heartbeats and attached notifications, read-only from the DB.
- Hook `guard.py` (PreToolUse) blocks: reading/editing `.env`; commands that print secrets indirectly
  (`compose config` without `-q`, `docker inspect` without a safe `--format`, container env dumps,
  `/proc/*/environ`, recursive grep without `--exclude`); `sudo`; writes to `/mnt/media`; `docker.sock` outside
  the socket proxy; `:latest`/untagged images; `ANTHROPIC_API_KEY`. A media mount without `:ro` asks first.
  Fails closed (`onFailure: block`, 10 s timeout): a guard crash or timeout blocks the call.
  Tests: `python3 -m unittest discover -s scripts/tests` (`test_guard.py`, blocked/allowed/ask cases).
- Hooks `Notification` (permission_prompt), `PermissionDenied` and `StopFailure` run `scripts/loop-alert.sh`.
- Hook `compose-check.sh` (PostToolUse) runs `config -q` after every `compose.yaml` edit and re-checks the
  whole file (pinned images, docker.sock), then `compose-lint.py` on it (its findings + repo-wide port-unique;
  skipped with a warning if PyYAML or the script is missing). Read-write media mounts are approved via the guard's ask.
- Hook `stop-check.sh` (Stop, after hookify's "require tests before stopping"): if `git status` shows changes under
  `scripts/`, `.claude/hooks/` or to any `compose.yaml`, and the transcript (`transcript_path`) has no Bash call running
  `scripts/check.sh`, `unittest` or `compose-lint.py` after the last Edit/Write of such a file, it blocks the stop once
  and asks Claude to run `scripts/check.sh`. Never blocks twice in a row (`stop_hook_active`). Fails open (no jq, no
  transcript, not a git checkout, bad input: exit 0). Test by piping `{"transcript_path":…,"stop_hook_active":false}`
  with a fake JSONL transcript.
- Permissions: git, `dc.sh` config/ps/logs and homelab `curl` run freely; up/down/stop/restart ask;
  `rm -rf`, `sudo`, reading `.env` and `dc.sh` up/down/build/… on `.worktrees/*` are denied. Exception: `dc.sh core/dashboard` build/up/restart run
  freely. Ask rules beat allow rules and can't say "except", so the up/down/stop/restart ask rules name
  each other core service (incl. `core/omada`): **a new core service must be added there**
  (`media/*`, `tools/*` are wildcards; `games/*` still needs adding).
