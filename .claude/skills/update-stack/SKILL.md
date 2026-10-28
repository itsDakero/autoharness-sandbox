---
name: update-stack
description: Check every pinned image for newer releases, summarize breaking changes, and apply approved upgrades one service at a time.
argument-hint: "[service name to limit the check]"
disable-model-invocation: true
---

# Update the stack $ARGUMENTS

Pinned images now: !`git ls-files '*compose.yaml' | grep -v '^templates/' | xargs grep -Hn '^\s*image:' | sed 's/ *#.*//'`

## 1. Check (read-only)
For each image (or only `$ARGUMENTS`), skipping locally built `homelab/*` images:
- **Newer tags**:
  - Docker Hub: `curl -s 'https://hub.docker.com/v2/repositories/<ns>/<repo>/tags?page_size=100&ordering=last_updated' | jq -r '.results[].name'`
    (official images use the `library/` namespace).
  - GHCR: `tok=$(curl -s 'https://ghcr.io/token?scope=repository:<owner>/<repo>:pull' | jq -r .token)`, then
    `curl -s -H "Authorization: Bearer $tok" https://ghcr.io/v2/<owner>/<repo>/tags/list | jq -r '.tags[]'`.
  - Keep the same tag *flavour* as the current one (e.g. `-rootless`, `v` prefix). Ignore pre-releases (`rc`, `beta`, `alpha`, `dev`, `nightly`)
    and moving tags (`latest`, `stable`, `2`, `2.5`). Pick the highest semver.
- **Release notes**: the GitHub repo behind the image (from Docker Hub / OCI source label / README):
  `curl -s 'https://api.github.com/repos/<owner>/<repo>/releases?per_page=30' | jq -r '.[] | select(.prerelease|not) | "## \(.tag_name)\n\(.body)"'`.
  Read every release between current and candidate. Note breaking changes, required migrations, config/env renames, and new minimum versions.
- Note relevant notes in this repo (e.g. docs/m1-core.md says AutoKuma 2.1.0 fixes re-login; the
  uptime-kuma and autokuma major versions must match).

Show one table and stop:

| Service | Current | Candidate | Type (patch/minor/major) | Breaking changes / actions | Recommend |

## 2. Apply (only the approved rows, one service at a time)
1. Bump the tag in the compose file (the hooks check pinning and run `config -q`).
2. `scripts/dc.sh <dir> pull`, then `scripts/dc.sh <dir> up -d` (prompts).
3. Health: `scripts/dc.sh <dir> ps` (healthy/running), `scripts/dc.sh <dir> logs --tail 50` (no errors), the app's
   URL returns 200, and the dashboard (`curl -s http://localhost:8000/api/services`) / `scripts/kuma-status.py <name>` show `up`.
4. If it's unhealthy: show logs and offer to roll back (restore the old tag, `up -d`). Don't push on.
5. `git commit -m "Update <service> <old> → <new>"` per service, then continue with the next one.
Core order if several: docker-socket-proxy → traefik → adguard → ntfy → uptime-kuma(+autokuma) → dashboard.
