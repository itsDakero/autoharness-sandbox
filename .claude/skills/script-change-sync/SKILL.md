---
name: script-change-sync
description: Use when changing a scripts/ script's flags or usage text.
category: repo-maintenance
---

# Keep a script's docs in step with the script

A change to a script's flags, usage, or exit behaviour is not done until every place that describes it matches. Do this in the same change, not as a follow-up.

1. Update the script's line in the CLAUDE.md `scripts/` list (keep the list alphabetical; new scripts go in their spot).
2. Find every other mention with the Grep tool, path = repo root, and fix live docs (`docs/`, CLAUDE.md, the Commands block in `docs/m5-pipeline.md`). Leave dated `ideas/done/` notes as they are; they record history.
3. Keep existing callers working. If another script calls the changed one (e.g. `deploy-idea.sh` calling `--apply`), do not rename or remove the flag it uses.
4. Help text: `-h|--help` prints the header comment block, the usage line lists every valid flag, and bad arguments exit 2. Document the exit codes in the header.
5. Verify one command per Bash call (see `bash-command-shape`). If a check is refused, report it as not run and list it for the user.
