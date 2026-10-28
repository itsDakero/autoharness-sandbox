# Patch-level image bumps through the auto-deploy lane

Value: 3   (security/bug-fix patches apply without Dan; majors and minors still come to him)
Effort: 2  (image-check.py already finds newer tags)
Risk: 2    (it changes running images, even if only patch versions)
Score: 12
Source: claude 2026-10-25 (reports/Homelab autonomy and assistant gaps.md, roadmap #6)

## Problem
`scripts/image-check.py` posts a Monday digest of newer tags, and nothing applies them. Patch releases
(x.y.Z) pile up until Dan runs `/update-stack`.

## Proposal
- `image-check.py --propose`: for each image whose newest tag differs only in the patch number (strict
  semver, same tag suffix such as `-alpine`), write one proposal note to `ideas/proposed/` (`Risk: 1`,
  Source `image-check`), one note per service, listing old → new tag and the release-notes link.
- Skip, and keep in the digest only: minor/major bumps, non-semver tags, anything in `core/` that the ask
  rules protect (traefik, docker-socket-proxy, adguard), gluetun, and images on a pin with a comment saying
  why (e.g. the NVIDIA/Jellyfin constraints).
- Dan approves on the Proposed tab as usual; the existing Risk 1 auto-deploy then builds and deploys it.
  Nothing skips Dan's approval.
- Don't propose the same bump twice (check `ideas/`, `ideas/proposed/`, done, rejected and dismissed).

## Notes
- If Dan later wants patches applied without the Approve tap, that is a separate decision, not this note.

## Plan
Goal: `image-check.py --propose` writes one Risk 1 proposal note per strict-semver patch bump to `ideas/proposed/`. Dan approves each one, and the existing Risk 1 auto-deploy then builds and ships it.
Kind: change to scripts/image-check.py (+ its cron line)
Files:
- scripts/image-check.py:
  - Add a `--propose` flag. It works alongside the digest, which still posts as before.
  - `--print --propose` prints the notes it would write and writes nothing.
  - `read_images()` must also return, for each ref, the compose files it is in (repo-relative) and whether its
    `image:` line has an inline `# ...` comment.
  - Add `GITHUB` entries `dgtlmoon/changedetection.io` -> `dgtlmoon/changedetection.io` and
    `wabayang/jelu` -> `bayang/jelu`.
  - Update the docstring.
- scripts/install-cron.sh: change the cron line to `10 9 * * 1 $REPO/scripts/image-check.py --propose # homelab`.
- CLAUDE.md: in the scripts list, change the `image-check.py` entry to add "`--propose`: a Risk 1 note in
  ideas/proposed/ per patch bump".
- docs/m6-research.md: a short "Patch bump proposals (image-check)" paragraph after Stage A's Built list. It
  covers the rules below, the slug format, and that the notes still need Dan's Approve.

When a ref gets a proposal (all of these must hold, otherwise it stays in the digest only):
- The newest candidate (`ok[-1]`, the same tag the digest picks) and the current tag both fully match
  `^v?(\d+)\.(\d+)\.(\d+)(-[a-z][a-z0-9-]*)?$`. The `v` prefix and the suffix are identical (the skeleton
  check already ensures this), major and minor are the same, and the patch number is higher.
  - So linuxserver `x.y.z.b-lsN`, jellyfin's date tags, rc and the like are skipped.
- No compose file of the ref is under `core/`. Not gluetun: add a set `PROPOSE_SKIP = {"gluetun"}`, checked
  against the ref's service names.
- No service of the ref is in `HOLDS`.
- The `image:` line has no inline `#` comment. A comment on the line above doesn't count.
- Not a duplicate. The slug is `bump-<first service>-<new tag>`: lowercase, every run of `[^a-z0-9]` turned
  into `-`, dashes trimmed, cut to 50 chars (e.g. `bump-seerr-v3-5-1`). Skip if `<slug>.md` already exists
  in `ideas/`, or in `ideas/{proposed,done,parked,rejected,terminal}/`, or if `ideas/dismissed/<slug>.md` or
  `<slug>-N.md` exists.
- No proposal is pending for the same service. Skip if any `bump-<first service>-*.md` is still in
  `ideas/proposed/` or `ideas/`, so Dan doesn't get two competing bumps.

A ref used by several services (radarr + radarr-remote, sonarr + sonarr-remote) gets one note that names
every compose file. Notes are written as `REPO/ideas/proposed/<slug>.md`: create the dir if it's missing,
write to `.<slug>.tmp` and then `os.replace`. The note text:
```
# Bump <services joined by " + "> to <new> (patch)

Value: 2   (patch release: bug and security fixes)
Effort: 1  (one image tag)
Risk: 1    (patch bump within <major>.<minor>, same tag flavour)
Score: 10
Source: image-check <YYYY-MM-DD>

## Problem
<compose files> pin `<ref>`; `<new tag>` is out (patch).[ Release notes mention security: <tags>.]

## Proposal
- In <each compose file>, change only the `image:` tag `<cur>` -> `<new>`; nothing else.
- Release notes: https://github.com/<repo>/releases (from GITHUB), else the registry tag page
  (https://hub.docker.com/r/<ns>/<repo>/tags, or https://github.com/<owner>/<repo>/pkgs/container/<name> for ghcr).
- Check: scripts/dc.sh <dir> config -q for each dir. No manual steps.
```
- The digest line of a proposed ref gets ` - proposed (<slug>)` instead of ` - /update-stack <svc>`. A ref
  skipped because a proposal is pending gets ` [proposal pending]`.
- Add one more digest line: `N patch proposals written`.
- Log each note written to syslog.

New service: None
New env vars: None
Checks the builder must run:
- `python3 -m py_compile scripts/image-check.py`
- `bash -n scripts/install-cron.sh`
- `CRON_LIST=/dev/null scripts/install-cron.sh --check`: it is expected to report the missing lines; this is
  only to prove it runs.
- `scripts/image-check.py --print --propose`. It must write nothing: compare `ls ideas/proposed` before and after.
- A unit check with `python3 -c` that imports the module (importlib) and runs the patch-test function on:
  - `v3.5.0` -> `v3.5.1` gives true
  - `v0.9.5-omnibus` -> `v0.9.6-omnibus` gives true
  - `0.60.9` -> `0.61.0` gives false
  - `6.4.4.10685-ls318` -> `6.4.5.10700-ls320` gives false
  - `2.5.6-rootless` (core) is skipped
  - the slug function: `("seerr", "v3.5.1")` gives `bump-seerr-v3-5-1`

Review focus:
- Registry tags are untrusted text that gets written into a note the planner reads -> only tags that fully
  match the strict regex get into a note, and nothing else from the registry or GitHub (release bodies)
  goes in.
- The same bump on later Mondays, or after Dan dismissed or rejected it -> no second note (all dirs
  checked, dismissed `-N` included).
- `--print --propose`, a failed registry lookup, or a GitHub rate limit -> no note written for that ref, the
  digest still posts, and the exit code is the same as before.
- `ideas/proposed/` missing or not writable -> the dir is created, or one log line and the digest still
  posts. No traceback, no half-written `.md` (the tmp file isn't named `*.md`).
- Core, gluetun, held or commented pins, a minor bump that comes out between the current tag and the
  newest -> never proposed. The note must say `Risk: 1` exactly, and no Manual steps, so auto-deploy picks it
  up only after Approve.

Docs:
- CLAUDE.md scripts list (image-check entry).
- docs/m6-research.md: the new paragraph.
- No port or layout changes.

## Manual steps
None. deploy-idea.sh reinstalls the cron line on drift.

Note for Dan:
- This build itself won't auto-deploy: it changes `install-cron.sh` and is Risk 2. That's expected.
- With strict semver, today only changedetection, dozzle, hermes, jelu, scrutiny and seerr can get
  proposals. The linuxserver arr and qbittorrent images and jellyfin will stay digest-only.
- Relevant paths:
  - /home/dan/homelab/.worktrees/image-patch-autobump/scripts/image-check.py
  - /home/dan/homelab/.worktrees/image-patch-autobump/scripts/install-cron.sh
  - /home/dan/homelab/.worktrees/image-patch-autobump/docs/m6-research.md
  - /home/dan/homelab/.worktrees/image-patch-autobump/scripts/idea-actions.py (the auto-deploy rules, unchanged)

## Review notes
1. /home/dan/homelab/.worktrees/image-patch-autobump/scripts/image-check.py:496: the ntfy security alert still ends with `/update-stack <svc>` even when a proposal note was written for that bump. It is harmless, but it could point at the Proposed tab instead.
2. scripts/image-check.py:74: the strict regex accepts matching pre-release suffixes, so `3.5.0-rc1` -> `3.5.1-rc1` returns true. The plan's own regex allows this, and nothing is pinned to an rc today. I'm noting it only because the plan's prose says "rc ... skipped".
3. scripts/image-check.py:206 (`pending_for`): the glob `bump-radarr-*` would also match a `bump-radarr-remote-*` note. Today shared refs always use the first service (radarr, sonarr), so this can't happen yet.
4. hermes is now eligible for proposals, and the live run would propose v0.22.2 -> v0.22.5. Its image line has no inline comment, so this follows the plan. Dan should still know the assistant container can now be patched once he taps Approve.

## Declined to judge
- Whether the planner keeps `Risk: 1` when it plans an approved bump note: that is existing planner and auto-deploy behaviour (idea-actions.py, unchanged), outside this diff.
- How the old cron line (without `--propose`) gets replaced on deploy: the plan relies on deploy-idea.sh reinstalling on drift, which already exists.
- hub_tags only reads 2 pages, so in theory it could miss a minor tag and propose a patch: this is existing candidate logic that the digest shares.
