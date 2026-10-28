The linter now runs clean on the repo (exit 0). It flagged two things and both turned out to be false positives, so I fixed the linter and left both compose files unchanged.

**What it found:** adguard and omada have no `logging:` block. `docs/m1-core.md:172` says that's on purpose: both are on the always-manual list, and you add the block by hand if you want it. The linter already read the healthcheck exceptions from that doc but not this logging one. Adding the blocks myself would have meant editing always-manual services and recreating adguard, which drops DNS briefly.

**What changed:**
- **`scripts/compose-lint.py`**: a new `logging_exceptions()` reads the "Container logs are capped" bullet in `docs/m1-core.md` and takes the names from "… are left out on purpose". Those services are skipped for `logging-cap` only. The help text says so too.
- **`scripts/tests/test_compose_lint.py`**: one new test. Services named in that bullet are skipped. A service still gets flagged if it's listed as a healthcheck exception, or if "left out on purpose" appears in some other bullet.
- **`CLAUDE.md`**: the `compose-lint.py` line now says the m1-core exceptions cover the logging cap as well as healthchecks.

No healthcheck findings came up, so `docs/m1-core.md` didn't need anything new.

**Checks:**
- `python3 -m py_compile scripts/compose-lint.py`: OK.
- `python3 scripts/compose-lint.py`: no findings, exit 0.
- `python3 -m unittest discover -s scripts/tests`: 63 tests, all pass.
- `--help`: shows the new text.

The exception depends on that sentence's wording. If someone rewrites "adguard and omada are left out on purpose", the two findings come back; it fails loudly, not silently. Nothing is committed. The changes under `.claude/autoharness/` and `.claude/skills/script-change-sync/.sidecar.json` came from the session tooling, not from me.