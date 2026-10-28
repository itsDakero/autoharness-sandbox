# Prune Old Images and Build Cache

Value: 2
Effort: 1
Score: 10
Source: scout 2026-10-15 (audit sweep)

## Problem
3.7 GB is reclaimable: unused images (playwright v1.48.2-noble 2.98 GB, node 22.11.0-alpine, node:22-alpine,
httpd, hello-world), 21 old `homelab/dashboard` tags and 464 MB of build cache. Every dashboard deploy adds
another tag, so it keeps growing.

## Proposal
- `scripts/deploy-idea.sh`: after a successful deploy that rebuilt a `homelab/*` image, keep the current and
  the previous tag (for rollback) and remove older ones; prune build cache older than 168h
  (`docker builder prune --filter until=168h -f`).
- The same step as a standalone `scripts/image-prune.sh` (dry run by default, `--apply` to remove), so it can
  run after a hand deploy too.
- Never removes an image a container uses, running or stopped. Only `homelab/*` tags and build cache are
  removed automatically; other unused images are listed for Dan, who removes them by hand (deletes are on
  the always-manual list).

## Checks
`bash -n`; dry run lists the 21 dashboard tags minus the newest two and the build cache; `docker ps -a`
images are never in the list. Docs: `docs/m5-pipeline.md` deploy section, CLAUDE.md scripts list.

_Added by Claude in the terminal for Dan, 2026-10-15._

## Plan
Goal: Stop old `homelab/*` image tags and old build cache from piling up. `deploy-idea.sh` prunes them after every build deploy, and a standalone script does the same after a hand deploy.
Kind: script, plus a change to `scripts/deploy-idea.sh`
Not a "deletes data" park: images and build cache can be rebuilt. Only `homelab/*` tags and build cache are removed automatically. Every other unused image is only listed, and Dan removes those by hand, as the note asks.

Files:
- `scripts/image-prune.sh` (new, executable, `set -euo pipefail`). Usage: `image-prune.sh [--apply]`. The default is a dry run that changes nothing.
  1. In-use IDs: get the full image ID of every container, running or stopped:
     `docker ps -aq | xargs -r docker inspect --format '{{.Image}}'`
     It must keep that exact `--format`, because the guard blocks inspect without one.
  2. Candidates: run `docker images --no-trunc --format '{{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}'`. For each `homelab/<name>` repo, sort its tags with `sort -V`. Keep the newest 2, plus any tag whose ID is in use. Every other tag is "remove".
  3. Build cache: dry run prints the `Total:` line of `docker buildx du --filter until=168h`. `--apply` runs `docker builder prune --filter until=168h -f`.
  4. "For Dan (remove by hand)": every image that isn't `homelab/*` and whose ID is not in use, plus dangling `<none>` images. Print one line each (repo:tag, size), then a hint: `docker rmi <repo:tag>`. Never remove these.
  5. `--apply` removes each candidate with `docker rmi <repo>:<tag>`, by tag and never by ID, never with `-f`. If one rmi fails, print it, carry on, and exit 1 at the end. Finish with a summary: N tags removed, cache reclaimed.
  - Any other argument: print usage and exit 2.
- `scripts/deploy-idea.sh`: in the services loop, set a flag when the dir has a `Dockerfile` (the `--build` branch). After the "checking" loop and before `git push`, if the flag is set:
  `echo "== pruning old homelab images"; "$REPO/scripts/image-prune.sh" --apply || echo "deploy-idea: image prune had errors (deploy is fine)" >&2`
  A prune failure must never fail the deploy (`set -e`).
- `docs/m5-pipeline.md`: add one sentence to the Deploy (Dan) bullet (around line 65). Add `scripts/image-prune.sh` / `--apply` to the Commands block.
- `CLAUDE.md`: add to the scripts list: `image-prune.sh [--apply]` (old `homelab/*` tags beyond the newest two + build cache >7d; lists other unused images for Dan; deploy-idea runs it after a build).

New service: None
New env vars: None

Checks the builder must run:
- `bash -n scripts/image-prune.sh scripts/deploy-idea.sh`
- `scripts/image-prune.sh` (dry run only; the builder must NOT run `--apply`). The output must show:
  - 0.1.0 through 0.13.0 of `homelab/dashboard` (19 tags) as remove. Keep 0.14.1 and 0.15.0 (the latter is in use).
  - `homelab/leafgreen:0.1.0` kept.
  - A cache Total line.
  - Playwright, both node, httpd, hello-world, ubuntu, and the old ntfy/jellyfin/kuma/traefik in the For-Dan list.
- Cross-check against the dry run: no ID from `docker ps -aq | xargs docker inspect --format '{{.Image}}'` appears in either list.
- Fact check: the note says "21 tags minus the newest two". There are actually 21 dashboard tags, so 19 to remove.

Review focus:
- Tags sorted as strings (0.10.0 < 0.2.0) -> must use `sort -V`. 0.15.0 and 0.14.1 are kept, not 0.9.0.
- An older tag still used by a stopped or running container (e.g. after a rollback) -> kept, on top of the newest two.
- Two tags share one image ID -> rmi by tag only untags, and never `-f`.
- `docker rmi` or `builder prune` fails partway -> later items still run, exit 1, and the deploy still pushes, drops the branch and posts to Discord.
- A deploy with no Dockerfile dir (a plain compose change) -> no prune runs.

Docs: CLAUDE.md scripts list, `docs/m5-pipeline.md` Deploy bullet + Commands block.

## Manual steps
- Once after deploy: run `scripts/image-prune.sh`, then `scripts/image-prune.sh --apply` to clear today's 19 old dashboard tags and old build cache.
- Remove the listed third-party images by hand with `docker rmi`, if wanted. Playwright alone is 2.98 GB.

## Review notes
1. The plan's numbers are out of date. `homelab/dashboard` now has 24 tags, not 21, because 0.14.0, 0.14.1 and 0.15.0 were built after the note was written. The dry run keeps 0.15.0 (in use) and 0.14.1, and removes 22 tags (0.1.0 to 0.14.0), not 19. The logic is right; the Manual steps line "today's 19 old dashboard tags" should say 22.
2. /home/dan/homelab/.worktrees/prune-old-images/scripts/image-prune.sh:20: the script runs with `set -euo pipefail`. If a container is removed between `docker ps -aq` and `docker inspect`, the script stops before printing anything. That is harmless: nothing gets removed, and deploy-idea carries on because of its `||`.
3. image-prune.sh, the For-Dan loop: an untagged `homelab/x:<none>` image would be listed as `homelab/x:<none>`, and the `docker rmi <repo:tag>` hint doesn't work for it. Dangling images need their ID.
4. A `homelab/*` tag that a compose file pins, but that no container uses (the service is `down`) and that is older than the newest two, would be removed. It can be rebuilt, and nothing like that exists today.
5. The changes in the worktree are not committed yet (`git status` shows M/A). That is expected before the commit step.

## Declined to judge
- Non-semver `homelab/*` tags (e.g. `dev`) sorting above the version tags with `sort -V`: all homelab tags are pinned semver, and the plan only covers version tags.
- How long the prune adds to idea-actions.py's 20-minute deploy timeout: removing about 22 tags plus the cache prune takes seconds.
