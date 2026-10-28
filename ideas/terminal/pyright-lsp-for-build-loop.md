# Pyright diagnostics for the build loop (official pyright-lsp plugin)

Value: 3   (builders see wrong names/attributes/signatures on every .py edit, before review; fewer fix commits)
Effort: 2  (user venv + plugin enable + a pyrightconfig.json; terminal-lane plan)
Risk: 1    (user-level tool and project settings; no containers, no network at run time)
Score: 12
Source: scout 2026-10-26

## Problem
The repo has 107 tracked `.py` files, 20,512 lines (dashboard, scripts, tools/*). Builders only check them with
`py_compile`, `bash -n` and `config -q`, which miss wrong names, bad attribute access and wrong call signatures.
Since 2026-10-12, 16 of 298 commits are "fix" commits. Neither pyright nor node is installed, and
`.claude/settings.json` has no `enabledPlugins`.

## Proposal
Install `pyright[nodejs]==1.1.414` (bundled Node via nodejs-wheel) in a user venv and link
`pyright-langserver` into `~/.local/bin`. Enable `pyright-lsp@claude-plugins-official` in the project settings so
Claude Code reports "Found N new diagnostic issues" after each Edit/Write. Add a root `pyrightconfig.json`
(`typeCheckingMode: basic`, `reportMissingImports` off, since fastapi etc. live only in containers). Confirm the
wrapper doesn't fetch the npm package on first run; if it does, fall back to basedpyright. Optionally add
`pyright <changed files>` to the builder's checks. Writes under `.claude/`, so it goes to `ideas/terminal/`.

## Existing tools checked
- pyright-lsp (https://github.com/anthropics/claude-plugins-official/tree/main/plugins/pyright-lsp): official
  plugin, needs a separate `pyright-langserver`; docs https://code.claude.com/docs/en/plugins/code-intelligence.md
- pyright (https://pypi.org/project/pyright/): 1.1.414, released 2026-09-10, MIT, `[nodejs]` extra; chosen.
- basedpyright (https://pypi.org/project/basedpyright/): 1.40.2, released 2026-10-04, MIT; fallback.

## Rough plan
1. User venv with the pinned pyright, symlink, version check; document in docs/m5-pipeline.md.
2. pyrightconfig.json; run once over the repo and record the baseline count (don't fix everything now).
3. Enable the plugin in project settings; check a builder sees diagnostics on a deliberate bad edit.
4. Optional: builder check line for changed files only.

_Approved on the dashboard, 2026-10-26._

## Plan
Goal: Pyright diagnostics after every .py Edit/Write in Claude Code (official pyright-lsp plugin), plus a pyright check line for builders. This is a terminal build because it writes under `.claude/`.
Kind: script/cron (a user-level setup script) plus a change to the Claude Code kit
Files:
- scripts/pyright-setup.sh: new, idempotent, runs as dan with no sudo (see below)
- pyrightconfig.json: new, at the repo root
- .claude/settings.json: add a top-level `"enabledPlugins": {"pyright-lsp@claude-plugins-official": true}`. Change nothing else.
- .claude/agents/idea-builder.md: in "## Checks", after the py_compile line, add: "If `pyright` is on PATH: `pyright <changed .py files>`. Fix errors on lines you added or changed; report the count of other errors, but don't fix those."
- docs/m5-pipeline.md: new `### Pyright diagnostics` subsection at the end of Stage C (just before `## Stage D`)
- scripts/README.md: add a `pyright-setup.sh` bullet in alphabetical order (between `media-cleanup.py` and `qbit-setup.py`: "user runs once: pyright venv + `~/.local/bin` wrappers for the pyright-lsp plugin; prints the repo's baseline"). In `docs/claude-kit.md` (the kit detail moved out of CLAUDE.md), add one line: "Plugin `pyright-lsp` (enabled in project settings) reports type diagnostics after .py edits; needs `scripts/pyright-setup.sh`."

scripts/pyright-setup.sh (`set -euo pipefail`):
1. Settings: `VENV=$HOME/.local/share/pyright/venv` and `PIN='pyright[nodejs]==1.1.414'` (PyPI, https://pypi.org/project/pyright/; version taken from the note's scout check).
2. Check venv support with `python3 -c 'import ensurepip'`. If that fails, print "python3-venv missing: run sudo ./bootstrap.sh first" and exit 1. (bootstrap.sh already installs python3-venv at line 30. Today it is not installed, so bootstrap hasn't been re-run.)
3. Create the venv only if `$VENV/bin/python` is missing. Then run `$VENV/bin/pip install -q "$PIN"`. pip skips this when the pin is already installed.
4. Write two wrapper scripts, `~/.local/bin/pyright` and `~/.local/bin/pyright-langserver`, mode 0755. Use wrapper scripts, not symlinks. Each one is `#!/bin/sh`, then `export PYRIGHT_PYTHON_IGNORE_WARNINGS=1` (no PyPI "new version" check on each run), then `exec "$VENV/bin/<name>" "$@"`. Rewrite them on every run.
5. Warm-up: run `~/.local/bin/pyright --version`. If the wrapper needs to fetch its npm package, it does so now, once, into its cache, while there is network. Print the version and fail if it doesn't contain 1.1.414.
6. Baseline: `cd` to the repo root (the script's dir/..), run `pyright --outputjson`, and print one line: "baseline: N errors, M warnings in K files". Pyright exits non-zero when it finds errors; that must not end the script.
7. Running the script again changes nothing and prints the same lines.

pyrightconfig.json:
- `typeCheckingMode: "basic"`
- `pythonVersion: "3.12"`
- `reportMissingImports: false`
- `reportMissingModuleSource: false`
- `exclude`: `.worktrees`, `ideas`, `**/.venv`, `**/__pycache__`, `**/node_modules`

New service: None
New env vars: None
Checks the builder must run:
- `bash -n scripts/pyright-setup.sh` (and `shellcheck` if installed)
- `python3 -c 'import json;json.load(open("pyrightconfig.json"));json.load(open(".claude/settings.json"))'` in the worktree
- `git diff main -- .claude/settings.json` must show only the enabledPlugins addition
- Don't run the setup script: python3-venv is missing until Dan re-runs bootstrap.
Review focus:
- python3-venv still missing -> clear message pointing to bootstrap.sh, exit 1, and nothing half-written in ~/.local/bin
- Script run twice -> no reinstall, same wrappers, same output
- Baseline pyright run finds errors (non-zero exit) -> the count is printed and the script still exits 0
- pyright not on PATH (setup not run yet) -> the builder skips the pyright line instead of failing the build
- settings.json edit drops or reorders permission/hook entries -> must not happen; the diff is only the new key

Docs:
- docs/m5-pipeline.md, new `### Pyright diagnostics` section: what it does, where the venv lives, the wrappers and why (the plugin runs `pyright-langserver --stdio`; the env var stops a PyPI check on each run), how to re-run the setup, how to bump the pin (edit PIN, re-run), the baseline (not to be fixed in bulk), and the fallback (basedpyright, with `pyright-langserver` pointing to `basedpyright-langserver`) if the warm-up ever fails.
- CLAUDE.md: the two lines above. docs/README.md is unchanged (no new doc).

## Manual steps
1. `sudo ./bootstrap.sh`. It installs python3-venv, which bootstrap.sh already lists but which isn't installed on the host today.
2. `scripts/pyright-setup.sh`. Note the baseline line it prints.
3. Restart Claude Code, so the loop's tmux session `ideas` picks up the plugin. In `/plugin`, confirm pyright-lsp is enabled. The marketplace `claude-plugins-official` is already known at user level.
4. Spot check: in a scratch worktree, make a deliberate bad edit (for example call an undefined name in a .py file). "Found N new diagnostic issues" should appear. If it doesn't for files under `.worktrees/` (the root config excludes that path), tell the loop and we drop `.worktrees` from `exclude`.

## Build in a terminal 2026-10-26

Planned files under .claude/ (Claude Code asks before each write there, and
nobody sees that in the background loop):
- .claude/settings.json
- .claude/agents/idea-builder.md
