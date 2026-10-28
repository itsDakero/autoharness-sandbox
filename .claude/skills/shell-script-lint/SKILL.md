---
name: shell-script-lint
description: Use when running shellcheck or fixing bash SC#### warnings.
category: repo-maintenance
---

# Shell script lint (shellcheck)

Fix real findings in the code. Suppress only the intentional patterns, each with a targeted directive and a one-line reason. Never change behaviour to silence a warning.

- Check `command -v shellcheck` first. It is a standard apt package. Run `shellcheck scripts/*.sh .claude/hooks/*.sh`, then `bash -n` on every changed file, then the unit tests if they exist.
- A `# shellcheck disable=SCxxxx` directive covers only the next command. Put it on its own line directly above the failing line, with the reason on the line above the directive. A trailing `# reason` on the directive line does not work.
- If a failing line holds several commands (`set -a; . file; set +a`), split it onto separate lines first so the directive lands on the command that needs it.
- Intentional patterns to suppress, not rewrite:
  - SC2015 `A && B || C` where C is the deliberate fallback (die, continue, log and exit).
  - SC2064 when a trap must expand a local variable now.
  - SC1090/SC1091 when sourcing a root-only or git-ignored env file that is not in the repo: `# shellcheck source=/dev/null`.
  - SC2001 `sed 's/^/  /'` indenting every line of a multi-line string, which a parameter expansion cannot do.
- Real fixes: SC2001 on a single substitution becomes `${var//a/b}`. SC1010 on a bare `done` used as a loop word gets quoted.
- A function whose name matches an argument to an external command (`attach()` alongside `tmux attach`) causes false SC2032/SC2033. Rename the function and update its callers.
