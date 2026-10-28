---
name: bash-command-shape
description: Use when a Bash call is refused or needs approval.
category: tool-usage
---

# Bash command shape under the permission matcher

Keep each Bash call to one plain command with absolute paths. The matcher refuses shapes it cannot check statically; a refusal says nothing about whether the command is safe.

- Use absolute paths. Never `cd dir && cmd` or two `cd`s in one call. Relative reads after a `cd` are refused (`cd-compound-read`, `multi-cd`).
- Do not assign shell variables in the same command that uses them. Inline the literal path (`assigned-variable`).
- Do not chain several distinct operations with `&&` or `;` (syntax check, generate, run, list). Make one call per step (`too-complex`, `no-rule-match`).
- An inline env prefix (`VAR=x docker compose ...`) is refused like an assignment; pass values through `.env` or ask the user to run it.
- A plain `python3 -c "..."` with no pipe was still refused ("requires approval"). To read a YAML or JSON file, use Read or Grep instead.
- Do not start background servers and kill them with `pkill -f` in the same call. Run them as separate calls, and report any step that was refused.
- A raw `docker compose --env-file <path> -f <path> config -q` was refused ("requires approval", `no-rule-match`). Use the project's own compose wrapper with its default env instead, or hand the exact command to the user.
- `command -v X && ... || ...` chains are refused as shell operators ("uses shell operators that require approval"). Split into single calls, or use Read/Grep to inspect files.
- Read files with the Read tool (`offset`/`limit`) instead of `cat`/`head` when the path is relative or the call is compound.
- Search with the Grep tool, not `grep -r`: the homelab guard blocks recursive grep that could read `.env`. Fetch remote JSON with WebFetch or one plain `curl -sS <url>`; `curl ... | python3 -c` and `$(...)` tokens count as several operations and are refused.
- File-mode changes (`chmod +x`) can be refused too. Do not retry; list the exact command as a step for the user to run.
- Searching for a term across the repo: use the Grep tool (with `path` and `glob`) and Glob for file listings. Observed refusals in one session: `grep ...; ls ...; git status --short` was denied by a project permission rule; `grep -rli <term> <abs path> --exclude-dir=...` was denied the same way; `git -C <dir> grep ...` and `git -C <dir> status --short` needed approval (`no-rule-match`). A single `ls -la <abs path>`, `rm <abs file>` and `rmdir <abs dir>` went through.
- After a refusal, do not retry the same string. Re-issue the simplest single command. If it is still refused, state that the step did not run.

Observed reason codes and what triggered them: references/rejection-codes.md
