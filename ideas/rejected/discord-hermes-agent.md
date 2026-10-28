# Discord Hermes agent

I’d like the Hermes agent to be in charge of the discord server in terms of improving it. So creating an icon for it, adds any features to improve the usage of the server. Let me know what you think, it might need web access first for this so that might have to be the first step

_Added from the dashboard, 2026-10-16._

## Parked 2026-10-16

## Questions
Why parked: it's three projects, and each undoes a fence set on purpose in Stage D (docs/m6-research.md, "Decided 2026-10-15": web, discord_admin and image tools off, no paid fallback):
1. Web access for Hermes needs its own network fence first (a DOCKER-USER rule allowing only the internet plus the Mac's Ollama port; firewall = always-manual), plus a search backend (Hermes docs name no free/self-hosted one).
2. Server admin: Hermes's `discord_admin` toolset covers bans, role changes, channel management. Needs a bot re-invite with Manage Server/Channels/Roles (today 117760). A 9B local model with ban/role powers is a risk only Dan can accept.
3. Icon: Hermes's `image_gen` uses FAL.ai, OpenAI or xAI, all paid; nothing on the Mac mini makes images.
"Adds any features to improve the usage of the server" is open-ended.

Proposed split, each its own idea:
(a) hermes-web-fence: DOCKER-USER rule (manual/bootstrap) plus a web backend (e.g. self-hosted SearXNG).
(b) hermes-discord-proposals: Hermes suggests server improvements as notes in ideas/proposed/ (fits its current fence); Dan or a script applies approved ones. No admin permission needed.
(c) discord-icon: Dan makes/picks the icon, or a later idea adds a local image model.

1. Should Hermes change the server itself (re-invite with Manage Channels/Roles/Server, turn on discord_admin), or only propose changes into ideas/proposed/ for you to approve?
2. Do you want web access as a first idea on its own (a)? Which backend: self-hosted SearXNG (new service, free) or a paid/keyed API such as Tavily/Firecrawl? Confirm you'll apply the DOCKER-USER/firewall rule by hand at deploy.
3. Icon: will you supply one, is a paid image API acceptable (against the no-paid-API rule), or drop it?
4. "Features": which ones (channel layout, roles, pinned guides, bots/webhooks per service, slash commands)? The plan needs a concrete list or a rule for what Hermes may touch.

## Rejected 2026-10-16

Status: rejected
Reason: Too broad: three projects, each undoing a Stage D fence (web, discord_admin, paid image API). Icon done by hand; server tweaks via Hermes proposals; web access later if a real need shows up.
