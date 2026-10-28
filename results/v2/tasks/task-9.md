I added `scripts/service-catalog.py`, generated `docs/services.md` from it, and wired `--check` into `scripts/check.sh`. The full `check.sh` passes, and the real repo's Ports table matches its labels.

**What the script does**
- **Default run:** reads every `<category>/<service>/compose.yaml` and writes `docs/services.md`, using the same file walk and label parsing as `compose-lint.py`. The file has one table per `homelab.group` with name, path, port, audience and description. External tiles are included without a port, shown as e.g. "(external `mac-mini`)". A final list shows the compose services with no `homelab.*` labels: gluetun, autokuma, the immich and paperless sidecars, and so on.
- **`--check`:** writes nothing and exits 1 on any of these:
  - `docs/services.md` is missing or out of date.
  - A `homelab.port` has no row in the CLAUDE.md Ports table.
  - A Ports row names a different service than the one carrying the label.
  - A Ports row has no `homelab.port` behind it.
- **Exit codes:** 0 when written or up to date, 1 for findings, 2 for usage errors. `--root DIR` and `-h` work.

**One rule I added for "extra" ports:** the table legitimately lists 53, 80, 445 and 8043, which have no `homelab.port` label. So a row without a label still passes if the service it names publishes that port, or runs with `network_mode: host` (Omada does). A row naming a service that doesn't exist, or a port its service doesn't publish, is flagged.

**Other edits**
- `scripts/check.sh`: new `service-catalog` step after compose-lint, and its header comment updated.
- `CLAUDE.md`: a line for the new script in its alphabetical spot, and the `check.sh` line now lists the new step.
- `docs/README.md`: a row for `docs/services.md`.
- `scripts/tests/test_service_catalog.py`: 10 tests covering generation, a stale or missing file, each of the three Ports mismatches, the published-port and host-network cases, usage errors and help.

**Checks run**
- The new tests: 10 OK.
- `bash scripts/check.sh`: every step passed (bash -n, py_compile, shellcheck, compose-lint, service-catalog, 73 unit tests).
- `--check` against the real repo exits 0 after generating.

**Left for you**
- Nothing is committed. The changes under `.claude/autoharness/` and `.claude/skills/script-change-sync/.sidecar.json` in `git status` were already there and aren't mine.
- Whenever a label changes, run `scripts/service-catalog.py` again, or `check.sh` will fail on a stale `docs/services.md`.