# M6 research + assistant – plan

Status: A and B **done** (2026-10-15: first scout run, 2 of 3 proposals approved and built). C **done**
(2026-10-15: Mac mini `100.74.81.122`, Ollama 0.40.4, 3 models; came back unattended from a pull-the-plug
test: Ollama's first bind failed before Tailscale was up, launchd's retry got it). D **done** (2026-10-15: Hermes answers Dan on Discord; first reply 88 s, with a cold model load). E **done** (2026-10-16, built by hand in a terminal: it edits
`.claude/`, which the background builder can't write; that also added the loop's terminal-build lane).

Done when a Friday scout run has put 3 scored proposals on the dashboard, Dan has approved one, and the build
loop has built it; and an assistant agent answers on chat using a model served by the Mac mini, no paid API.

## Why
- The build loop only builds what Dan thinks of. A scout looks outward (new AI tools, self-hosted projects on
  GitHub) and inward (the homelab's waste and costs) and brings back a few weekend projects each week.
- The Mac mini (M2, 16 GB) sits unused. It can serve a local model, so an agent like Hermes costs nothing to run.

## Rules carried over
- Anything an LLM writes on its own is a **proposal**, never a queued idea: it goes to `ideas/proposed/`
  and only Dan's Approve moves it to `ideas/`. The build loop never reads `ideas/proposed/`.
- Same billing as M5: interactive Claude Code on the subscription, no `claude -p`, no `ANTHROPIC_API_KEY`.
- Anything pasted from the web (READMEs, changelogs, release notes) is untrusted input, the same as in M5.

## Stage A: scoring + Proposed tab
- **Note format** (`ideas/proposed/<slug>.md`): the usual idea note plus a header block:
  ```
  Value: 4   (how much it helps Dan or the family, 1-5)
  Effort: 2  (1 = one script ... 5 = multi-stage milestone)
  Risk: 2    (media, secrets, network, data loss = high, 1-5)
  Score: 16  (value x (6 - effort); risk >= 4 shows a warning, never hidden)
  Source: scout 2026-10-16 | hermes | ...
  ```
  then Problem, Proposal, Existing tools checked (name, link, version, last release), Rough plan.
- **Proposed tab** on `/admin`, next to Parked/Deploy and built the same way: carousel sorted by score,
  count in the nav. Buttons:
  - **Approve**: moves the note to `ideas/` (the loop plans it as usual; the header stays for the planner).
  - **Dismiss** (optional reason): moves it to `ideas/dismissed/`, which the scout reads so it doesn't
    propose the same thing again.
- **Before proposing**, the scout and the assistant read `ideas/dismissed/` and `ideas/rejected/` (builds Dan
  rejected on the Deploy tab, with a `Reason:`). No proposal repeats one of those unless something changed
  that answers the reason; then the note gets a `Changed since rejected:` line saying what.
  - **Later**: leaves it in Proposed but sends it to the back of the line.
- Both moves stay inside the `/ideas` mount, so the dashboard can do them itself (no runner needed).
- The idea box also gets optional Value/Effort fields, so Dan's own ideas can be scored too (not required).

### Built (2026-10-15)
- `core/dashboard/app/ideas.py` (`proposed()`, `decide()`), `GET /api/widgets/proposed`,
  `POST /api/ideas/proposed` (`approve | dismiss | later`, same-origin + admin like the other writes).
  Dashboard 0.14.0.
- The score is worked out from Value and Effort when both are there, so a note's own `Score:` line can't
  push it up the list. Risk >= 4: a red badge and a warning box on the card.
- **Approve** appends `_Approved on the dashboard, <date>._` and posts "Idea queued" to Discord. It refuses
  if `ideas/<slug>.md` exists or the slug was built, parked or rejected before (rename the note first).
- **Dismiss** appends `## Dismissed <date>` + `Reason: ...` (or "No reason given."), the same shape as
  `## Rejected`, into `ideas/dismissed/<slug>.md` (`-2`, `-3`... if dismissed before).
- **Later** is kept in `ideas/proposed/.later.json`, so the order survives a reload.
- `ideas/proposed/` and `ideas/dismissed/` are **git-ignored**: drafts, written by the scout and moved by the
  dashboard, which has no git. An approved note gets committed by `idea.sh start` like any other. Both
  folders still reach restic (the repo dir is a backup source).
- Idea box: optional Value/Effort selects; with both, the note gets `Value/Effort/Score/Source: dashboard`.

### Patch bump proposals (image-check)
`scripts/image-check.py --propose` (the Monday cron) writes one note per service to `ideas/proposed/`
(`Risk: 1`, `Source: image-check <date>`) for each strict-semver patch bump: current and newest tag both
match `vN.N.N[-suffix]`, same major.minor and suffix, higher patch. Never proposed: anything with a compose
file under `core/`, gluetun, `HOLDS` pins, an `image:` line with an inline `#` comment, linuxserver
`x.y.z.b-lsN`, date tags, minor/major bumps (those stay in the digest only). Slug `bump-<service>-<new tag>`
(e.g. `bump-seerr-v3-5-1`); no second note if that slug exists anywhere in `ideas/` (incl. dismissed
`-N`) or another `bump-<service>-*` is still pending. Dan still has to Approve each note on the Proposed tab;
only then does the Risk 1 auto-deploy build it. `--print --propose` shows the notes and writes nothing.

## Stage B: the scout
- `idea-scout` agent (Opus, read-only apart from `ideas/proposed/`) + a `/scout` skill.
- **When**: Friday mornings. The `/build-ideas` loop runs `/scout` when it's Friday after 06:00 and
  its last loop run (`ideas/proposed/.last-scout-auto`) is older than 6 days, so no second session or new
  scheduler is needed. `/scout` by hand works any time and doesn't move the Friday run.
- **Three sweeps per run**, each with a time budget:
  1. **AI/agent tech**: new agent frameworks, Claude Code skills/plugins, local models that fit the Mac mini.
  2. **Homelab audit** (read-only): idle or duplicate services, image versions far behind, container
     CPU/RAM (`docker stats --no-stream`), disk growth, restic/B2 size (the only running cost), power
     (GPU idle state), stack overlap. Never touches `.env`, never reads secrets.
  3. **GitHub projects**: self-hosted projects (awesome-selfhosted, trending) that would replace, improve
     or add to something running here. Health check: stars, last release, open issues, licence,
     pinned Docker image available.
- **Output**: the **3** best ideas as deep notes (above format), plus `ideas/proposed/_report-<date>.md`
  with an "Also spotted" list of one-liners so nothing is lost. Discord: "Scout: 3 proposals" with titles,
  scores and a link to `/admin#proposed`.
- **First run, directed topics** (instead of a free sweep):
  - Assistant agents: Hermes Agent (Nous Research) vs alternatives, running on a local model on an
    M2 with 16 GB. Which one, which model, what it can safely do here.
  - obra/superpowers (Claude Code skills pack): would it improve the build loop's planner/builder/reviewer?
  - Plus one normal audit idea.

### Built (2026-10-15)
- `.claude/agents/idea-scout.md` (Opus) has two modes, so no single context holds a whole run:
  `sweep <ai|audit|github> [topic]` (read-only, about 15 web lookups, at most 6 candidates with
  Value/Effort/Risk and evidence) and `write <date>` (picks 3 by score, at most 2 from one sweep, a directed
  topic's best always in; writes the notes and `_report-<date>.md`; Write tool only).
- `.claude/skills/scout/SKILL.md` (`/scout [topic]`): the 3 sweeps in parallel → write → checks
  `git status` didn't change (anything outside `ideas/proposed/` stops the run, unstamped) →
  `scripts/idea.sh scout-done [auto]` (stamps `ideas/proposed/.last-scout`; a loop run, args `auto`, also
  `.last-scout-auto`) → one Discord post.
  The first run (no stamp) uses the directed topics above; `/scout <topic>` points one sweep at a topic.
- Held topics (2026-10-25): `ideas/proposed/_topics.md` (git-ignored; one `- ` line per topic, indented lines
  continue it). A run without its own topic, the Friday loop run included, gives the first one to the sweep it
  fits best, then `scripts/idea.sh scout-topic-done` drops it. Dashboard ignores `_` files in `proposed/`.
- `/build-ideas` checks `scripts/idea.sh scout-due` each round: due on Fridays from 06:00 when the loop
  stamp (`.last-scout-auto`) is 6+ days old (or missing). Hand runs don't count, so every Friday gets one.
- Permissions (`.claude/settings.json`): Write to `ideas/proposed/**`; read-only audit commands
  (`docker stats --no-stream`, `docker images/ps/system df`, `df -h`, `du -sh`, `nvidia-smi`,
  `journalctl -u homelab-backup*`); WebFetch for a few more docs sites. Other sites ask, so a background
  run can wait on a prompt: allow the domain if one keeps coming up.
- restic's repo is root-only, so backup size comes from the backup journal, not `restic stats`.
- The dashboard skips `_report-*.md` (not a slug); read the report in the repo for now.

## Stage C: Mac mini as model server (manual runbook, not in the repo's compose)
Mac mini M2, 16 GB, on 24/7, headless. Wiped and set up fresh (Dan, by hand; needs a monitor + keyboard once).
- **Wipe**: System Settings → General → Transfer or Reset → Erase All Content and Settings.
- **Setup Assistant**: one admin user, no Apple ID needed, skip Siri/analytics/Screen Time.
- **FileVault off**: with it on, a reboot after a power cut stops at the unlock screen and the Mac stays
  offline until someone types the password. It holds only models; the trade-off is accepted here.
- **Auto-login** as that user (needs FileVault off), so Ollama and Tailscale start after any reboot.
- **Energy**: prevent sleep with the display off, start up after a power failure, wake for network access
  (or `pmset -a sleep 0 disksleep 0 autorestart 1`, run as root on the Mac).
- **Updates**: download automatically, install by hand, so it never reboots on its own mid-week.
- **Remote access**: Sharing → Remote Login (SSH, key only) and Screen Sharing for the odd GUI task.
  Tailscale (standalone app, start at login). An HDMI dummy plug only if Screen Sharing resolution annoys.
- **Model**: Ollama (or LM Studio), a ~14B model that fits in 16 GB with room for the OS; chosen from the
  scout's first report.
- **Exposure**: Ollama has no auth. Reachable from the homelab and the tailnet only, never forwarded;
  the exact bind (tailnet IP vs LAN + pf rule) is settled in the runbook, since the tailnet IP may not be
  up yet when Ollama starts at boot.
- Uptime Kuma monitor on the Ollama endpoint (ntfy if down), so a hung or asleep Mac is noticed.
  Done: `mac-mini-ollama` (labels on `core/uptime-kuma`, 3 retries before ntfy since it's on Wi-Fi).
- First smoke test (one short prompt each, 64K context, not the bench): granite4.1:8b 19 tok/s but 11.2 GB
  resident (near the 11.8 GiB GPU limit), gemma4:12b-it-qat 13 tok/s at 7.6 GB, qwen3.5:9b 6 tok/s at 7.7 GB.
  `scripts/model-bench.py` (results in `docs/mac-mini.md`) does the real comparison with tool calls.
- Finding: the pulled `qwen3.5:9b` is the MLX/safetensors build, not q4_K_M GGUF (`qwen3.5:9b-q4_K_M`); likely why it ran at 6 tok/s.
- Runbook: `docs/mac-mini.md` (written 2026-10-15). Exposure settled there: Ollama binds the Mac's tailnet IP
  only; launchd retries until Tailscale is up at boot, so no pf rule is needed.

## Stage D: assistant agent on the homelab (Hermes or the scout's pick)
- `tools/<name>/compose.yaml` on the homelab, model = the Mac mini over Tailscale. Pinned image,
  usual labels, next free port (8086), web UI behind the dashboard login like Dozzle.
- **Chat**: Discord, its own bot in a separate text channel (not #homelab, which stays the webhook feed),
  answering Dan only.
- **What it may do**:
  - Read: service status (via the dashboard's `/api/agent/*`, never the socket proxy: decided 2026-10-15), parked
    ideas, the build queue, the scout reports.
  - Write: new notes into `ideas/proposed/` only (source `hermes`), so Dan approves them like the scout's.
- **What it may not**: docker.sock, repo or `/mnt/media` mounts beyond `ideas/` and the read-only runbooks, the env file,
  shell on the host, deploys. If the agent can't be fenced in this way, it's parked.

### Built (2026-10-15)
- `tools/hermes/`: `compose.yaml`, `config.yaml`, `SOUL.md` (its instructions). `nousresearch/hermes-agent:v0.22.5`,
  `gateway run` (Discord only). Model qwen3.5:9b on the Mac mini, 64K context.
- **Changed from the plan above**: no web UI and no port (Discord is the interface; nothing to put behind a
  login). Status comes from a **file**, not `/api/agent/*`: with the minimal toolset Hermes has no tool that
  makes HTTP calls, so the dashboard writes `${APPDATA_PATH}/dashboard/agent-feed/status.json` every minute
  (`AGENT_FEED_DIR`, dashboard 0.15.0: services + status, queued/parked/proposed/ready/rejected ideas, nothing
  secret) and Hermes mounts it read-only at `/homelab/status`. Dan chose this (2026-10-15).
- **Fence**: own `hermes` network (no `proxy`, no `socket-proxy`: checked, the proxy doesn't resolve); mounts:
  its data `/srv/homelab/hermes` → `/opt/data`, `config.yaml` and `SOUL.md` read-only over it (it can't edit its
  own model or tools), `ideas/` read-only at `/homelab/ideas`, `ideas/proposed/` read-write (checked both);
  both again under `/opt/data/homelab/ideas` (its file tool resolves a relative `homelab/ideas/...` from
  `/opt/data`: three proposals were lost in its data dir that way, found 2026-10-18);
  `docs/` and `forensics/README.md` read-only at `/homelab/docs` and `/homelab/forensics-README.md`, and again
  under `/opt/data/homelab/` (2026-10-19). Repo root and CLAUDE.md stay unmounted. The README is a single-file
  bind: after a git change to it, recreate hermes or it shows the old copy;
  runs as uid 1000 (`HERMES_UID`), `no-new-privileges`, `mem_limit: 3g`. It can still reach published LAN ports
  (as any device can) but has no tool to do so; a DOCKER-USER fence is due if a network tool is ever turned on.
- **Tools** (checked with `docker exec -u 1000 hermes hermes tools list --platform discord`): file, todo,
  memory, session_search, clarify enabled; everything else disabled (`agent.disabled_toolsets` too).
  No fallback provider, `auth.adopt_external_logins: false`, telemetry and update checks off, approvals auto-deny.
- **Discord**: env `DISCORD_BOT_TOKEN`, `DISCORD_ALLOWED_USERS`, `DISCORD_ALLOWED_CHANNELS`,
  `DISCORD_FREE_RESPONSE_CHANNELS`, `DISCORD_HOME_CHANNEL`, from `HERMES_DISCORD_*` in the env file. The bot
  needs the Message Content **and** Server Members intents, and an invite to the server (scopes `bot` +
  `applications.commands`, permissions `117760`). Not invited = it connects fine but logs
  `Channel directory built: 0 target(s)` and never sees a message.
- Expected log warning: `model.context_length pins qwen3.5:9b at 65,536 ... the pin wins`. That's deliberate
  (the Mac's memory; see the bench).
- Kuma: `hermes` docker monitor through the socket proxy (Kuma's access, not Hermes's); the model has
  `mac-mini-ollama`. Tile under Tools, no link.
- Logs: `/srv/homelab/hermes/logs/` (`gateway.log`, `errors.log`, `agent.log`).
- **Upgrades**: Hermes ships often. Bump the tag via `/update-stack hermes`, then re-run the tools check above,
  since a new version can add toolsets (the disabled list catches the named ones, not new names).

### Personal feed
The dashboard (0.16.0) also writes `agent-feed/personal.json` every 15 min (atomic tmp + rename), read by Hermes
from `/homelab/status/personal.json`. Blocks: fitness (the fitness app's read-only `/api/feed.json`), today's
outfit (wardrobe `/api/daily.txt`), books being read (books `/api/current`, no auth), deals (changedetection watches changed
in 7 days + LeafGreen card drops). Each block is `{updated_at, data, error}`: a source that fails is null with a
short error, never stale data. Env vars (dashboard): `CHANGEDETECTION_API_KEY`;
empty = "not configured". No check-in notes, book notes or Garmin JSON.

### Morning brief
`scripts/morning-brief.py` (cron 07:00, replaces the old outfit-only job) posts one plain-template Discord message, no
model call: outfit (live wardrobe `/api/daily.txt`, 204 = none), readiness/illness and yesterday's activity
(personal.json, only when `fitness.data.date` is today), deals, services not up and Parked/Deploy/Proposed counts
(status.json). A feed file missing, unreadable or older than 2 h (personal) / 15 min (status) is skipped with one
"stale/missing" line. `MORNING_BRIEF_ENABLED=0` turns it off; `test` posts now, `--print` prints. Log: `journalctl -t morning-brief`.

## Stage E: researcher before the planner
- `idea-researcher` agent (Sonnet, read-only apart from the note): writes a `## Research` section
  (existing tools, versions, known problems, links).
- Runs only when needed: the planner gets a third verdict, **RESEARCH** (with what it wants to know).
  The loop runs the researcher, then the planner again. Small ideas skip it; scout notes already
  have their research.
- Updates `docs/m5-pipeline.md` (stage list) and CLAUDE.md's kit section.
- **Built** (2026-10-16): `.claude/agents/idea-researcher.md` (Sonnet, read-only: it returns the section and the
  loop appends it). "Small" and "scout note" are a script's call, not the planner's: `scripts/idea.sh research-ok`
  says no for a note with `## Research`, `Research: yes`, `Source: scout…` or `Effort:` 1-2. One research round per
  idea; a second RESEARCH is a PARK. The `Research: yes` path is unchanged (the planner's research mode).

## Order
A → B (first scout run decides C/D's details) → C → D → E. E is independent and can move earlier.

## Decided (Dan, 2026-10-14)
- Mac mini: on 24/7, wiped and set up headless (Stage C).
- Assistant chat: Discord, separate text channel.

## Decided (Dan, 2026-10-15)
- Hermes gets homelab status from a token-protected, GET-only `/api/agent/*` on the dashboard, **not** the
  socket proxy (a container's JSON there includes its env). Stage D builds that API.
- Hermes's model: **qwen3.5:9b** (the MLX build), from the bench in `docs/mac-mini.md`: 10/10 tool calls,
  6 s per call, 8.9 GB resident at 64K context (~3 GB GPU headroom). granite4.1:8b (10/10, 2 s, but 11.2 GB of
  the 11.8 GiB GPU limit) stays pulled as the fallback.
- Hermes's toolsets: the **minimal set**. On: file (its mounts only), memory, session_search, todo, clarify.
  Off: terminal, code_execution, browser, web, delegation, cronjob, discord_admin. No `fallback_providers`,
  `approvals.mode: manual`. Web search can come later as its own idea (needs the network fence).

## First scout run (2026-10-15, by hand)
Report: `ideas/proposed/_report-2026-10-15.md` (git-ignored; restic has it). Versions, star counts and issue
numbers below are the scout's and were not re-checked.
- Approved and built: `apply-pending-image-upgrades` (Traefik security fix first), `build-loop-review-focus`
  (from obra/superpowers; the plugin itself is **not** to be installed: its SessionStart hook and
  self-committing steps clash with the loop. Copy pinned pieces only).
- Built, waiting on Dan's run: `mac-mini-model-bench` (`scripts/model-bench.py`) benchmarks models on the Mac mini at 64K context.
- **Stage C input**: Hermes needs a model with **≥ 64K context**, and macOS gives the GPU about 2/3 of the 16 GB.
  Candidates: gemma4:12b-it-qat, qwen3.5:9b q4_K_M, granite4.1:8b. Ollama settings to test:
  `OLLAMA_CONTEXT_LENGTH=65536`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_KEEP_ALIVE=24h`.
- **Stage D input**: the pick is Hermes Agent; runner-up is OpenClaw, which has had malicious skills in its
  hub. Two changes to the plan above, to decide before D:
  - The assistant must **not** reach the socket proxy. It allows `CONTAINERS`, so a container's JSON
    includes its env (API keys, VPN credentials). Give it a token-protected, GET-only `/api/agent/*` on
    the dashboard instead (services + Kuma, queue, parked, proposed, latest report).
  - Hermes toolsets: only file, memory, session_search, todo and clarify. terminal, code_execution, browser,
    web, delegation, cronjob and discord_admin stay off. Pin `model.context_length`, set no
    `fallback_providers` (that would mean paid API billing), and use `approvals.mode: manual`.
    It needs its own network with a DOCKER-USER rule allowing the internet + the Mac's Ollama port only, if
    any network tool is ever turned on.
- Next week's strong candidates (Also spotted): a weekly image-freshness digest (score 16), capping container
  logs, pruning old images/build cache (3.7 GB reclaimable), and GPU persistence mode.

## Open questions
- Scout cost: two Opus-heavy runs a week (scout + loop) use more of the plan's limits. Fall back to
  Sonnet for the sweeps and Opus only for the 3 deep notes if limits bite.
