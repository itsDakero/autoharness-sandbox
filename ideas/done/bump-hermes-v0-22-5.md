# Bump hermes to v0.22.5 (patch)

Value: 2   (patch release: bug and security fixes)
Effort: 1  (one image tag)
Risk: 1    (patch bump within 0.22, same tag flavour)
Score: 10
Source: image-check 2026-10-26

## Problem
`tools/hermes/compose.yaml` pin `nousresearch/hermes-agent:v0.22.2`; `v0.22.5` is out (patch). Release notes mention security: v0.22.5.

## Proposal
- In `tools/hermes/compose.yaml`, change only the `image:` tag `v0.22.2` -> `v0.22.5`; nothing else.
- Release notes: https://github.com/NousResearch/hermes-agent/releases
- Check: scripts/dc.sh tools/hermes config -q. No manual steps.

_Approved on the dashboard, 2026-10-26._

## Plan
Goal: Bump Hermes from nousresearch/hermes-agent:v0.22.2 to v0.22.5 (a patch release with security fixes). The rejected note ideas/rejected/discord-hermes-agent.md is about new Hermes features, not image bumps, so it doesn't apply here.
Kind: change to tools/hermes
Files:
- tools/hermes/compose.yaml: change `image: nousresearch/hermes-agent:v0.22.2` to `image: nousresearch/hermes-agent:v0.22.5`. Nothing else in the file changes.
- tools/hermes/config.yaml: in the line 3 comment, change the reference URL `.../blob/v0.22.2/cli-config.yaml.example` to `.../blob/v0.22.5/cli-config.yaml.example`. This is a comment only. No config keys change.
- docs/m6-research.md: on line 153, change `nousresearch/hermes-agent:v0.22.2` to `v0.22.5`.
New service (if any): None
New env vars: None
Checks the builder must run:
- scripts/dc.sh /home/dan/homelab/.worktrees/bump-hermes-v0-22-5/tools/hermes config -q
- git -C /home/dan/homelab/.worktrees/bump-hermes-v0-22-5 diff --stat. Exactly the 3 files above should change, with one line each.
- grep -rn --exclude='*.env' "v0.22.2" /home/dan/homelab/.worktrees/bump-hermes-v0-22-5/tools/hermes /home/dan/homelab/.worktrees/bump-hermes-v0-22-5/docs. This should return nothing.
Review focus:
- Something other than the tag changed (the healthcheck, volumes or environment) -> the diff should be the image line plus the two comment/doc lines, and nothing else.
- The new image no longer starts the `hermes_cli` `gateway run` process the healthcheck looks for -> deploy-idea will show hermes as unhealthy. Dan rolls back to v0.22.2. The builder can't test this in the background.
Docs: docs/m6-research.md line 153 (the version pin). No changes to the ports table or the layout section.

## Manual steps
None. deploy-idea.sh pulls the image and recreates the container. After deploy, Dan checks that `scripts/dc.sh tools/hermes ps` shows healthy and that Hermes still answers in its Discord channel.

## Review notes
1. The jump is bigger than a usual patch. Per the release page, v0.22.3 rolls up about 620 merged PRs and v0.22.5 about 81, and the curated notes are put off to v0.23.0. v0.22.5 also moves `hermes mcp serve` and the Singularity backend out of core into plugins. Neither is used here: the setup is Discord-only and has no shell or MCP tools. Because this is Risk 1 it may auto-deploy, so Dan should check `scripts/dc.sh tools/hermes ps` shows healthy and that Hermes replies in Discord. If not, he can roll back to v0.22.2, as the plan says.
2. The proposal says the release notes "mention security" for v0.22.5. The releases page lists no security items for v0.22.3 to v0.22.5; the only ones are under v0.21.6. This doesn't block the bump. It's just a flag that the security claim from image-check may be overstated.
3. `_config_version: 50` in `tools/hermes/config.yaml` is unchanged. The release notes say nothing about a config migration, so I couldn't confirm it still matches the new image. The healthcheck and the Discord reply after deploy will show if it doesn't.

## Declined to judge
- Whether the image still starts `hermes_cli gateway run` (Review focus 2): this can't be tested without starting the container. The plan accepts that and leaves it to Dan's check after deploy.
