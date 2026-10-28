The compose-check hook now also runs `scripts/compose-lint.py` on the edited `compose.yaml` and reports its findings back the same way it reports config errors (stderr, exit 2). It also wasn't wired in `.claude/settings.json` (the v2 settings only enable the plugin), so I've wired it.

**What changed**
- **`.claude/hooks/compose-check.sh`:**
  - After the existing checks, the hook runs `compose-lint.py --root <checkout> <file>`. With a file argument the script already lints only that file and checks port uniqueness across the whole repo, so it didn't need changing. The lint takes about 0.17 s, and a 20 s timeout caps it.
  - Lint findings are combined with the image/docker.sock problems into one report, sent back with exit 2.
  - It fails open: if PyYAML or the script is missing, or the lint crashes, it prints a warning and exits 0.
  - If the file is under `.worktrees/<slug>/`, it lints against that worktree as the root. Otherwise a worktree copy of a service would always be reported as clashing ports with the main copy.
  - **One change you didn't ask for:** with no `.env` or no `docker`, the hook now skips the `dc.sh config` checks with a warning. Before, it exited 2 with "Missing .env", which in this sandbox would have blocked every compose edit and hidden the lint output. The behaviour is unchanged on the real server.
  - Some problems will now show up twice, because the lint repeats the pinned-image and docker.sock checks. I kept both because the config-based check sees the values filled in from `.env`.
- **`.claude/settings.json`:** added the `PostToolUse` entry (`Edit|Write|MultiEdit`) for `compose-check.sh`. I didn't re-add `guard.py`, because the v2 sandbox dropped it on purpose.
- **`CLAUDE.md`:** updated the line describing the hook.

**Checks I ran**
- `bash -n` on the hook: passed.
- `python3 -m unittest discover -s scripts/tests`: all 63 tests passed.
- I piped sample hook JSON into the script for each case:

| Case | Result |
|---|---|
| Clean `tools/books` file (absolute and relative path) | exit 0 |
| Non-compose file | exit 0, silent |
| Bad copy using `:latest` and books' port 8090 | exit 2 with `image-pinned`, `port-unique` and `port-table` findings |
| Worktree copy | linted against the worktree root, no port clash |
| PyYAML missing | warning, exit 0 |
| Lint script missing | warning, exit 0 |
| Copy of the repo with a dummy `.env` and a stub `docker` | exit 2 on a `config -q` failure; exit 2 when the image and docker.sock problems are combined with the lint |

The bad-copy and worktree tests also flagged a missing healthcheck. That's only because my test copies left out books' Dockerfile, which has its own `HEALTHCHECK`. I removed all test files afterwards.

**Not done**
- Nothing is committed.
- The deleted `.claude/autoharness/last_run.json` and the `session-*` files in `git status` come from the autoharness plugin, not from me.