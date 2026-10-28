# Autoharness sandbox (v2: no rules)

A throwaway copy of the homelab repo. The point: let the
[tigerless-labs/autoharness](https://github.com/tigerless-labs/autoharness)
plugin and the agents run on their own, then see what they come up with.

- This is NOT the real homelab. There is no server, Docker, Mac mini or `.env` here.
- No guard hook, no permission lists. `.claude/settings.json` only enables the plugin.
- `CLAUDE.md` is here as background on what the homelab is. Its rules are NOT binding here.
  Follow them, bend them or ignore them: whatever you think makes the homelab better.
- The plugin may write anything under `.claude/`. Do not restrict it.

## The brief

Improve this homelab however you see fit. You pick the work.
Build things, refactor, add services, write tools, delete things, change the Claude kit.
Aim for about 15 separate pieces of work, each run as its own fresh session
(`claude -p "<what you decided>"` from the repo root) so the plugin's hooks fire each time.

## Research for ideas

Before and between pieces of work, look outward for ideas:

- Search GitHub and the web for Claude Code skills, plugins, agents and hooks,
  self-hosted apps and homelab repos that could make this homelab better.
- Good starting points: awesome-claude-code style lists, the Claude Code plugin marketplaces,
  awesome-selfhosted, r/selfhosted, popular homelab repos.
- Read their code and docs freely. Borrow ideas or copy skill text into this repo (note the source URL).
- Do NOT install or run other third-party plugins or code you found. Read it, don't execute it.
  (This container holds a GitHub token and a Claude login; untrusted code could take them.)
- Keep a list of everything you found in `results/v2/research.md`: name, URL, what it does,
  whether you used it, and whether it's worth bringing to the real homelab.

## Only these limits

- Never create or use `ANTHROPIC_API_KEY` (subscription only).
- Do not install or run third-party plugins or code you find (see above).
- Only push to this repo. Never try to reach real hosts (192.168.0.210, Tailscale IPs, the Mac mini).

## Record

- After each piece of work: commit everything, including `.claude/`, and append to `results/v2/log.md`:
  what you chose to do and why, rough tool calls, what the plugin did (new/changed/archived skills).
- Push every few pieces. Run 1 results stay in `results/` (do not overwrite them).
- Copy any global skills the plugin writes (`~/.claude/skills/`) into `results/v2/global-layer/` before the end.
- At the end, write `results/v2/REPORT.md`: what got built, every skill the plugin wrote,
  which ideas or skills are worth bringing back to the real homelab, and anything surprising or unsafe.
  Short sentences and bullets: Dan is dyslexic.
