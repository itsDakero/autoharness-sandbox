I've written `scripts/compose-lint.py` and 62 unit tests. Run on the current repo it finds two problems: adguard and omada have no logging cap. Nothing is committed and I didn't fix either finding.

**Findings on the current repo** (exit 1):
```
core/adguard/compose.yaml:3: logging-cap: adguard: no logging: block (json-file, max-size 10m, max-file 3)
core/omada/compose.yaml:2: logging-cap: omada: no logging: block (json-file, max-size 10m, max-file 3)
```
`docs/m1-core.md` already says adguard's cap is added by hand, because recreating the container drops DNS for a moment. Omada's gap isn't explained anywhere.

**What changed**
- **`scripts/compose-lint.py`**: one line per finding, as `file:line: rule: detail`. Exit 0 when clean, 1 on findings, 2 on a usage error; `--help` prints the header. `--root DIR` points it at another repo, and you can pass single files. Port uniqueness is always checked across the whole repo. The header credits DCLint and compose-lint for ideas only, no code.
- **`scripts/tests/test_compose_lint.py`**: builds small temp repos, each with its own CLAUDE.md, m1-core.md and compose files, then runs the script as a command.
- **`CLAUDE.md`**: the script's line is in the scripts list, alphabetically after `cert-expiry-check.sh`.

**Rule choices you may want to check**
- **Approval comments:** the arr apps and qbittorrent write "approved via the guard" on the comment lines just above the mount, not on the mount line itself. So the linter also accepts an "approved" comment in the comment block directly above a mount. Without that, all five would be flagged.
- **Media sources:** `${MEDIA_PATH}` counts as `/mnt/media`.
- **Healthcheck exceptions:** these come from the "left alone: …" and "Skipped: …" sentences in `docs/m1-core.md`. The linter also accepts a `HEALTHCHECK` in a locally built service's Dockerfile, so books, fpl and lms pass, though m1-core.md doesn't list them.
- **Traefik:** omada runs on the host network, so it doesn't need Traefik labels. Traefik itself routes to `service=api@internal`, so it doesn't need a loadbalancer port.
- **Uptime Kuma:** any `kuma.<id>.<type>.name` label counts, not only an http monitor.
- **Ports table:** the table row must name either the service or its directory (the 8083 row names qbittorrent).
- **Build-only services:** a service with `build:` but no `image:` is flagged, because the image it builds is tagged `:latest`.

**Checks run**
- `py_compile` on both files passes.
- All 62 tests pass with `python3 -m unittest discover -s scripts/tests`, including the existing guard tests.
- Writing the tests caught one bug, now fixed: mapping-style `traefik.enable: true` was read as "True".
- `--help` exits 0 and a bad flag exits 2.

**Not done**
- I couldn't read either upstream README (WebFetch got a 403 and GitHub access was refused). So the header credits only general ideas like rule ids and the socket-mount check, not specific upstream rules.
- The linter isn't hooked into `compose-check.sh` or anything else yet.
- The `.claude/autoharness/` changes in `git status` weren't made by me in this task, so I left them alone.