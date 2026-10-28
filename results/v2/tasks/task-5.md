I've added `scripts/check.sh` and the CI workflow, and `scripts/check.sh` passes locally: all 5 steps PASS, exit 0. The workflow itself hasn't run on GitHub yet.

**What changed**
- **`scripts/check.sh`** (new, executable) runs these steps in order:
  1. `bash -n` on `scripts/*.sh` and `.claude/hooks/*.sh`
  2. `python3 -m py_compile` on `scripts/*.py`
  3. shellcheck on the same shell files. If shellcheck isn't installed, the step shows as SKIP with an install hint and doesn't count as a failure.
  4. `scripts/compose-lint.py`
  5. `python3 -m unittest discover -s scripts/tests`

  Every step runs even if an earlier one fails. It ends with a PASS/FAIL/SKIP line per step and exits 1 if anything failed. The `py_compile` step writes its compiled files to a temporary folder that gets deleted, so it leaves nothing in the repo.
- **`.github/workflows/check.yml`** (new) runs on push and pull_request on `ubuntu-latest`. It installs `shellcheck` and `python3-yaml` with apt, then runs `scripts/check.sh`. `actions/checkout` is pinned to `v4.2.2`.
- **`CLAUDE.md`**: added a `check.sh` line to the scripts list, in alphabetical order between `cert-expiry-check.sh` and `compose-lint.py`.

**Checks I ran**
- **First run:** shellcheck failed on `check.sh` itself (SC2164, an unguarded `cd`). I changed it to `cd "$REPO" || exit 1`, and the re-run passed: 63 tests OK and no compose-lint findings.
- **Failure path:** with a deliberately broken `.py` file added and shellcheck removed from `PATH`, the output was "FAIL py_compile" and "SKIP shellcheck (not installed)" with exit 1. I deleted the broken file afterwards.
- **Workflow file:** it parses as valid YAML.

**Left undone**
- No commit or push, as asked.