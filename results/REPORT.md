# Autoharness sandbox — report

Plugin: `autoharness@autoharness` v0.5.3, default settings.
All 15 tasks ran. Each was a fresh `claude -p … --permission-mode acceptEdits` session from the repo root.
Per-task details: `results/log.md`.

## Short version

- The plugin made **3 skills** and rejected **12 other proposals**.
- 1 skill is useful (`rules-audit`), 1 is so-so (`script-change-sync`), 1 is mostly noise (`bash-command-shape`).
- Its "only touch my own skills" check **worked**: it tried to edit your `add-service` and `remove-service` skills 15 times, and every attempt was blocked.
- Biggest risk: it writes **global** skills to `~/.claude/skills/`. On your real machine, that means every project, not just homelab.
- Cost: **15 background `claude -p` runs** (one reflection per task), each started by the plugin. No curator runs.

## Skills it created

| Skill | Layer | Summary | Verdict |
|---|---|---|---|
| `bash-command-shape` | **global** (`~/.claude/skills/`) | Long list of Bash command shapes that got refused, and what to do instead. Created in task 1, patched 13 times. | **Noise.** It learned this sandbox's permission quirks (see "Caveats"). Your real setup has a working allow list, so most of it would be wrong there. |
| `script-change-sync` | project | When a script's flags change, update the CLAUDE.md script list and docs, keep callers working, standard `--help` and exit 2. | **Somewhat useful.** Correct, but mostly restates CLAUDE.md. |
| `rules-audit` | project | Checklist to review a diff against CLAUDE.md: file modes, pinned images, docker.sock, `.env`, ports, ask rules, docs index, leftovers. | **Useful.** Good checklist. Has one broken link (below). |

Copies: project skills in `.claude/skills/`; the global one in `results/global-layer/skills/`
(the original lives outside the repo, so it dies with the container).

## Proposals it rejected (12)

| Proposal | Times | Why rejected |
|---|---|---|
| patch `add-service` (your skill) | 13 | `self_produced` — not its skill |
| patch `remove-service` (your skill) | 2 | `self_produced` + `safety` |
| create `add-cron-job` | 4 | `structure`, sometimes `safety` |
| create `cron-job-setup` | 1 | `safety` + `structure` |
| create `restore-service-appdata` | 1 | `structure` |
| create `guard-hook-tests` | 1 | `structure` |
| create `idea-note-writing` | 1 | `structure` |
| patch `bash-command-shape` | 2 | `structure` |

- The run files only keep the category name, not the detail. So I can't say what tripped `safety`.
- The cron-job skill was the most wanted (5 tries across tasks 1, 2, 13, 15) but never landed.

## Conflicts with CLAUDE.md or the guard

- **No skill told the agent to break a rule.** None suggested `sudo`, reading `.env`, `:latest`, or `docker.sock`.
- `bash-command-shape` agrees with the guard (use the Grep tool, add `--exclude='*.env'`).
- `rules-audit` restates CLAUDE.md correctly.
- **Broken link:** `rules-audit` says "follow the `cron-job-setup` skill". That skill was rejected in the same run, so it doesn't exist.
- **Overlap:** your hand-written skills (`add-service`, `remove-service`) cover the same ground the plugin kept trying to change. It can't edit them, so it may grow rival skills over time instead.

## Surprising or unsafe things

- **Global layer by default.** The first skill went to `~/.claude/skills/`, not the repo. On your Mac/server, every project would load it. Set `AUTOHARNESS_DISABLE_GLOBAL=1` if you try it for real.
- **It learned the environment, not the work.** 14 of its 16 landed changes were about refused Bash commands. Little was about homelab patterns.
- **Skill bloat.** `bash-command-shape` grew from 7 rules to about 20 in 15 sessions. Its description also grew to fire "before chaining Bash commands", so it loads a lot.
- **It writes state into the repo.** `.claude/autoharness/` gets lock files, offsets and run logs on every session. That's noise in git unless you ignore it.
- **The reflector runs as `claude -p --agent autoharness:reflector --dangerously-skip-permissions`.** It is fenced by the plugin's own hook (no write tools), but it's still a background session with permissions skipped.
- **It adds context to every session start:** an index of its skills plus the last run summary.
- **My own session picked up its skills too** (same container, global layer).
- Your own skills were left alone: no file under `add-service`, `remove-service`, etc. changed.

## Caveats (read before trusting the verdicts)

- **Untrusted workspace.** Child `claude -p` sessions printed "workspace has not been trusted", so the repo's `permissions.allow` (52 rules) was ignored. Many normal commands (`python3`, `chmod`, `bash -n`, `py_compile`) were refused. That is why `bash-command-shape` exists. In your real repo it would look different.
- **Session ID bug (fixed).** The first task-1 attempt shared this parent session's ID and wrote into its transcript. I killed it, plus the reflector it started, deleted its output and re-ran with `--session-id`. Nothing from that attempt was kept.
- Children could see `SANDBOX.md`, and one mentioned "tasks 3–15". No harm done.

## Task outcomes (the work itself)

- Tasks 1–10, 12–15: done.
- **Task 11 (shellcheck): not done.** All installs were refused. The agent stopped instead of guessing (good).
- **Task 10:** the agent couldn't run its tests. I ran them after: 20 tests, all pass.
- **Task 15** found the 3 new cron scripts were not executable (`100644`). The child couldn't `chmod`; I fixed it in the final commit.
- Most tasks couldn't run their own checks (`config -q`, `py_compile`) because of the untrusted workspace. They said so clearly.

## Usage

- Background `claude -p` runs started by the plugin: **15 reflections** (+1 killed in the aborted first attempt), **0 curator runs** (that fires every 250 requests; we reached 15).
- Task sessions: 15. About 250 tool calls in total (see `results/log.md`).
- Each reflection finished before the next task started.

## Recommendation

- Not worth adding to the real homelab as is.
- If you try it: set `AUTOHARNESS_DISABLE_GLOBAL=1`, git-ignore `.claude/autoharness/`, and review `.claude/skills/` diffs before merging.
- Worth keeping by hand: copy the `rules-audit` checklist into your own skill, and drop the `cron-job-setup` line.
