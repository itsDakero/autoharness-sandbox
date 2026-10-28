# Bump seerr to v3.5.1 (patch)

Value: 2   (patch release: bug and security fixes)
Effort: 1  (one image tag)
Risk: 1    (patch bump within 3.5, same tag flavour)
Score: 10
Source: image-check 2026-10-26

## Problem
`media/seerr/compose.yaml` pin `ghcr.io/seerr-team/seerr:v3.5.0`; `v3.5.1` is out (patch). Release notes mention security: v3.5.1.

## Proposal
- In `media/seerr/compose.yaml`, change only the `image:` tag `v3.5.0` -> `v3.5.1`; nothing else.
- Release notes: https://github.com/seerr-team/seerr/releases
- Check: scripts/dc.sh media/seerr config -q. No manual steps.

_Approved on the dashboard, 2026-10-26._

## Plan
Goal: Bump Seerr from ghcr.io/seerr-team/seerr:v3.5.0 to v3.5.1 (a patch release with security fixes).
Kind: change to media/seerr
Files:
- media/seerr/compose.yaml: on line 6, change `image: ghcr.io/seerr-team/seerr:v3.5.0` to `:v3.5.1`. Nothing else changes.
- docs/m2-media.md: on line 246, change "`ghcr.io/seerr-team/seerr` v3.5.0" to "v3.5.1".
New service (if any): None
New env vars: None
Checks the builder must run:
- scripts/dc.sh /home/dan/homelab/.worktrees/bump-seerr-v3-5-1/media/seerr config -q
- git diff main -- media/seerr docs/m2-media.md: the diff should be exactly the two tag lines.
- Confirm the tag exists: curl -s https://github.com/seerr-team/seerr/releases/tag/v3.5.1 (a GET; the page should exist)
  (source: https://github.com/seerr-team/seerr/releases)
Review focus:
- The tag is missing on GHCR or has a different flavour (e.g. `3.5.1` with no `v`) -> the builder stops and reports it, and does not guess a tag.
- The v3.5.1 release notes list a breaking change or a database migration -> mention it in the build summary, so Dan knows before deploying. The config lives in ${APPDATA_PATH}/seerr/config, which the nightly restic backup covers.
Docs: docs/m2-media.md line 246 (version mention). No changes to the port table or layout.

## Manual steps
None. deploy-idea.sh pulls the image and recreates the container. After deploy, the Kuma monitor `seerr` should go green, and family users should still be able to sign in with Jellyfin.

## Review notes
- The v3.5.1 release notes (published 2026-10-21) list one security fix: Node.js goes to 22.23.4 to distrust the compromised eMudhra intermediate CA certificates (CVE-2026-113470). They list no breaking changes and no database migrations, so there is nothing extra to tell Dan before he deploys.

## Declined to judge
None
