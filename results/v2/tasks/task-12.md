I added `scripts/tests/test_ops_actions.py` with 21 tests for the decision logic, and they all pass. `scripts/ops-actions.py` itself is unchanged: the tests swap out its Docker, Discord, ntfy, syslog and clock calls from outside, so no refactor was needed.

**What the tests cover:**
- **Unhealthy for 1 vs 2 checks:** one unhealthy check only counts toward the streak; two in a row restart the service once, reset the streak, and log and announce the restart. A healthy check in between resets the streak. A container that is unhealthy but not running is ignored, and a failed `dc.sh` check leaves the streak as it was.
- **1 restart per hour per service:** a second restart within the hour is refused and "needs Dan" goes to Discord once. It isn't sent again on the next run, it clears when the service turns healthy, and a restart is allowed again after an hour.
- **3 restarts per day per service:** a fourth is refused. Once a restart is more than 24 hours old it no longer counts, so another restart is allowed.
- **Breaker:** with 3 restarts already in the last hour, the next one writes PAUSE, alerts on Discord and ntfy, logs a "pause" entry, and stops the run so later services are left alone. With only 2 recent restarts, the next restart still goes ahead.
- **PAUSE:** when PAUSE exists, nothing is restarted, nothing is sent and the saved state is untouched.
- **Core and never-list services:** the real registry contains no `core/` service and none of gluetun, qbittorrent or hermes. If one is slipped in, the script exits with code 2 and restarts nothing. Services outside the registry are never even checked.
- **`--dry-run`:** no restarts or messages are sent, and nothing is written (state, audit log, lock file or PAUSE). It still prints what it would do, including "would write PAUSE" and the cap message.

The script holds its lock file open until it exits, which made Python print "unclosed file" warnings during the tests. The test helper now hides those and closes the file after each run.

**Checks run:**
- `python3 -m unittest scripts/tests/test_ops_actions.py`: 21 tests pass.
- Full test suite (`unittest discover -s scripts/tests`): 94 tests pass.
- `scripts/check.sh`: every step passes (bash -n, py_compile, shellcheck, compose-lint, service-catalog, unit tests).

Not covered: the real `health()` parsing of `dc.sh ps` output, the ntfy and Discord senders, and the "skip if another run holds the lock" path.